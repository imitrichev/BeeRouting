"""Постоянный кэш исходных OSRM-матриц: секунды и метры до конвертации."""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Callable
from zipfile import BadZipFile

import numpy as np


def load_table(
    points: list[tuple[float, float]],
    identity: str,
    pair_path: Path | None,
    matrix_directory: Path | None,
    fetch: Callable[[list[int], list[int]], tuple[list, list]],
) -> tuple[list, list]:
    """Читает NPZ, собирает SQLite-пары и запрашивает отсутствующие строки.

    identity включает endpoint и профиль графа. Здесь хранятся сырые данные:
    коэффициент общественного транспорта применяется вызывающим provider
    после чтения, поэтому автомобильные пары можно безопасно переиспользовать.
    """
    signature = hashlib.sha256(
        json.dumps([identity, points], separators=(",", ":")).encode()
    ).hexdigest()
    path = Path(matrix_directory) / f"{signature}.npz" if matrix_directory else None
    size = len(points)
    if path is not None and path.exists():
        try:
            with np.load(path, allow_pickle=False) as data:
                durations, distances = data["durations"], data["distances"]
                if (
                    str(data["signature"].item()) == signature
                    and durations.shape == distances.shape == (size, size)
                    and np.isfinite(durations).all() and np.isfinite(distances).all()
                    and (durations >= 0).all() and (distances >= 0).all()
                ):
                    return durations.tolist(), distances.tolist()
        except (OSError, ValueError, KeyError, EOFError, BadZipFile):
            pass  # Повреждённый архив восстанавливается из SQLite или OSRM.

    keys = [json.dumps(point, separators=(",", ":")) for point in points]
    durations = np.full((size, size), np.nan)
    distances = np.full((size, size), np.nan)
    if pair_path is not None:
        Path(pair_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(pair_path)) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS osrm_pairs_v1 (
                graph TEXT, origin TEXT, destination TEXT,
                seconds REAL NOT NULL, meters REAL NOT NULL,
                PRIMARY KEY (graph, origin, destination))""")
            # Один SELECT на исходную точку вместо запроса на каждую пару.
            for i, origin in enumerate(keys):
                rows = dict((dst, (sec, meters)) for dst, sec, meters in db.execute(
                    "SELECT destination, seconds, meters FROM osrm_pairs_v1 WHERE graph=? AND origin=?",
                    (identity, origin),
                ))
                for j, destination in enumerate(keys):
                    if destination in rows:
                        durations[i, j], distances[i, j] = rows[destination]

    missing = ~np.isfinite(durations) | ~np.isfinite(distances)
    sources = np.flatnonzero(missing.any(axis=1)).tolist()
    destinations = np.flatnonzero(missing.any(axis=0)).tolist()
    if sources:
        raw_time, raw_distance = fetch(sources, destinations)
        times = np.asarray(raw_time, dtype=float)
        lengths = np.asarray(raw_distance, dtype=float)
        shape = (len(sources), len(destinations))
        if (
            times.shape != shape or lengths.shape != shape
            or not np.isfinite(times).all() or not np.isfinite(lengths).all()
            or (times < 0).any() or (lengths < 0).any()
        ):
            raise ValueError("OSRM вернул неполную или некорректную матрицу маршрутов")
        rows = []
        for i, source in enumerate(sources):
            for j, destination in enumerate(destinations):
                # Известные пары сохраняем: новый запрос дополняет снимок.
                if missing[source, destination]:
                    seconds, meters = float(times[i, j]), float(lengths[i, j])
                    durations[source, destination] = seconds
                    distances[source, destination] = meters
                    rows.append((identity, keys[source], keys[destination], seconds, meters))
        if pair_path is not None:
            with closing(sqlite3.connect(pair_path)) as db, db:
                db.executemany("INSERT OR REPLACE INTO osrm_pairs_v1 VALUES (?, ?, ?, ?, ?)", rows)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Уникальный временный файл и атомарная замена защищают читателей
        # от частично записанного ZIP при параллельных запусках.
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            try:
                np.savez_compressed(output, signature=signature, durations=durations, distances=distances)
                output.close()
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    return durations.tolist(), distances.tolist()
