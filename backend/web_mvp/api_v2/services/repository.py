"""Синхронизация актуального domain-состояния с моделями коллеги."""
from ..models import Engineer, Job, Skill, VehicleType, Priority, District
from backend.optimization import TaskStatus


def sync_entities(territory, service):
    """Сохраняет текущие сущности, не переписывая контрольное распределение."""
    # При самой первой загрузке плана ещё нет. Контрольные статусы остаются
    # в reference-полях, а operational-состояние в БД начинается с NOT_SENT.
    has_existing_plan = bool((territory.response or {}).get("result"))
    engineers = {}
    for item in service._scenario.engineers:
        shift = next(a for a in service._scenario.availabilities if a.engineer_id == item.id)
        vehicle, _ = VehicleType.objects.get_or_create(code=item.vehicle_type.value, defaults={'name':item.vehicle_type.value})
        existing = Engineer.objects.filter(
            territory=territory, engineer_id=item.id
        ).first()
        engineer, _ = Engineer.objects.update_or_create(territory=territory, engineer_id=item.id, defaults={
            'name':item.name, 'vehicle_type':vehicle,
            'start_lat':item.start_latitude, 'start_lon':item.start_longitude,
            # В domain Engineer пока нет отдельного адреса старта. Поэтому
            # повторное сохранение плана не должно затирать адрес, введённый
            # через ORM API коллеги, общим адресом офиса scenario.
            'start_address':(
                existing.start_address if existing
                else service._scenario.office_address or ''
            ),
            'shift_start':shift.available_from, 'shift_end':shift.available_until,
            'available_equipment':sorted(item.available_equipment),
            'available_router_count':item.available_router_count,
        })
        engineer.skills.set([Skill.objects.get_or_create(code=s.value, defaults={'name':s.value})[0] for s in item.qualifications])
        engineers[item.id] = engineer
    planned_engineers = {
        stop.task_id: engineer_id
        for engineer_id, route in (service._result.routes.items() if service._result else [])
        for stop in route.stops
    }
    source_jobs = {j['job_id']:j for j in territory.source_payload.get('jobs', [])}
    for item in service._scenario.tasks:
        original = source_jobs.get(item.id, {})
        district, _ = District.objects.get_or_create(territory=territory, name=original.get('district') or territory.name)
        skill_code = next(iter(item.required_skills)).value
        skill = Skill.objects.get_or_create(code=skill_code, defaults={'name':skill_code})[0]
        priority, _ = Priority.objects.get_or_create(code=item.priority.value, defaults={'name':item.priority.value})
        vehicle = None
        if item.required_vehicle_type:
            vehicle, _ = VehicleType.objects.get_or_create(code=item.required_vehicle_type.value, defaults={'name':item.required_vehicle_type.value})
        reference = next((e for e in engineers.values() if e.name == original.get('reference_crew')), None)
        operational_status = item.status.value
        operational_engineer_id = planned_engineers.get(item.id, item.current_engineer_id)
        if (
            service._result is None
            and not has_existing_plan
            and not getattr(service, "_manual_status_update", False)
        ):
            operational_status = TaskStatus.NOT_SENT.value
            operational_engineer_id = None
        Job.objects.update_or_create(territory=territory, job_id=item.id, defaults={
            'request_id':original.get('request_id', 0), 'control_request_id':original.get('control_request_id'),
            'skill_required':skill, 'priority':priority, 'district':district,
            'request_type_bk':original.get('request_type_bk',''), 'request_type_hd':original.get('request_type_hd',''),
            'address':item.address or '', 'lat':item.latitude, 'lon':item.longitude,
            'window_start':item.window_start, 'window_end':item.window_end, 'duration_min':item.duration_minutes,
            'required_vehicle':vehicle, 'required_equipment':sorted(item.required_equipment),
            'required_router_count':item.required_router_count,
            'reference_status':original.get('reference_status','Не отправлена'), 'reference_engineer':reference,
            'current_status':operational_status, 'current_engineer':engineers.get(operational_engineer_id),
            'gigabit':original.get('gigabit',False),
        })
