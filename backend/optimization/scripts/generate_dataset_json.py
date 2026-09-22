"""Генерация JSON-сценария только из исходных CSV-файлов.

Источники данных разделены:

* ``Югоцентр Синтетические данные.csv`` — заявки, окна, адреса и типы работ;
* ``engineers.csv`` — состав инженеров, навыки, транспорт, смены и адреса старта;
* необязательный контрольный CSV — ручное распределение заявок;
Готовый JSON-сценарий не является источником генерации. Если адреса нет в
``nominatim_cache.json`` — постоянный локальный кэш координат домов.
Если адреса нет в кэше, используется Nominatim. Квартирная часть адреса
удаляется до поиска, поэтому координаты определяются на уровне дома.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict, deque
from datetime import datetime
import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROAD_MINUTES = 20

# В JSON duration_min хранится только работа после прибытия. Нормативные
# 20 минут дороги отдельно моделируются routing matrix.
TIME_NORMS: dict[str, dict[str, int | str]] = {
    "connection": {"name": "Подключение клиентов Базовая", "road_to_client_min": 20, "technical_work_min": 60, "documents_min": 10, "base_norm_min": 90},
    "emergency": {"name": "Авария на ТКД", "road_to_client_min": 20, "technical_work_min": 80, "documents_min": 0, "base_norm_min": 100},
    "equipment_order": {"name": "Дозаказ оборудования", "road_to_client_min": 20, "technical_work_min": 10, "documents_min": 10, "base_norm_min": 40},
    "local": {"name": "Локальная заявка/ремонт у клиента", "road_to_client_min": 20, "technical_work_min": 30, "documents_min": 0, "base_norm_min": 50},
}

SKILL_NAMES_RU = {
    "emergency_works": "Аварийные работы",
    "local_works": "Локальные работы",
    "connection_orders": "Работы на подключение и дозаказы",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Читает CSV в UTF-8 или Windows-1251 с разделителем ``;`` или ``,``."""
    last_error: UnicodeError | None = None
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            with path.open(encoding=encoding, newline="") as csv_file:
                sample = csv_file.read(4096)
                csv_file.seek(0)
                try:
                    delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
                except csv.Error:
                    delimiter = ";"
                return list(csv.DictReader(csv_file, delimiter=delimiter))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Не удалось прочитать {path}: неизвестная кодировка") from last_error


def _request_rows(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Оставляет только строки, содержащие числовой номер заявки."""
    return [dict(row) for row in rows if (row.get("Заявка") or "").strip().isdigit()]


def _replace_building_marker(value: str) -> str:
    """Заменяет российские обозначения строения на обозначение корпуса.

    Замена выполняется только после цифры дома и перед номером строения,
    поэтому обычная буква «с» внутри названия улицы не изменяется.
    """
    value = re.sub(
        r"(?<=\d)\s*с\.?\s*(?=\d)",
        " к ",
        value,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"\s+(?:стр\.?|строение)\s*(?=\d)",
        " к ",
        value,
        flags=re.IGNORECASE,
    )


def _normalise_address(value: str) -> str:
    """Строит ключ дома, удаляя квартиру и различия в пробелах.

    Поэтому ``д. 9, кв. 47`` и ``д. 9`` сопоставляются с одной точкой дома.
    """
    value = value.lower().replace("ё", "е")
    # Маркер квартиры должен быть отдельным словом. Иначе последовательность
    # «кв» внутри слова «Москва» ошибочно удаляет оставшуюся часть адреса.
    value = re.sub(
        r"(?:,\s*|\s+)\b(?:кв\.?|квартира|апартамент(?:ы)?|apt\.?)\s*[^,;]*$",
        "",
        value,
    )
    return re.sub(r"\s+", " ", value).strip(" ,")


def _match_rows(
    source_rows: list[dict[str, str]],
    target_rows: list[dict[str, Any]],
    source_name: str,
    target_name: str,
) -> list[dict[str, Any] | None]:
    """Сопоставляет строки по адресу, сохраняя порядок повторяющихся адресов."""
    target_by_address: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for row in target_rows:
        target_by_address[_normalise_address(str(row.get("Адрес", row.get("address", ""))))].append(row)
    matched: list[dict[str, Any] | None] = []
    for source in source_rows:
        key = _normalise_address(source.get("Адрес", ""))
        candidates = target_by_address.get(key)
        if not candidates:
            raise ValueError(f"Строка заявки {source.get('Заявка')!r} из {source_name} не найдена в {target_name} по адресу {source.get('Адрес')!r}")
        matched.append(candidates.popleft())
    leftovers = [row for rows in target_by_address.values() for row in rows]
    if leftovers:
        raise ValueError(f"В {target_name} остались строки, которым нет пары в {source_name}: {len(leftovers)}")
    return matched


def _time(value: str) -> str:
    """Преобразует дату и время CSV в доменный формат HH:MM."""
    return datetime.strptime(value.strip(), "%d.%m.%Y %H:%M").strftime("%H:%M")


def _work_kind(request_type_bk: str) -> str:
    """Определяет код норматива по типу заявки BK."""
    value = request_type_bk.strip().lower()
    if "подключ" in value:
        return "connection"
    if "глобальн" in value or "авар" in value:
        return "emergency"
    if "дозаказ" in value:
        return "equipment_order"
    if "локальн" in value or "ремонт" in value:
        return "local"
    raise ValueError(f"Неизвестный тип работы BK: {request_type_bk!r}")


def _skill_for_kind(kind: str) -> tuple[str, str]:
    """Возвращает фиксированный код навыка и его русское название."""
    if kind == "emergency":
        return "emergency_works", "Аварийные работы"
    if kind == "local":
        return "local_works", "Локальные работы"
    return "connection_orders", "Работы на подключение и дозаказы"


def _find_control_path(path: Path | None, synthetic_path: Path | None = None) -> Path | None:
    """Находит контрольный CSV для того же района, что и синтетические данные.

    Имя района берётся из ``<район> Синтетические данные.csv``. Поэтому при
    добавлении второго или третьего датасета контрольные файлы не смешаются
    между собой.
    """
    if path is not None:
        return path if path.exists() else None
    if synthetic_path is None:
        pattern = "Югоцентр Контрольное распределение*.csv"
    else:
        prefix = re.sub(r"\s+Синтетические данные(?:\.csv)?$", "", synthetic_path.stem)
        pattern = f"{prefix} Контрольное распределение*.csv"
    candidates = sorted(synthetic_path.parent.glob(pattern) if synthetic_path else Path.cwd().glob(pattern))
    return candidates[0] if candidates else None


def _first_value(row: Mapping[str, str], *names: str) -> str:
    """Возвращает первое непустое значение среди вариантов имени колонки."""
    for name in names:
        value = row.get(name)
        if value is not None and value.strip():
            return value.strip()
    return ""


class NominatimGeocoder:
    """Геокодер Nominatim с ограничением частоты и локальным JSON-кэшем."""

    def __init__(
        self,
        cache_path: Path = Path("nominatim_cache.json"),
        endpoint: str = "https://nominatim.openstreetmap.org/search",
        user_agent: str = "BeeRouting-dataset-import/1.0",
        email: str | None = None,
        min_interval_seconds: float = 1.0,
    ) -> None:
        self.cache_path = cache_path
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.email = email
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
            self._cache: dict[str, tuple[float, float]] = {
                str(key): (float(value[0]), float(value[1]))
                for key, value in loaded.items()
            }
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            self._cache = {}

    def __call__(self, address: str) -> tuple[float, float]:
        """Возвращает координаты дома или сообщает, что Nominatim его не нашёл."""
        key = _normalise_address(address)
        if key in self._cache:
            return self._cache[key]
        fallback_address = _replace_building_marker(address)
        fallback_key = _normalise_address(fallback_address)
        original_query_addresses = list(self._query_variants(address))
        query_addresses = list(original_query_addresses)
        # Сначала всегда проверяется исходная форма. Форма с «к» разрешена
        # только как второй поиск после полного отсутствия результата.
        if fallback_address != address:
            query_addresses.extend(self._query_variants(fallback_address))
        for query_index, query_address in enumerate(dict.fromkeys(query_addresses)):
            # Старые версии генератора могли сохранить координаты под
            # заменённой формой «к». Используем её только после того, как
            # исходная форма не дала результата.
            if (
                query_index == len(original_query_addresses)
                and fallback_key != key
                and fallback_key in self._cache
            ):
                return self._cache[fallback_key]
            wait_seconds = self.min_interval_seconds - (time.monotonic() - self._last_request_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            query = {
                "q": query_address,
                "format": "jsonv2",
                "limit": "1",
                "addressdetails": "0",
            }
            if self.email:
                query["email"] = self.email
            request = Request(
                f"{self.endpoint}?{urlencode(query)}",
                headers={"User-Agent": self.user_agent, "Accept-Language": "ru"},
            )
            self._last_request_at = time.monotonic()
            try:
                with urlopen(request, timeout=30) as response:  # noqa: S310: endpoint задаётся конфигурацией
                    results = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 429:
                    # Публичный Nominatim временно ограничивает частоту
                    # запросов. Уважаем Retry-After; без него ждём минуту и
                    # повторяем тот же вариант адреса один раз.
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        wait_seconds = float(retry_after) if retry_after else 60.0
                    except (TypeError, ValueError):
                        wait_seconds = 60.0
                    time.sleep(max(wait_seconds, 60.0))
                    self._last_request_at = 0.0
                    try:
                        with urlopen(request, timeout=30) as response:  # noqa: S310: endpoint задаётся конфигурацией
                            results = json.loads(response.read().decode("utf-8"))
                    except HTTPError as retry_exc:
                        raise ValueError(
                            f"Nominatim вернул HTTP {retry_exc.code} для адреса {address!r} после повторной попытки"
                        ) from retry_exc
                    except URLError as retry_exc:
                        raise ValueError(
                            f"Не удалось обратиться к Nominatim для адреса {address!r} после повторной попытки"
                        ) from retry_exc
                else:
                    raise ValueError(f"Nominatim вернул HTTP {exc.code} для адреса {address!r}") from exc
            except URLError as exc:
                raise ValueError(f"Не удалось обратиться к Nominatim для адреса {address!r}") from exc
            if not results:
                continue
            coordinates = (float(results[0]["lat"]), float(results[0]["lon"]))
            self._cache[key] = coordinates
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return coordinates
        raise ValueError(f"Nominatim не нашёл адрес дома: {address!r}")

    @staticmethod
    def _query_variants(address: str) -> tuple[str, ...]:
        """Строит несколько безопасных вариантов запроса одного дома.

        CSV-источники используют русские сокращения и разный порядок слов:
        например, ``проезд Симферопольский, д.7`` и ``Симферопольский
        проезд, 7``. Это не новые адреса и не дополнительные источники данных,
        а варианты записи одного ключа для поиска в Nominatim.
        """
        normalized = _normalise_address(address)
        variants: list[str] = [normalized]
        without_city = re.sub(
            r"^(?:г\.\s*|город\s+)москва\s*,?\s*",
            "",
            normalized,
        )
        street_types = {
            "ул": "улица",
            "улица": "улица",
            "проезд": "проезд",
            "пр-кт": "проспект",
            "проспект": "проспект",
            "пер": "переулок",
            "переулок": "переулок",
            "наб": "набережная",
            "набережная": "набережная",
            "б-р": "бульвар",
            "бульвар": "бульвар",
        }
        without_city = re.sub(
            r"\b(ул|улица|проезд|пр-кт|проспект|пер|переулок|наб|набережная|б-р|бульвар)\.",
            r"\1 ",
            without_city,
        )
        without_city = re.sub(r"\s+", " ", without_city).strip(" ,")
        variants.append(f"Москва, {without_city}")
        house_match = re.match(r"^(.+?),\s*д\.?\s*(.+)$", without_city)
        if house_match:
            street, house = house_match.groups()
            type_match = re.match(
                r"^(ул|улица|проезд|пр-кт|проспект|пер|переулок|наб|набережная|б-р|бульвар)\s+(.+)$",
                street,
            )
            if type_match:
                street_type, street_name = type_match.groups()
                variants.append(
                    f"Москва, {street_name} {street_types[street_type]}, {house}"
                )
        # Nominatim часто лучше понимает короткую запись без служебных
        # сокращений и знаков препинания: «Москва 60-летия Октября 18 к 2».
        compact = re.sub(
            r"\b(?:ул|улица|проезд|пр-кт|проспект|пер|переулок|наб|набережная|б-р|бульвар|д|дом)\.?\b",
            " ",
            without_city,
        )
        compact = re.sub(r"[,.;]", " ", compact)
        compact = re.sub(r"\s+", " ", compact).strip()
        if compact:
            variants.append(f"Москва {compact}")
        # Для российского адресного формата дополнительно пробуем вариант
        # с точкой после сокращения: «к. 2». Развёрнутая форма намеренно
        # не используется.
        for variant in tuple(variants):
            dotted_corpus = re.sub(r"\s+к\.?\s*(?=\d)", " к. ", variant)
            variants.append(dotted_corpus)
        return tuple(dict.fromkeys(variants))


def _resolve_coordinates(
    address: str,
    geocoder: Callable[[str], tuple[float, float]],
) -> tuple[float, float]:
    """Возвращает координаты через кэш Nominatim или новый запрос.

    Сам callable-geocoder отвечает за чтение и запись постоянного кэша.
    Передаём ему исходный адрес: ``NominatimGeocoder`` нормализует его перед
    формированием запроса, а тестовый geocoder может проверить этот контракт.
    """
    return geocoder(address)


def _office_address(rows: Iterable[Mapping[str, str]]) -> str:
    """Извлекает адрес офиса из специальной строки синтетического CSV."""
    for row in rows:
        if "адрес офиса" in (row.get("Заявка") or "").strip().lower():
            address = _first_value(row, "Тип заявки BK", "Адрес")
            if address:
                return address
    raise ValueError("В синтетическом CSV не найдена строка с адресом офиса")


def _territory_metadata(path: Path) -> tuple[str, str, str]:
    """Возвращает коды сценария для имени района в синтетическом CSV."""
    territory_name = re.sub(
        r"\s+Синтетические данные(?:\.csv)?$", "", path.stem
    ).strip()
    metadata = {
        "Югоцентр": ("yugo_tsentr", "Юго-центр", "yugo_tsentr_day"),
        "Юго-восток": ("yugo_vostok", "Юго-восток", "yugo_vostok_day"),
        "Восток": ("vostok", "Восток", "vostok_day"),
    }
    try:
        return metadata[territory_name]
    except KeyError as exc:
        raise ValueError(
            f"Неизвестный район в имени файла {path.name!r}. "
            "Ожидается Югоцентр, Юго-восток или Восток."
        ) from exc


def _engineers_from_csv(
    path: Path,
    geocoder: Callable[[str], tuple[float, float]],
) -> list[dict[str, Any]]:
    """Читает инженеров только из engineers.csv.

    У инженера может быть start_address; при его наличии координаты тоже
    ищутся через кэш Nominatim или новый запрос. Иначе используются
    координаты из CSV, а при их отсутствии — точка офиса.
    """
    rows = _read_csv(path)
    vehicle_codes = {
        "автомобиль": "car", "car": "car", "пешком": "foot", "walk": "foot",
        "велосипед": "bicycle", "bicycle": "bicycle",
        "общественный транспорт": "public_transport", "public_transport": "public_transport",
    }
    engineers: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        name = _first_value(row, "name", "ФИО", "Фамилия Имя", "Инженер", "Бригада")
        if not name:
            continue
        start_address = _first_value(row, "start_address", "Адрес старта", "Адрес офиса")
        if not start_address:
            raise ValueError(
                f"Для инженера {name!r} в {path} не задан start_address"
            )
        # Координаты не читаются из engineers.csv. Даже если один и тот же
        # офис встречается у нескольких инженеров, его точка определяется
        # через общий Nominatim-кэш.
        start_lat, start_lon = _resolve_coordinates(start_address, geocoder)
        raw_skills = re.split(r"[,|;/]+", _first_value(row, "skills", "Навыки", "Квалификации"))
        raw_vehicle = _first_value(row, "vehicle_type", "Транспорт", "Тип транспорта").lower()
        skills = [skill.strip() for skill in raw_skills if skill.strip()]
        engineers.append(
            {
                "engineer_id": _first_value(row, "engineer_id", "ID", "Идентификатор", "Табельный номер") or f"engineer-{index}",
                "name": name,
                "start_lat": start_lat,
                "start_lon": start_lon,
                "shift_start": _first_value(row, "shift_start", "Начало смены") or "09:00",
                "shift_end": _first_value(row, "shift_end", "Конец смены") or "22:00",
                "skills": skills,
                "skills_ru": [SKILL_NAMES_RU.get(skill, skill) for skill in skills],
                "vehicle_type": vehicle_codes.get(raw_vehicle, raw_vehicle),
            }
        )
    if not engineers:
        raise ValueError(f"В {path} не найдено ни одного инженера")
    return engineers


def generate_dataset(
    synthetic_path: Path,
    output_path: Path,
    control_path: Path | None = None,
    engineers_path: Path = Path("engineers.csv"),
    geocoder: Callable[[str], tuple[float, float]] | None = None,
    office_address: str | None = None,
) -> dict[str, Any]:
    """Создаёт JSON только из CSV и возвращает его содержимое.

    ``geocoder`` удобен для тестов и позволяет подключить другой сервис. В
    обычном запуске используется Nominatim с постоянным кэшем
    ``nominatim_cache.json``.
    """
    all_synthetic_rows = _read_csv(synthetic_path)
    synthetic_rows = _request_rows(all_synthetic_rows)
    if not synthetic_rows:
        raise ValueError(f"В {synthetic_path} нет заявок")
    control_path = _find_control_path(control_path, synthetic_path)
    control_rows = _request_rows(_read_csv(control_path)) if control_path else []
    control_matches = (
        _match_rows(synthetic_rows, control_rows, synthetic_path.name, control_path.name)
        if control_rows else [None] * len(synthetic_rows)
    )
    if not engineers_path.exists():
        raise ValueError(f"Не найден обязательный справочник инженеров: {engineers_path}")

    geocode = geocoder or NominatimGeocoder()
    office = office_address or _office_address(all_synthetic_rows)
    office_lat, office_lon = _resolve_coordinates(office, geocode)
    office_point = {"lat": office_lat, "lon": office_lon, "address": office}
    engineers = _engineers_from_csv(engineers_path, geocode)

    jobs: list[dict[str, Any]] = []
    territory_code, territory_name, scenario_name = _territory_metadata(synthetic_path)
    for synthetic, control in zip(synthetic_rows, control_matches):
        request_id = synthetic["Заявка"].strip()
        kind = _work_kind(synthetic["Тип заявки BK"])
        norm = TIME_NORMS[kind]
        skill, skill_ru = _skill_for_kind(kind)
        address = synthetic["Адрес"].strip()
        latitude, longitude = _resolve_coordinates(address, geocode)
        jobs.append(
            {
                "job_id": f"{territory_code}-J{request_id}",
                "territory_code": territory_code,
                "territory_name": territory_name,
                "request_id": int(request_id),
                "control_request_id": int(control["Заявка"]) if control else None,
                "skill_required": skill,
                "skill_required_ru": skill_ru,
                "request_type_bk": synthetic["Тип заявки BK"],
                "request_type_hd": synthetic["Тип заявки HD"],
                "district": synthetic["Район"],
                "address": address,
                "lat": latitude,
                "lon": longitude,
                "window_start": _time(synthetic["Начало"]),
                "window_end": _time(synthetic["Окончание"]),
                "duration_min": int(norm["base_norm_min"]) - ROAD_MINUTES,
                "time_norm_code": kind,
                "priority": "normal",
                "required_vehicle": None,
                "reference_status": (control or {}).get("Статус BK", "Отправлена"),
                "reference_crew": (control or {}).get("Бригада", ""),
                "gigabit": synthetic.get("Гигабитное подключение", "").strip().lower() == "да",
            }
        )

    result: dict[str, Any] = {
        "schema_version": "1.0",
        "scenario": scenario_name,
        "territory_code": territory_code,
        "territory_name": territory_name,
        "units": {"time": "HH:MM", "duration": "minutes", "distance": "km", "coordinates": "lat/lon (WGS84)"},
        "office_start_point": office_point,
        "engineers": engineers,
        "jobs": jobs,
        "time_norms": list(TIME_NORMS.values()),
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def compare_with_json(generated: Mapping[str, Any], comparison_path: Path) -> dict[str, Any]:
    """Сравнивает новый JSON со старым по адресам и возвращает сводку.

    Изменения номера заявки и длительности ожидаемы: номер берётся из
    синтетического CSV, а длительность — из новых нормативов.
    """
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    old_jobs = _match_rows(
        [{"Заявка": str(job.get("request_id", "")), "Адрес": job.get("address", "")} for job in generated.get("jobs", ())],
        list(comparison.get("jobs", ())),
        "сгенерированный JSON",
        comparison_path.name,
    )
    ignored = {"job_id", "request_id", "control_request_id", "duration_min", "time_norm_code"}
    duration_changes = 0
    identifier_changes = 0
    other_changes: dict[str, int] = defaultdict(int)
    samples: list[dict[str, Any]] = []
    for new_job, old_job in zip(generated.get("jobs", ()), old_jobs):
        if new_job.get("duration_min") != old_job.get("duration_min"):
            duration_changes += 1
            if len(samples) < 5:
                samples.append({"address": new_job.get("address"), "old": old_job.get("duration_min"), "new": new_job.get("duration_min")})
        if new_job.get("job_id") != old_job.get("job_id"):
            identifier_changes += 1
        for field_name, old_value in old_job.items():
            if field_name not in ignored and new_job.get(field_name) != old_value:
                other_changes[field_name] += 1
    return {"duration_changes": duration_changes, "identifier_changes": identifier_changes, "other_changes": dict(other_changes), "duration_samples": samples}


def main() -> None:
    """Запускает генерацию из аргументов командной строки."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", type=Path, default=Path("Югоцентр Синтетические данные.csv"))
    parser.add_argument("--control", type=Path, default=None)
    parser.add_argument("--engineers", type=Path, default=Path("engineers.csv"))
    parser.add_argument("--nominatim-cache", type=Path, default=Path("nominatim_cache.json"))
    parser.add_argument("--nominatim-email", default=None)
    parser.add_argument("--office-address", default=None)
    parser.add_argument("--output", type=Path, default=Path("Югоцентр.json"))
    parser.add_argument("--compare-json", type=Path, default=Path("yugo_center.json"))
    args = parser.parse_args()
    print(f"Источник инженеров: {args.engineers}")
    geocoder = NominatimGeocoder(cache_path=args.nominatim_cache, email=args.nominatim_email)
    result = generate_dataset(args.synthetic, args.output, args.control, args.engineers, geocoder, args.office_address)
    print(f"Создан {args.output}: {len(result['engineers'])} инженеров, {len(result['jobs'])} заявок")
    print("Источники: синтетические данные + engineers.csv" + (" + контрольное распределение" if args.control or _find_control_path(args.control, args.synthetic) else ""))
    print("Координаты: nominatim_cache.json, отсутствующие адреса — Nominatim; квартиры удаляются до поиска")
    print("Нормативы после прибытия: Подключение 70, авария 80, дозаказ 20, локальная заявка 30 минут")
    if args.compare_json.exists():
        report = compare_with_json(result, args.compare_json)
        print(f"Сравнение с {args.compare_json} по совпадающим адресам:")
        print(f"  изменено длительностей: {report['duration_changes']} (ожидаемо по новым нормативам)")
        print(f"  изменено идентификаторов: {report['identifier_changes']} (номер берётся из синтетического CSV)")
        print(f"  изменения других полей: {report['other_changes'] or 'нет'}")
        if report["duration_samples"]:
            print("  примеры изменения длительности:")
            for sample in report["duration_samples"]:
                print(f"    {sample['address']}: {sample['old']} -> {sample['new']} мин")


if __name__ == "__main__":
    main()
