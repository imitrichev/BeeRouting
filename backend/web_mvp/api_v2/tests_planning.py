"""Минимальные API-тесты end-to-end MVP."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from backend.optimization import CoordinateRoutingProvider
from backend.web_mvp.api_v2.models import Territory
from backend.web_mvp.api_v2.services import import_dataset, restore, save
from backend.web_mvp.api_v2.services.optimization import OptimizationWebService
from backend.web_mvp.api_v2.services.planning import OFFICIAL_DATASET_PATH


class TerritoryApiClient(APIClient):
    """Направляет прежние сценарии тестов только в API v2 выбранного района."""

    territory_code: str

    def generic(self, method, path, *args, **kwargs):
        """Добавляет обязательный территориальный контекст API v2."""
        if path.startswith("/api/v2/") and "territory=" not in path:
            separator = "&" if "?" in path else "?"
            path = f"{path}{separator}territory={self.territory_code}"
        return super().generic(method, path, *args, **kwargs)


class OptimizationApiTests(TestCase):
    """Проверяет загрузку dataset и запуск независимого solver."""

    def setUp(self) -> None:
        """Создаёт постоянный район и локальный routing provider для API v2."""
        self.dataset_path = OFFICIAL_DATASET_PATH
        self.territory = import_dataset(
            self.dataset_path.read_bytes(),
            self.dataset_path.name,
        )
        self.client = TerritoryApiClient()
        self.client.territory_code = self.territory.code
        provider_factory = lambda coordinates, **_kwargs: CoordinateRoutingProvider(
            coordinates,
            speed_km_per_hour=30,
        )
        planning_provider = patch(
            "backend.web_mvp.api_v2.services.planning.create_osrm_provider_from_environment",
            side_effect=provider_factory,
        )
        restore_provider = patch(
            "backend.web_mvp.api_v2.services.optimization.create_osrm_provider_from_environment",
            side_effect=provider_factory,
        )
        planning_provider.start()
        restore_provider.start()
        self.addCleanup(planning_provider.stop)
        self.addCleanup(restore_provider.stop)

    def test_official_dataset_is_visible(self) -> None:
        """Официальный dataset доступен через API."""
        response = self.client.get("/api/v2/dataset/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["dataset"]["engineers"]), 11)
        self.assertEqual(len(response.data["dataset"]["tasks"]), 56)
        # До нажатия «Контрольное распределение» reference_status из JSON не
        # является текущим статусом заявки и не должен попадать в таблицу.
        self.assertIsNone(response.data.get("result"))
        self.assertTrue(
            all(task["status"] == "NOT_SENT" for task in response.data["dataset"]["tasks"])
        )

    def test_existing_unplanned_snapshot_hides_legacy_reference_statuses(self) -> None:
        """GET скрывает старые контрольные статусы и в уже сохранённом JSON."""
        self.territory.response["dataset"]["tasks"][0]["status"] = "COMPLETED"
        self.territory.response["dataset"]["tasks"][0]["assignment_locked"] = True
        self.territory.save(update_fields=["response"])

        response = self.client.get("/api/v2/dataset/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(task["status"] == "NOT_SENT" for task in response.data["dataset"]["tasks"])
        )
        self.assertFalse(
            any(task["assignment_locked"] for task in response.data["dataset"]["tasks"])
        )

    def test_json_dataset_can_be_uploaded(self) -> None:
        """API принимает официальный JSON как multipart upload."""
        with self.dataset_path.open("rb") as dataset_file:
            response = self.client.post(
                "/api/v2/dataset/upload/",
                {"file": dataset_file},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["dataset"]["source_name"], "Югоцентр.json")

    def test_optimize_returns_metrics_routes_and_unassigned_reasons(self) -> None:
        """Запуск OR-Tools возвращает маршрутный результат для dataset."""
        response = self.client.post("/api/v2/optimize/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("metrics", response.data["result"])
        self.assertIn("routes", response.data["result"])
        self.assertIn("unassigned", response.data["result"])
        # В исходном dataset только 14 заявок требуют текущего планирования:
        # COMPLETED и CANCELLED остаются в таблице, но не строятся повторно.
        self.assertEqual(response.data["result"]["metrics"]["assigned_task_count"], 14)
        tasks = response.data["dataset"]["tasks"]
        self.assertEqual(sum(task["is_plannable"] for task in tasks), 14)
        # При уважении статусов API сохраняет 10 обычных ASSIGNED и 4 уже
        # начатые заявки; в новом полном режиме frontend отправляет
        # ignore_task_statuses=True и блокировок не будет.
        self.assertEqual(sum(task["assignment_locked"] for task in tasks), 14)
        self.assertTrue(
            any(
                route["geometry"] is not None
                and route["geometry"]["type"] == "LineString"
                for route in response.data["result"]["routes"]
            )
        )

    def test_control_distribution_reveals_source_statuses_after_planning(self) -> None:
        """После контрольного расчёта исходные operational статусы видны."""
        response = self.client.post(
            "/api/v2/optimize/",
            {"ignore_task_statuses": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data.get("result"))
        self.assertTrue(
            any(
                task["status"] != "NOT_SENT"
                for task in response.data["dataset"]["tasks"]
            )
        )

    def test_assigned_tasks_can_be_preserved_by_request_mode(self) -> None:
        """API передаёт режим фиксации ASSIGNED в математическое ядро."""
        response = self.client.post(
            "/api/v2/optimize/",
            {"preserve_assigned_tasks": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        assigned_tasks = [
            task
            for task in response.data["dataset"]["tasks"]
            if task["status"] == "ASSIGNED"
        ]
        self.assertEqual(len(assigned_tasks), 10)
        self.assertTrue(all(task["assignment_locked"] for task in assigned_tasks))

        route_by_task = {
            stop["task_id"]: route["engineer_id"]
            for route in response.data["result"]["routes"]
            for stop in route["stops"]
        }
        self.assertTrue(
            all(
                route_by_task[task["id"]] == task["current_engineer_id"]
                for task in assigned_tasks
            )
        )

    def test_ignore_statuses_builds_a_new_plan_for_all_tasks(self) -> None:
        """Полный режим frontend включает даже исторические статусы в новый план."""
        response = self.client.post(
            "/api/v2/optimize/",
            {"ignore_task_statuses": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["result"]["metrics"]["assigned_task_count"],
            56,
        )
        self.assertTrue(all(task["is_plannable"] for task in response.data["dataset"]["tasks"]))
        self.assertFalse(any(task["assignment_locked"] for task in response.data["dataset"]["tasks"]))

    def test_task_can_be_created_through_api(self) -> None:
        """Новая заявка появляется в dataset и сбрасывает старый результат."""
        response = self.client.post(
            "/api/v2/tasks/",
            {
                "id": "NEW-1",
                "latitude": 55.75,
                "longitude": 37.61,
                "work_type": "LOCAL",
                "window_start": "12:00",
                "window_end": "14:00",
                "required_equipment": ["multimeter"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created = response.data["dataset"]["tasks"][-1]
        self.assertEqual(created["id"], "NEW-1")
        self.assertEqual(created["required_skill"], "LOCAL_WORKS")
        self.assertEqual(created["duration_minutes"], 30)
        self.assertEqual(created["priority"], "NORMAL")
        self.assertEqual(created["status"], "NOT_SENT")

    def test_duplicate_task_is_rejected(self) -> None:
        """API не позволяет затереть существующую заявку тем же ID."""
        existing_id = self.client.get("/api/v2/dataset/").data["dataset"]["tasks"][0]["id"]
        response = self.client.post(
            "/api/v2/tasks/",
            {
                "id": existing_id,
                "latitude": 55.75,
                "longitude": 37.61,
                "work_type": "LOCAL",
                "window_start": "12:00",
                "window_end": "14:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_late_manual_task_cannot_activate_new_engineer(self) -> None:
        """После условных 14:00 новый план не вызывает инженера из дома."""
        initial = self.client.post(
            "/api/v2/optimize/",
            {"ignore_task_statuses": True},
            format="json",
        )
        self.assertEqual(initial.status_code, 200)
        created = self.client.post(
            "/api/v2/tasks/",
            {
                "id": "LATE-NEW",
                "latitude": 55.75,
                "longitude": 37.61,
                "work_type": "LOCAL",
                "window_start": "16:00",
                "window_end": "18:00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        service = restore(Territory.objects.get(pk=self.territory.pk))
        self.assertIn("LATE-NEW", service._late_day_manual_task_ids)

        # Имитируем результат, который потребовал бы вызвать любого инженера,
        # отсутствовавшего в исходном составе на линии.
        service._late_day_active_engineer_ids.clear()
        save(self.territory, service)
        rejected = self.client.post(
            "/api/v2/optimize/",
            {"ignore_task_statuses": True},
            format="json",
        )

        self.assertEqual(rejected.status_code, 422)
        self.assertIn("После условных 14:00", rejected.data["error"])
        task = next(
            item
            for item in self.client.get("/api/v2/dataset/").data["dataset"]["tasks"]
            if item["id"] == "LATE-NEW"
        )
        self.assertEqual(task["status"], "NOT_SENT")

    def test_late_emergency_can_activate_new_engineer(self) -> None:
        """Авария не включает запрет вызова дополнительной бригады."""
        created = self.client.post(
            "/api/v2/tasks/",
            {
                "id": "LATE-EMERGENCY",
                "latitude": 55.75,
                "longitude": 37.61,
                "work_type": "EMERGENCY",
                "window_start": "16:00",
                "window_end": "18:00",
            },
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertNotIn(
            "LATE-EMERGENCY",
            restore(Territory.objects.get(pk=self.territory.pk))._late_day_manual_task_ids,
        )

    def test_task_window_rejects_non_24_hour_time(self) -> None:
        """Форма не принимает часы за пределами 00:00–23:59."""
        response = self.client.post(
            "/api/v2/tasks/",
            {
                "id": "BAD-TIME",
                "latitude": 55.75,
                "longitude": 37.61,
                "work_type": "LOCAL",
                "window_start": "25:00",
                "window_end": "26:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cancelled_task_is_removed_by_dynamic_replanning(self) -> None:
        """Сценарий отмены исключает заявку из продолжения плана."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        task_id = initial.data["result"]["routes"][0]["stops"][0]["task_id"]

        response = self.client.post(
            "/api/v2/replan/",
            {"event_type": "TASK_CANCELLED", "planning_time": "09:00", "task_id": task_id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        task = next(item for item in response.data["dataset"]["tasks"] if item["id"] == task_id)
        self.assertEqual(task["status"], "CANCELLED")
        planned_ids = {
            stop["task_id"]
            for route in response.data["result"]["routes"]
            for stop in route["stops"]
        }
        self.assertNotIn(task_id, planned_ids)

    def test_unavailable_engineer_receives_no_tasks(self) -> None:
        """Сценарий недоступности освобождает и запрещает маршрут инженера."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        engineer_id = next(
            route["engineer_id"]
            for route in initial.data["result"]["routes"]
            if route["stops"]
        )

        response = self.client.post(
            "/api/v2/replan/",
            {
                "event_type": "ENGINEER_UNAVAILABLE",
                "planning_time": "09:00",
                "engineer_id": engineer_id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        route = next(
            item for item in response.data["result"]["routes"]
            if item["engineer_id"] == engineer_id
        )
        self.assertEqual(route["stops"], [])

    def test_emergency_event_creates_urgent_emergency_task(self) -> None:
        """Аварийный сценарий создаёт заявку с обязательным приоритетом и навыком."""
        response = self.client.post(
            "/api/v2/replan/",
            {
                "event_type": "EMERGENCY_TASK",
                "planning_time": "09:00",
                "task": {
                    "id": "EMERGENCY-1",
                    "latitude": 55.70,
                    "longitude": 37.65,
                    "work_type": "LOCAL",
                    "window_start": "09:00",
                    "window_end": "21:00",
                    "priority": "NORMAL",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        task = response.data["dataset"]["tasks"][-1]
        self.assertEqual(task["id"], "EMERGENCY-1")
        self.assertEqual(task["required_skill"], "EMERGENCY_WORKS")
        self.assertEqual(task["duration_minutes"], 80)
        self.assertEqual(task["priority"], "URGENT")

    def test_manual_reassignment_requires_preview_and_confirmation(self) -> None:
        """Preview показывает метрики, а план меняется только после подтверждения."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        task_id = "yugo_tsentr-J78540"
        old_engineer_id = next(
            route["engineer_id"]
            for route in initial.data["result"]["routes"]
            if any(stop["task_id"] == task_id for stop in route["stops"])
        )
        new_engineer_id = "yugo_tsentr-E02"

        preview = self.client.post(
            "/api/v2/manual-reassignment/preview/",
            {"task_id": task_id, "engineer_id": new_engineer_id},
            format="json",
        )

        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.data["feasible"])
        self.assertEqual(preview.data["old_engineer"]["id"], old_engineer_id)
        self.assertIn("used_engineers_count", preview.data["before"])
        self.assertIn("total_distance_km", preview.data["after"])
        # До подтверждения опубликованный result всё ещё содержит старый маршрут.
        self.assertTrue(
            any(
                stop.task_id == task_id
                for stop in restore(Territory.objects.get(pk=self.territory.pk))._result.routes[old_engineer_id].stops
            )
        )

        confirmed = self.client.post(
            "/api/v2/manual-reassignment/confirm/",
            {"proposal_id": preview.data["proposal_id"]},
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200)
        new_route = next(
            route for route in confirmed.data["result"]["routes"]
            if route["engineer_id"] == new_engineer_id
        )
        self.assertTrue(any(stop["task_id"] == task_id for stop in new_route["stops"]))

    def test_manual_reassignment_reports_missing_skill(self) -> None:
        """Недопустимый инженер отклоняется до запуска OR-Tools с ясной причиной."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        task = next(
            item for item in initial.data["dataset"]["tasks"]
            if item["required_skill"] == "EMERGENCY_WORKS"
        )
        engineer = next(
            item for item in initial.data["dataset"]["engineers"]
            if "EMERGENCY_WORKS" not in item["qualifications"]
        )

        response = self.client.post(
            "/api/v2/manual-reassignment/preview/",
            {"task_id": task["id"], "engineer_id": engineer["id"]},
            format="json",
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(response.data["feasible"])
        self.assertEqual(response.data["reason_code"], "MISSING_SKILL")
        self.assertIn("нет требуемой квалификации", response.data["message"])

    @patch.object(
        OptimizationWebService,
        "geocode_address",
        return_value=(55.7558, 37.6176),
    )
    def test_address_can_be_geocoded_for_task_form(self, _geocode_mock) -> None:
        """Frontend получает координаты только после успешной проверки адреса."""
        response = self.client.post(
            "/api/v2/geocode/", {"address": "Москва, Красная площадь, 1"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["latitude"], 55.7558)

    @patch("LLM.query.explain_assignment", return_value="Заявка назначена Иванову.")
    @patch(
        "backend.web_mvp.api_v2.services.planning.ExplanationEngine.explain_task",
        return_value={
            "schema_version": "1.0",
            "event_type": "task_assignment_explanation",
            "assignment": {
                "status": "assigned",
                "engineer": {"id": "e1", "name": "Иванов"},
            },
            "assignment_reasons": [],
            "checks": [],
        },
    )
    def test_explanation_endpoint_returns_trace_and_llm_text(
        self,
        _trace_mock,
        _llm_mock,
    ) -> None:
        """Endpoint отдаёт decision trace и текст, не выполняя LLM в тесте."""
        optimize_response = self.client.post("/api/v2/optimize/", {}, format="json")
        task_id = optimize_response.data["dataset"]["tasks"][0]["id"]

        response = self.client.post(
            f"/api/v2/explain/{task_id}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["task_id"], task_id)
        self.assertEqual(
            response.data["explanation"],
            "Заявка назначена Иванову.",
        )
        self.assertTrue(response.data["developer_mode"])
        self.assertEqual(
            response.data["decision_trace"]["event_type"],
            "task_assignment_explanation",
        )

    @override_settings(DEVELOPER_MODE=False)
    @patch("LLM.query.explain_assignment", return_value="Причины назначения.")
    @patch(
        "backend.web_mvp.api_v2.services.planning.ExplanationEngine.explain_task",
        return_value={
            "assignment": {
                "status": "assigned",
                "engineer": {"id": "e1", "name": "Иванов"},
            },
        },
    )
    def test_production_explanation_does_not_expose_trace(
        self,
        _trace_mock,
        _llm_mock,
    ) -> None:
        """Production API не передаёт внутренний decision trace клиенту."""
        optimize_response = self.client.post("/api/v2/optimize/", {}, format="json")
        task_id = optimize_response.data["dataset"]["tasks"][0]["id"]

        response = self.client.post(f"/api/v2/explain/{task_id}/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["developer_mode"])
        self.assertNotIn("decision_trace", response.data)
        self.assertEqual(response.data["explanation"], "Причины назначения.")
