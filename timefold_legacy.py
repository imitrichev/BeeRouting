from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
from timefold.solver import SolverFactory
from timefold.solver.config import Duration, ScoreDirectorFactoryConfig, SolverConfig, TerminationConfig
from timefold.solver.domain import (PlanningEntityCollectionProperty, PlanningId, PlanningListVariable, PlanningScore, ProblemFactCollectionProperty, ValueRangeProvider, planning_entity, planning_solution)
from timefold.solver.score import Constraint, ConstraintFactory, HardMediumSoftScore, constraint_provider

LOG = logging.getLogger(__name__)
EARTH_RADIUS_KM = 6371.0088
OSRM_URLS = {
    "car": "https://routing.openstreetmap.de/routed-car",
    "bicycle": "https://routing.openstreetmap.de/routed-bike",
    "foot": "https://routing.openstreetmap.de/routed-foot",
}
# Статистический суррогат наземного ОТ Москвы. Эффективная скорость 15.69 км/ч.
PT_WEIGHTS = {"car": 0.55, "bicycle": 0.30, "foot": 0.15}


def hhmm_to_minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def minutes_to_hhmm(value: float) -> str:
    value = max(0, int(round(value)))
    return f"{value // 60:02d}:{value % 60:02d}"


def haversine_matrix(points: Sequence[tuple[float, float]]) -> np.ndarray:
    xy = np.radians(np.asarray(points, dtype=float))
    lat, lon = xy[:, 0], xy[:, 1]
    dlat, dlon = lat[:, None] - lat[None, :], lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def http_json(url: str, params: Mapping[str, Any], timeout: float, retries: int) -> dict[str, Any]:
    request = Request(f"{url}?{urlencode(params, doseq=True, safe='|,;:')}", headers={"Accept": "application/json", "User-Agent": "timefold-engineer-routing/1.0"})
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            if (e.code != 429 and not 500 <= e.code < 600) or attempt == retries:
                raise RuntimeError(f"OSRM HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from e
            time.sleep(min(float(e.headers.get("Retry-After", 2 ** attempt)), 30.0))
        except (URLError, TimeoutError) as e:
            if attempt == retries:
                raise RuntimeError(f"OSRM недоступен: {e}") from e
            time.sleep(min(2 ** attempt, 30.0))
    raise AssertionError("unreachable")


class PairCache:
    """SQLite-кэш направленных пар, общий между запусками и перепланированиями."""
    def __init__(self, path: Path | None) -> None:
        self.db = None
        self.path = path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path)
            self.db.execute("""CREATE TABLE IF NOT EXISTS route_pair (
                profile TEXT NOT NULL, origin TEXT NOT NULL, destination TEXT NOT NULL,
                distance REAL NOT NULL, duration REAL NOT NULL,
                PRIMARY KEY(profile, origin, destination))""")

    @staticmethod
    def key(p: tuple[float, float]) -> str:
        return f"{p[0]:.7f},{p[1]:.7f}"

    def get(self, profile: str, a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float] | None:
        if not self.db:
            return None
        row = self.db.execute("SELECT distance,duration FROM route_pair WHERE profile=? AND origin=? AND destination=?", (profile, self.key(a), self.key(b))).fetchone()
        return (float(row[0]), float(row[1])) if row else None

    def put(self, profile: str, rows: list[tuple[tuple[float, float], tuple[float, float], float, float]]) -> None:
        if not self.db or not rows:
            return
        self.db.executemany("INSERT OR REPLACE INTO route_pair VALUES(?,?,?,?,?)", [(profile, self.key(a), self.key(b), d, t) for a, b, d, t in rows])
        self.db.commit()

    def close(self) -> None:
        if self.db:
            self.db.close()


class OsrmMatrixProvider:
    """Строит только нужные колонки заявок: старт/заявка -> заявка."""
    def __init__(self, *, block_size: int = 50, pair_cache: Path | None = Path("osrm_pair_cache.sqlite"), max_air_distance_km: float | None = None, pt_wait_min: float = 0.0, timeout: float = 30.0, retries: int = 3) -> None:
        if block_size < 1 or (max_air_distance_km is not None and max_air_distance_km <= 0) or pt_wait_min < 0:
            raise ValueError("Некорректные параметры OSRM")
        self.block_size, self.max_air_distance_km = block_size, max_air_distance_km
        self.pt_wait_min, self.timeout, self.retries = pt_wait_min, timeout, retries
        self.cache = PairCache(pair_cache)
        self.memory: dict[tuple[str, str, tuple[int, ...]], tuple[np.ndarray, np.ndarray]] = {}

    @property
    def identity(self) -> dict[str, Any]:
        speed = 1 / sum(PT_WEIGHTS[m] / {"car": 40., "bicycle": 15., "foot": 5.}[m] for m in PT_WEIGHTS)
        return {"provider": "osrm", "scope": "all_points_to_jobs_only", "block_size": self.block_size, "pair_cache": str(self.cache.path) if self.cache.path else None, "max_air_distance_km": self.max_air_distance_km, "public_transport": {"model": "moscow_weighted_proxy_v2", "weights": PT_WEIGHTS, "wait_min": self.pt_wait_min, "effective_speed_kph": round(speed, 3)}}

    def close(self) -> None:
        self.cache.close()

    def build(self, points: Sequence[tuple[float, float]], mode: str, jobs: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
        if mode == "public_transport":
            matrices = {m: self._native(points, m, jobs) for m in PT_WEIGHTS}
            return self._mix(matrices)
        return self._native(points, mode, jobs)

    def _mix(self, matrices: Mapping[str, tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
        modes = tuple(PT_WEIGHTS)
        ds = np.stack([matrices[m][0] for m in modes]); ts = np.stack([matrices[m][1] for m in modes])
        w = np.array([PT_WEIGHTS[m] for m in modes])[:, None, None]
        valid = np.isfinite(ds) & np.isfinite(ts)
        weight = np.where(valid, w, 0).sum(axis=0)
        d = np.divide(np.where(valid, ds * w, 0).sum(axis=0), weight, out=np.full_like(ds[0], np.inf), where=weight > 0)
        t = np.divide(np.where(valid, ts * w, 0).sum(axis=0), weight, out=np.full_like(ts[0], np.inf), where=weight > 0)
        diagonal = np.eye(d.shape[0], dtype=bool)
        t[np.isfinite(t) & ~diagonal] += self.pt_wait_min
        np.fill_diagonal(d, 0.); np.fill_diagonal(t, 0.)
        return d, t

    def _native(self, points: Sequence[tuple[float, float]], mode: str, jobs: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
        if mode not in OSRM_URLS:
            raise ValueError(f"OSRM не имеет профиля {mode!r}")
        point_hash = hashlib.sha256(json.dumps([[round(a, 7), round(b, 7)] for a, b in points]).encode()).hexdigest()
        key = (point_hash, mode, tuple(jobs))
        if key in self.memory:
            return self.memory[key]
        n = len(points); d, t = np.full((n, n), np.inf), np.full((n, n), np.inf)
        np.fill_diagonal(d, 0.); np.fill_diagonal(t, 0.)
        air = haversine_matrix(points) if self.max_air_distance_km is not None else None
        missing: dict[int, list[int]] = {}
        hits = 0
        for i, a in enumerate(points):
            for j in jobs:
                if i == j or (air is not None and air[i, j] > self.max_air_distance_km):
                    continue
                cached = self.cache.get(mode, a, points[j])
                if cached:
                    d[i, j], t[i, j] = cached; hits += 1
                else:
                    missing.setdefault(i, []).append(j)
        LOG.info("OSRM %s: %d пар из SQLite, %d нужно запросить", mode, hits, sum(map(len, missing.values())))
        source_ids = list(missing)
        for s0 in range(0, len(source_ids), self.block_size):
            src = source_ids[s0:s0 + self.block_size]
            target_ids = sorted({j for i in src for j in missing[i]})
            for d0 in range(0, len(target_ids), self.block_size):
                dst = target_ids[d0:d0 + self.block_size]
                needed = {(i, j) for i in src for j in dst if j in missing[i]}
                if not needed:
                    continue
                coords = [points[i] for i in src] + [points[j] for j in dst]
                endpoint = f"{OSRM_URLS[mode]}/table/v1/driving/" + ";".join(f"{lon:.7f},{lat:.7f}" for lat, lon in coords)
                data = http_json(endpoint, {"sources": ";".join(map(str, range(len(src)))), "destinations": ";".join(map(str, range(len(src), len(coords)))), "annotations": "duration,distance"}, self.timeout, self.retries)
                if data.get("code") != "Ok":
                    raise RuntimeError(f"OSRM вернул ошибку: {str(data)[:500]}")
                rows = []
                for si, i in enumerate(src):
                    for dj, j in enumerate(dst):
                        if (i, j) not in needed:
                            continue
                        sec, meters = data["durations"][si][dj], data["distances"][si][dj]
                        if sec is not None and meters is not None:
                            d[i, j], t[i, j] = float(meters) / 1000, float(sec) / 60
                            rows.append((points[i], points[j], d[i, j], t[i, j]))
                self.cache.put(mode, rows)
        self.memory[key] = d, t
        return d, t


@dataclass
class RoutingData:
    points: list[tuple[float, float]]
    job_offset: int
    matrices: dict[str, tuple[np.ndarray, np.ndarray]]

    def leg(self, mode: str, origin: int, job: "Job") -> tuple[float, float]:
        return float(self.matrices[mode][0][origin, self.job_offset + job.matrix_index]), float(self.matrices[mode][1][origin, self.job_offset + job.matrix_index])


@dataclass
class Job:
    job_id: Annotated[str, PlanningId]
    matrix_index: int
    duration_min: float
    window_start: int
    window_end: int
    skill_required: str
    required_vehicle: str | None
    is_urgent: bool

    def __hash__(self) -> int: return hash(self.job_id)
    def __eq__(self, other: Any) -> bool: return isinstance(other, Job) and self.job_id == other.job_id


@planning_entity
@dataclass
class Engineer:
    engineer_id: Annotated[str, PlanningId]
    name: str
    start_index: int
    shift_start: int
    shift_end: int
    skills: set[str]
    vehicle_type: str
    routing_data: RoutingData
    jobs: Annotated[list[Job], PlanningListVariable(allows_unassigned_values=True)] = field(default_factory=list)

    def skill_violations(self) -> int:
        return sum(j.skill_required not in self.skills for j in self.jobs)

    def vehicle_violations(self) -> int:
        return sum(j.required_vehicle is not None and j.required_vehicle != self.vehicle_type for j in self.jobs)

    def schedule(self) -> tuple[int, int, float, list[dict[str, Any]]]:
        now, point, late, total_distance, rows = float(self.shift_start), self.start_index, 0, 0., []
        for job in self.jobs:
            dist, travel = self.routing_data.leg(self.vehicle_type, point, job)
            if not math.isfinite(dist) or not math.isfinite(travel):
                return 1_000_000, 1_000_000, total_distance, rows
            arrival = now + travel; start = max(arrival, float(job.window_start)); finish = start + job.duration_min
            late += max(0, int(math.ceil(start - job.window_end)))
            total_distance += dist
            rows.append({"job_id": job.job_id, "dist_km": round(dist, 2), "travel_min": round(travel, 1), "arrive": minutes_to_hhmm(arrival), "start": minutes_to_hhmm(start), "finish": minutes_to_hhmm(finish)})
            now, point = finish, self.routing_data.job_offset + job.matrix_index
        return late, max(0, int(math.ceil(now - self.shift_end))), total_distance, rows


@planning_solution
@dataclass
class RoutingPlan:
    engineers: Annotated[list[Engineer], PlanningEntityCollectionProperty]
    all_jobs: Annotated[list[Job], ProblemFactCollectionProperty, ValueRangeProvider]
    score: Annotated[HardMediumSoftScore | None, PlanningScore] = None


@constraint_provider
def constraints(factory: ConstraintFactory) -> list[Constraint]:
    # Нарушения не компенсируются наградами: feasibility находится в hard tier.
    return [
        factory.for_each(Engineer).filter(lambda e: e.skill_violations() > 0).penalize(HardMediumSoftScore.ONE_HARD, lambda e: e.skill_violations() * 1_000_000).as_constraint("Required skill"),
        factory.for_each(Engineer).filter(lambda e: e.vehicle_violations() > 0).penalize(HardMediumSoftScore.ONE_HARD, lambda e: e.vehicle_violations() * 1_000_000).as_constraint("Vehicle compatibility"),
        factory.for_each(Engineer).filter(lambda e: e.schedule()[0] > 0).penalize(HardMediumSoftScore.ONE_HARD, lambda e: e.schedule()[0]).as_constraint("Visit time window"),
        factory.for_each(Engineer).filter(lambda e: e.schedule()[1] > 0).penalize(HardMediumSoftScore.ONE_HARD, lambda e: e.schedule()[1]).as_constraint("Shift end"),
        # Unassigned values разрешены; они не получают награду. Срочные имеют 1000x приоритет в medium tier.
        factory.for_each(Engineer).reward(HardMediumSoftScore.ONE_MEDIUM, lambda e: sum(1000 if j.is_urgent else 1 for j in e.jobs)).as_constraint("Assigned job priority"),
        factory.for_each(Engineer).filter(lambda e: len(e.jobs) > 0).penalize(HardMediumSoftScore.ONE_SOFT, lambda e: len(e.jobs) ** 2 * 20).as_constraint("Balanced workload"),
        factory.for_each(Engineer).filter(lambda e: len(e.jobs) > 0).penalize(HardMediumSoftScore.ONE_SOFT, lambda e: int(round(e.schedule()[2] * 100))).as_constraint("Route distance")
    ]


class TimefoldEngineerRouting:
    def __init__(self, scenario: dict[str, Any], provider: OsrmMatrixProvider, matrix_cache: Path | None) -> None:
        self.scenario, self.provider, self.matrix_cache = scenario, provider, matrix_cache

    def build_problem(self) -> RoutingPlan:
        raw_jobs, raw_engineers = self.scenario["jobs"], self.scenario["engineers"]
        ids = set(); jobs = []
        for raw in raw_jobs:
            jid = str(raw["job_id"]).strip()
            if not jid or jid in ids: continue
            ids.add(jid)
            jobs.append(Job(jid, len(jobs), float(raw["duration_min"]), hhmm_to_minutes(raw["window_start"]), hhmm_to_minutes(raw["window_end"]), raw["skill_required"], raw.get("required_vehicle"), raw.get("priority") == "urgent"))
        seen = set(); engineer_raw = []
        for raw in raw_engineers:
            eid = str(raw["engineer_id"]).strip()
            if not eid or eid in seen: continue
            if raw["vehicle_type"] not in {"car", "bicycle", "foot", "public_transport"}: raise ValueError(f"Неизвестный транспорт: {raw['vehicle_type']}")
            seen.add(eid); engineer_raw.append(raw)
        if not jobs or not engineer_raw: raise ValueError("Нужны хотя бы одна заявка и один инженер")
        points = [(float(e["start_lat"]), float(e["start_lon"])) for e in engineer_raw] + [(float(x["lat"]), float(x["lon"])) for x in raw_jobs if str(x["job_id"]).strip() in ids]
        modes = sorted({e["vehicle_type"] for e in engineer_raw}); job_offset = len(engineer_raw); job_points = list(range(job_offset, job_offset + len(jobs)))
        matrices = self._matrices(points, modes, job_points)
        data = RoutingData(points, job_offset, matrices)
        engineers = [Engineer(str(e["engineer_id"]).strip(), e.get("name", str(e["engineer_id"])), i, hhmm_to_minutes(e["shift_start"]), hhmm_to_minutes(e["shift_end"]), set(e["skills"]), e["vehicle_type"], data) for i, e in enumerate(engineer_raw)]
        self._warm_start(engineers, jobs)
        return RoutingPlan(engineers, jobs)

    def _matrices(self, points: list[tuple[float, float]], modes: list[str], job_points: list[int]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        signature = hashlib.sha256(json.dumps({"points": points, "modes": modes, "jobs": job_points, "provider": self.provider.identity}, sort_keys=True).encode()).hexdigest()
        if self.matrix_cache and self.matrix_cache.exists():
            try:
                with np.load(self.matrix_cache, allow_pickle=False) as z:
                    if str(z["signature"].item()) == signature:
                        LOG.info("Матрицы сценария загружены из %s", self.matrix_cache)
                        return {m: (z[f"{m}_d"], z[f"{m}_t"]) for m in modes}
            except (OSError, ValueError, KeyError): pass
        value = {m: self.provider.build(points, m, job_points) for m in modes}
        if self.matrix_cache:
            self.matrix_cache.parent.mkdir(parents=True, exist_ok=True)
            arrays: dict[str, Any] = {"signature": np.array(signature)}
            for m, (d, t) in value.items(): arrays[f"{m}_d"], arrays[f"{m}_t"] = d, t
            np.savez_compressed(self.matrix_cache, **arrays)
        return value

    @staticmethod
    def _warm_start(engineers: list[Engineer], jobs: list[Job]) -> None:
        for job in sorted(jobs, key=lambda j: (not j.is_urgent, j.window_start, j.window_end)):
            candidates = []
            for e in engineers:
                if job.skill_required not in e.skills or (job.required_vehicle and job.required_vehicle != e.vehicle_type): continue
                e.jobs.append(job); late, shift, dist, _ = e.schedule(); e.jobs.pop()
                if late == 0 and shift == 0: candidates.append((len(e.jobs), dist, e))
            if candidates: min(candidates, key=lambda x: (x[0], x[1]))[2].jobs.append(job)

    def solve(self, seconds: int) -> RoutingPlan:
        config = SolverConfig(solution_class=RoutingPlan, entity_class_list=[Engineer], score_director_factory_config=ScoreDirectorFactoryConfig(constraint_provider_function=constraints), termination_config=TerminationConfig(spent_limit=Duration(seconds=seconds)))
        return SolverFactory.create(config).build_solver().solve(self.build_problem())

    def result(self, plan: RoutingPlan) -> dict[str, Any]:
        assigned, routes, total_distance = set(), [], 0.
        for e in plan.engineers:
            if not e.jobs: continue
            _, _, distance, schedule = e.schedule(); total_distance += distance
            for item in schedule: assigned.add(item["job_id"])
            routes.append({"engineer_id": e.engineer_id, "name": e.name, "vehicle_type": e.vehicle_type, "assigned_count": len(schedule), "route_distance_km": round(distance, 2), "route_travel_min": round(sum(x["travel_min"] for x in schedule), 1), "jobs": schedule})
        assignments = {j.job_id: None for j in plan.all_jobs}
        for r in routes:
            for x in r["jobs"]: assignments[x["job_id"]] = r["engineer_id"]
        missing = [{"job_id": j.job_id, "reason": "не назначена: нет совместимой выполнимой позиции в маршрутах"} for j in plan.all_jobs if j.job_id not in assigned]
        return {"scenario": self.scenario.get("scenario", "unknown"), "routing": self.provider.identity, "objective": {"score": str(plan.score), "urgent_unassigned": sum(j.is_urgent for j in plan.all_jobs if j.job_id not in assigned), "unassigned": len(missing), "engineers_used": len(routes), "total_distance_km": round(total_distance, 2)}, "per_engineer": routes, "job_assignments": assignments, "unassigned_jobs": missing, "explanation": "Timefold оптимизирует порядок и распределение заявок. Время и расстояние берутся из предрассчитанных направленных OSRM-матриц; public_transport — статистический московский прокси, а не расписание ОТ."}


def main() -> None:
    p = argparse.ArgumentParser(description="Timefold VRPTW инженеров на ускоренных OSRM-матрицах")
    p.add_argument("scenario", type=Path); p.add_argument("--output", type=Path, default=Path("solution_timefold.json")); p.add_argument("--seconds", type=int, default=20)
    p.add_argument("--osrm-block-size", type=int, default=50); p.add_argument("--osrm-pair-cache", type=Path, default=Path("osrm_pair_cache.sqlite")); p.add_argument("--matrix-cache", type=Path, default=Path("route_matrix_cache.npz")); p.add_argument("--no-matrix-cache", action="store_true")
    p.add_argument("--osrm-max-air-distance-km", type=float); p.add_argument("--osrm-pt-wait-min", type=float, default=0.0); p.add_argument("--quiet", action="store_true")
    a = p.parse_args(); logging.basicConfig(level=logging.WARNING if a.quiet else logging.INFO, format="%(levelname)s: %(message)s")
    with a.scenario.open(encoding="utf-8-sig") as f: scenario = json.load(f)
    provider = OsrmMatrixProvider(block_size=a.osrm_block_size, pair_cache=a.osrm_pair_cache, max_air_distance_km=a.osrm_max_air_distance_km, pt_wait_min=a.osrm_pt_wait_min)
    try:
        routing = TimefoldEngineerRouting(scenario, provider, None if a.no_matrix_cache else a.matrix_cache)
        result = routing.result(routing.solve(a.seconds))
        a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result["objective"], ensure_ascii=False, indent=2))
    finally:
        provider.close()


if __name__ == "__main__":
    main()
