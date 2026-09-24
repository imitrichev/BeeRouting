"""
Management-команда для загрузки датасетов диспетчеризации бригад
(формат Iugotsentr.json) в модели Django.

Расположение: <app>/management/commands/load_dispatch_dataset.py
(не забудьте создать пустые __init__.py в management/ и
management/commands/).

Использование:
    python manage.py load_dispatch_dataset path/to/Iugotsentr.json
    python manage.py load_dispatch_dataset path/to/*.json --dry-run
    python manage.py load_dispatch_dataset data.json --flush-territory
"""

import json
import re
from datetime import datetime
from glob import glob

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import (
    Territory,
    District,
    Skill,
    VehicleType,
    Priority,
    TimeNorm,
    Engineer,
    Job,
    RescheduleEvent,
)
from ...services import rebuild_after_crud


def parse_time(value):
    """'HH:MM' -> datetime.time. Пустые/None значения возвращают None."""
    if not value:
        return None
    return datetime.strptime(value, "%H:%M").time()


class Command(BaseCommand):
    help = "Загружает датасет диспетчеризации (формат Iugotsentr.json) в БД."

    def add_arguments(self, parser):
        parser.add_argument(
            "files", nargs="+",
            help="Один или несколько путей/масок к JSON-файлам датасета",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Разобрать и провалидировать файл(ы) без записи в БД",
        )
        parser.add_argument(
            "--flush-territory", action="store_true",
            help="Перед загрузкой удалить существующие Job/RescheduleEvent "
                 "по данной территории (полезно при перезагрузке того же дня)",
        )

    def handle(self, *args, **options):
        paths = []
        for pattern in options["files"]:
            matched = sorted(glob(pattern))
            if not matched:
                raise CommandError(f"Файлы не найдены по маске: {pattern}")
            paths.extend(matched)

        for path in paths:
            self.stdout.write(f"Обработка файла: {path}")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            if options["dry_run"]:
                self._validate(data)
                self.stdout.write(self.style.SUCCESS(f"OK (dry-run): {path}"))
                continue

            with transaction.atomic():
                territory = self._load(
                    data, flush_territory=options["flush_territory"]
                )
                # ORM-загрузка коллеги остаётся источником справочников и
                # сущностей. После неё формируем тот же persistent snapshot,
                # который используют optimization/replanning endpoints.
                rebuild_after_crud(territory)

            self.stdout.write(self.style.SUCCESS(f"Загружено: {path}"))

    # ------------------------------------------------------------------
    # Валидация (для --dry-run)
    # ------------------------------------------------------------------

    def _validate(self, data):
        required_top = ["territory_code", "territory_name", "engineers", "jobs"]
        missing = [k for k in required_top if k not in data]
        if missing:
            raise CommandError(f"В датасете отсутствуют ключи: {missing}")
        if not isinstance(data["engineers"], list) or not data["engineers"]:
            raise CommandError("Список 'engineers' пуст или некорректен")
        if not isinstance(data["jobs"], list) or not data["jobs"]:
            raise CommandError("Список 'jobs' пуст или некорректен")

    # ------------------------------------------------------------------
    # Основная загрузка
    # ------------------------------------------------------------------

    def _load(self, data, flush_territory=False):
        territory = self._load_territory(data)

        if flush_territory:
            RescheduleEvent.objects.filter(territory=territory).delete()
            Job.objects.filter(territory=territory).delete()
            self.stdout.write(f"  Очищены Job/RescheduleEvent для {territory}")

        skills_map = self._load_skills(data)
        vehicles_map = self._load_vehicle_types(data)
        priorities_map = self._load_priorities(data)
        time_norms_map = self._load_time_norms(data)

        districts_map = {}  # name -> District
        engineers_map = {}  # engineer_id -> Engineer
        engineers_by_name = {}  # name -> Engineer

        self._load_engineers(
            data, territory, skills_map, vehicles_map,
            engineers_map, engineers_by_name,
        )

        jobs_map = {}  # job_id -> Job
        self._load_jobs(
            data, territory, skills_map, priorities_map, vehicles_map,
            time_norms_map, districts_map, engineers_by_name, jobs_map,
        )

        self._load_reschedule_events(
            data, territory, skills_map, priorities_map, vehicles_map,
            time_norms_map, districts_map, engineers_map, jobs_map,
        )
        return territory

    # ------------------------------------------------------------------
    # Справочники
    # ------------------------------------------------------------------

    def _load_territory(self, data):
        office = data.get("office_start_point") or {}
        territory, _ = Territory.objects.update_or_create(
            code=data["territory_code"],
            defaults={
                "name": data["territory_name"],
                "office_lat": office.get("lat"),
                "office_lon": office.get("lon"),
                "office_address": office.get("address", ""),
                "source_payload": data,
            },
        )
        return territory

    def _load_skills(self, data):
        result = {}
        for item in data.get("dictionaries", {}).get("skills", []):
            skill, _ = Skill.objects.update_or_create(
                code=item["code"], defaults={"name": item["name"]},
            )
            result[skill.code] = skill
        return result

    def _load_vehicle_types(self, data):
        result = {}
        for item in data.get("dictionaries", {}).get("vehicle_types", []):
            vt, _ = VehicleType.objects.update_or_create(
                code=item["code"], defaults={"name": item["name"]},
            )
            result[vt.code] = vt
        return result

    def _load_priorities(self, data):
        result = {}
        for item in data.get("dictionaries", {}).get("priorities", []):
            pr, _ = Priority.objects.update_or_create(
                code=item["code"], defaults={"name": item["name"]},
            )
            result[pr.code] = pr
        return result

    def _load_time_norms(self, data):
        """Сопоставляем нормативы time_norms с job.time_norm_code
        по эвристике ключевых слов в названии норматива."""
        code_by_keyword = [
            ("авари", TimeNorm.CODE_EMERGENCY),
            ("дозаказ", TimeNorm.CODE_EQUIPMENT_ORDER),
            ("локальн", TimeNorm.CODE_LOCAL),
            ("подключ", TimeNorm.CODE_CONNECTION),
        ]
        result = {}
        for item in data.get("time_norms", []):
            code = None
            name_lower = item["name"].lower()
            for keyword, mapped_code in code_by_keyword:
                if keyword in name_lower:
                    code = mapped_code
                    break
            norm, _ = TimeNorm.objects.update_or_create(
                name=item["name"],
                defaults={
                    "code": code,
                    "road_to_client_min": item["road_to_client_min"],
                    "technical_work_min": item["technical_work_min"],
                    "documents_min": item["documents_min"],
                    "base_norm_min": item["base_norm_min"],
                },
            )
            if code:
                result[code] = norm
        return result

    def _get_district(self, territory, name, cache):
        if name in cache:
            return cache[name]
        district, _ = District.objects.get_or_create(
            territory=territory, name=name,
        )
        cache[name] = district
        return district

    # ------------------------------------------------------------------
    # Инженеры
    # ------------------------------------------------------------------

    def _load_engineers(
        self, data, territory, skills_map, vehicles_map,
        engineers_map, engineers_by_name,
    ):
        for item in data.get("engineers", []):
            vehicle = vehicles_map.get(item["vehicle_type"])
            if vehicle is None:
                vehicle, _ = VehicleType.objects.get_or_create(
                    code=item["vehicle_type"],
                    defaults={"name": item["vehicle_type"]},
                )
                vehicles_map[vehicle.code] = vehicle

            engineer, _ = Engineer.objects.update_or_create(
                engineer_id=item["engineer_id"],
                defaults={
                    "territory": territory,
                    "name": item["name"],
                    "start_lat": item["start_lat"],
                    "start_lon": item["start_lon"],
                    "shift_start": parse_time(item["shift_start"]),
                    "shift_end": parse_time(item["shift_end"]),
                    "vehicle_type": vehicle,
                    "start_address": item.get("start_address", ""),
                    "available_equipment": item.get("available_equipment", []),
                },
            )

            skill_objs = []
            for code in item.get("skills", []):
                skill = skills_map.get(code)
                if skill is None:
                    skill, _ = Skill.objects.get_or_create(
                        code=code, defaults={"name": code},
                    )
                    skills_map[code] = skill
                skill_objs.append(skill)
            engineer.skills.set(skill_objs)

            engineers_map[engineer.engineer_id] = engineer
            engineers_by_name[engineer.name] = engineer

    # ------------------------------------------------------------------
    # Заявки
    # ------------------------------------------------------------------

    def _build_job_defaults(
        self, territory, item, skills_map, priorities_map, vehicles_map,
        time_norms_map, districts_map, engineers_by_name,
    ):
        skill = skills_map.get(item["skill_required"])
        if skill is None:
            skill, _ = Skill.objects.get_or_create(
                code=item["skill_required"],
                defaults={"name": item.get("skill_required_ru", item["skill_required"])},
            )
            skills_map[skill.code] = skill

        priority = priorities_map.get(item.get("priority", "normal"))
        if priority is None:
            code = item.get("priority", "normal")
            priority, _ = Priority.objects.get_or_create(
                code=code, defaults={"name": code},
            )
            priorities_map[priority.code] = priority

        required_vehicle = None
        if item.get("required_vehicle"):
            required_vehicle = vehicles_map.get(item["required_vehicle"])

        time_norm = time_norms_map.get(item.get("time_norm_code"))

        district = self._get_district(territory, item["district"], districts_map)

        reference_engineer = None
        crew_name = item.get("reference_crew")
        if crew_name:
            reference_engineer = engineers_by_name.get(crew_name)

        current_engineer = None
        if item.get("current_engineer_id"):
            current_engineer = Engineer.objects.filter(
                territory=territory,
                engineer_id=item["current_engineer_id"],
            ).first()

        return {
            "territory": territory,
            "request_id": item["request_id"],
            "control_request_id": item.get("control_request_id"),
            "skill_required": skill,
            "request_type_bk": item.get("request_type_bk", ""),
            "request_type_hd": item.get("request_type_hd", ""),
            "district": district,
            "address": item["address"],
            "lat": item["lat"],
            "lon": item["lon"],
            "window_start": parse_time(item["window_start"]),
            "window_end": parse_time(item["window_end"]),
            "duration_min": item["duration_min"],
            "time_norm": time_norm,
            "priority": priority,
            "required_vehicle": required_vehicle,
            "reference_status": item.get("reference_status", Job.STATUS_SENT),
            "reference_engineer": reference_engineer,
            "gigabit": item.get("gigabit", False),
            "current_status": item.get("status", "NOT_SENT"),
            "current_engineer": current_engineer,
            "required_equipment": item.get("required_equipment", []),
        }

    def _load_jobs(
        self, data, territory, skills_map, priorities_map, vehicles_map,
        time_norms_map, districts_map, engineers_by_name, jobs_map,
    ):
        for item in data.get("jobs", []):
            defaults = self._build_job_defaults(
                territory, item, skills_map, priorities_map, vehicles_map,
                time_norms_map, districts_map, engineers_by_name,
            )
            job, _ = Job.objects.update_or_create(
                job_id=item["job_id"], defaults=defaults,
            )
            jobs_map[job.job_id] = job

    # ------------------------------------------------------------------
    # События перепланирования
    # ------------------------------------------------------------------

    def _resolve_cancel_job(self, job_id_ref, jobs_map):
        """cancel_job.job_id иногда ссылается напрямую на job_id, а
        иногда закодирован как '<territory>-J<control_request_id>',
        не совпадающий с реальным job_id заявки. Пробуем оба варианта."""
        if job_id_ref in jobs_map:
            return jobs_map[job_id_ref]

        match = re.search(r"-J(\d+)$", job_id_ref)
        if match:
            control_id = int(match.group(1))
            return Job.objects.filter(control_request_id=control_id).first()
        return None

    def _load_reschedule_events(
        self, data, territory, skills_map, priorities_map, vehicles_map,
        time_norms_map, districts_map, engineers_map, jobs_map,
    ):
        for event in data.get("reschedule_events", []):
            event_type = event["type"]
            event_time = parse_time(event["time"])
            job_ref = None
            engineer_ref = None

            if event_type == RescheduleEvent.TYPE_URGENT_JOB:
                payload = event["payload"]
                # Срочная заявка создаётся как полноценный Job.
                job_defaults = self._build_job_defaults(
                    territory, payload, skills_map, priorities_map,
                    vehicles_map, time_norms_map, districts_map, {},
                )
                job_ref, _ = Job.objects.update_or_create(
                    job_id=payload["job_id"], defaults=job_defaults,
                )
                jobs_map[job_ref.job_id] = job_ref

            elif event_type == RescheduleEvent.TYPE_CANCEL_JOB:
                job_ref = self._resolve_cancel_job(event["job_id"], jobs_map)
                if job_ref:
                    job_ref.reference_status = Job.STATUS_CANCELLED
                    job_ref.save(update_fields=["reference_status"])
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  cancel_job: не найдена заявка '{event['job_id']}'"
                    ))

            elif event_type == RescheduleEvent.TYPE_ENGINEER_UNAVAILABLE:
                engineer_ref = engineers_map.get(event["engineer_id"])
                if not engineer_ref:
                    self.stdout.write(self.style.WARNING(
                        f"  engineer_unavailable: не найден инженер "
                        f"'{event['engineer_id']}'"
                    ))

            RescheduleEvent.objects.update_or_create(
                territory=territory,
                event_type=event_type,
                time=event_time,
                job=job_ref,
                engineer=engineer_ref,
                defaults={"payload": event},
            )
