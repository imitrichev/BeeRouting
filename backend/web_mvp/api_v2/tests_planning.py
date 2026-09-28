"""Минимальные API-тесты end-to-end MVP."""

from dataclasses import replace
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from backend.optimization import CoordinateRoutingProvider, TaskStatus
from backend.web_mvp.api_v2.models import Engineer, Territory
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
        # При первой загрузке контрольные статусы не являются оперативным
        # состоянием: solver получает все 56 неназначенных заявок.
        self.assertEqual(response.data["result"]["metrics"]["assigned_task_count"], 56)
        tasks = response.data["dataset"]["tasks"]
        self.assertEqual(sum(task["is_plannable"] for task in tasks), 56)
        self.assertTrue(
            any(
                route["geometry"] is not None
                and route["geometry"]["type"] == "LineString"
                for route in response.data["result"]["routes"]
            )
        )

    def test_baseline_solver_is_available_through_the_planning_api(self) -> None:
        """Baseline строит тот же результат через API, что и основной solver."""
        response = self.client.post(
            "/api/v2/optimize/",
            {"solver": "baseline", "ignore_task_statuses": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("metrics", response.data["result"])
        self.assertIn("routes", response.data["result"])
        self.assertEqual(
            response.data["result"]["metrics"]["assigned_task_count"]
            + response.data["result"]["metrics"]["unassigned_task_count"],
            56,
        )

    def test_equipment_checkbox_controls_router_constraint_through_api(self) -> None:
        """API применяет запас роутеров только при consider_equipment=true."""
        service = restore(self.territory)
        service._scenario = replace(
            service._scenario,
            engineers=tuple(
                replace(engineer, available_router_count=0)
                for engineer in service._scenario.engineers
            ),
            tasks=tuple(
                replace(task, required_router_count=1)
                for task in service._scenario.tasks
            ),
        )
        service._problem = None
        service._result = None
        save(self.territory, service)

        ignored = self.client.post(
            "/api/v2/optimize/",
            {
                "solver": "ortools",
                "consider_equipment": False,
                "preserve_assigned_tasks": True,
            },
            format="json",
        )
        self.assertEqual(ignored.status_code, 200, ignored.data)
        self.assertGreater(
            ignored.data["result"]["metrics"]["assigned_task_count"],
            0,
        )
        self.assertFalse(ignored.data["planning_options"]["consider_equipment"])

        # Возвращаем чистую очередь перед вторым запуском, чтобы сравнить
        # ровно один и тот же набор заявок с включённой галочкой.
        service = restore(self.territory)
        service._scenario = replace(
            service._scenario,
            tasks=tuple(
                replace(task, status=TaskStatus.NOT_SENT, current_engineer_id=None)
                for task in service._scenario.tasks
            ),
        )
        service._problem = None
        service._result = None
        save(self.territory, service)

        enforced = self.client.post(
            "/api/v2/optimize/",
            {
                "solver": "ortools",
                "consider_equipment": True,
                "preserve_assigned_tasks": True,
            },
            format="json",
        )
        self.assertEqual(enforced.status_code, 200, enforced.data)
        self.assertEqual(
            enforced.data["result"]["metrics"]["assigned_task_count"],
            0,
        )
        self.assertTrue(enforced.data["planning_options"]["consider_equipment"])
        self.assertTrue(
            all(
                item["reason_code"] == "missing_equipment"
                for item in enforced.data["result"]["unassigned"]
            )
        )

    def test_status_dropdown_updates_operational_status_without_replanning(self) -> None:
        """Статус назначенной заявки меняется отдельной операцией без solver."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        self.assertEqual(initial.status_code, 200, initial.data)
        route = next(route for route in initial.data["result"]["routes"] if route["stops"])
        task_id = route["stops"][0]["task_id"]
        engineer_id = route["engineer_id"]
        route_ids_before = [item["task_id"] for item in route["stops"]]

        response = self.client.patch(
            "/api/v2/jobs/status/",
            {"task_id": task_id, "status": "IN_PROGRESS"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        task = next(item for item in response.data["dataset"]["tasks"] if item["id"] == task_id)
        self.assertEqual(task["status"], "IN_PROGRESS")
        route_after = next(
            route for route in response.data["result"]["routes"]
            if route["engineer_id"] == engineer_id
        )
        self.assertEqual(
            route_ids_before,
            [item["task_id"] for item in route_after["stops"]],
        )

    def test_assigned_task_can_be_marked_overdue(self) -> None:
        """Просроченный статус допустим для заявки, уже находящейся в плане."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        self.assertEqual(initial.status_code, 200, initial.data)
        route = next(route for route in initial.data["result"]["routes"] if route["stops"])
        task_id = route["stops"][0]["task_id"]

        response = self.client.patch(
            "/api/v2/jobs/status/",
            {"task_id": task_id, "status": "OVERDUE"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        task = next(item for item in response.data["dataset"]["tasks"] if item["id"] == task_id)
        self.assertEqual(task["status"], "OVERDUE")

    def test_assigned_task_can_be_released_without_reoptimization(self) -> None:
        """NOT_SENT освобождает маршрут и оборудование без запуска solver."""
        initial = self.client.post(
            "/api/v2/optimize/",
            {"ignore_task_statuses": True, "consider_equipment": True},
            format="json",
        )
        self.assertEqual(initial.status_code, 200, initial.data)
        tasks_by_id = {
            task["id"]: task for task in initial.data["dataset"]["tasks"]
        }
        route = next(
            route
            for route in initial.data["result"]["routes"]
            if any(
                tasks_by_id[stop["task_id"]]["required_router_count"] > 0
                for stop in route["stops"]
            )
        )
        task_id = next(
            stop["task_id"]
            for stop in route["stops"]
            if tasks_by_id[stop["task_id"]]["required_router_count"] > 0
        )
        assigned_count_before = initial.data["result"]["metrics"][
            "assigned_task_count"
        ]

        response = self.client.patch(
            "/api/v2/jobs/status/",
            {"task_id": task_id, "status": "NOT_SENT"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        task = next(
            item
            for item in response.data["dataset"]["tasks"]
            if item["id"] == task_id
        )
        self.assertEqual(task["status"], "NOT_SENT")
        self.assertIsNone(task["current_engineer_id"])
        self.assertFalse(
            any(
                stop["task_id"] == task_id
                for result_route in response.data["result"]["routes"]
                for stop in result_route["stops"]
            )
        )
        reason = next(
            item
            for item in response.data["result"]["unassigned"]
            if item["task_id"] == task_id
        )
        self.assertEqual(reason["reason_code"], "manually_unassigned")
        self.assertEqual(
            response.data["result"]["metrics"]["assigned_task_count"],
            assigned_count_before - 1,
        )

    def test_unassigned_status_can_only_be_cancelled(self) -> None:
        """Неназначенную заявку нельзя вручную перевести в рабочий статус."""
        task_id = self.client.get("/api/v2/dataset/").data["dataset"]["tasks"][0]["id"]
        rejected = self.client.patch(
            "/api/v2/jobs/status/",
            {"task_id": task_id, "status": "ASSIGNED"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 422, rejected.data)

        cancelled = self.client.patch(
            "/api/v2/jobs/status/",
            {"task_id": task_id, "status": "CANCELLED"},
            format="json",
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        task = next(item for item in cancelled.data["dataset"]["tasks"] if item["id"] == task_id)
        self.assertEqual(task["status"], "CANCELLED")

    def test_reference_distribution_fully_reloads_json_plan(self) -> None:
        """Контрольная кнопка отбрасывает изменения и загружает план JSON."""
        initial = self.client.post(
            "/api/v2/optimize/",
            {"ignore_task_statuses": True},
            format="json",
        )
        self.assertEqual(initial.status_code, 200, initial.data)
        scenario = restore(self.territory)._scenario
        reference_engineer_id_by_task = {
            task.id: next(
                engineer.id
                for engineer in scenario.engineers
                if engineer.name == scenario.reference_engineer_by_task[task.id]
            )
            for task in scenario.tasks
            if scenario.reference_engineer_by_task.get(task.id)
        }
        reference_status_by_task = {
            task.id: scenario.reference_status_by_task[task.id].value
            for task in scenario.tasks
        }

        response = self.client.post(
            "/api/v2/sync-reference-statuses/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        tasks_by_id = {
            task["id"]: task for task in response.data["dataset"]["tasks"]
        }
        route_engineer_by_task = {
            stop["task_id"]: route["engineer_id"]
            for route in response.data["result"]["routes"]
            for stop in route["stops"]
        }
        for task_id, reference_status in reference_status_by_task.items():
            if reference_status in {"CANCELLED", "COMPLETED", "NOT_SENT"}:
                self.assertNotIn(task_id, route_engineer_by_task)
            else:
                self.assertEqual(
                    route_engineer_by_task.get(task_id),
                    reference_engineer_id_by_task[task_id],
                )
            self.assertEqual(tasks_by_id[task_id]["status"], reference_status)

    def test_unknown_solver_is_rejected(self) -> None:
        """API не принимает случайное имя алгоритма."""
        response = self.client.post(
            "/api/v2/optimize/",
            {"solver": "control"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

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
        self.assertEqual(len(assigned_tasks), 56)
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
        """Новая заявка появляется в dataset как NOT_SENT."""
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

    def test_created_task_preserves_plan_and_baseline_only_adds_pending(self) -> None:
        """Создание не стирает план, а Baseline дополняет его новой заявкой."""
        self._assert_incremental_assignment("baseline", "NEW-BASELINE")

    def test_created_task_preserves_plan_and_ortools_only_adds_pending(self) -> None:
        """OR-Tools фиксирует прежних исполнителей и назначает новую заявку."""
        self._assert_incremental_assignment("ortools", "NEW-ORTOOLS")

    def _assert_incremental_assignment(self, solver: str, task_id: str) -> None:
        """Проверяет общий контракт инкрементального запуска solver."""
        initial = self.client.post(
            "/api/v2/optimize/",
            {"solver": "ortools", "preserve_assigned_tasks": True},
            format="json",
        )
        self.assertEqual(initial.status_code, 200, initial.data)
        assignment_before = {
            stop["task_id"]: route["engineer_id"]
            for route in initial.data["result"]["routes"]
            for stop in route["stops"]
        }

        created = self.client.post(
            "/api/v2/tasks/",
            {
                "id": task_id,
                "latitude": 55.75,
                "longitude": 37.61,
                "work_type": "LOCAL",
                "window_start": "09:00",
                "window_end": "22:00",
                "required_router_count": 0,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        # Ответ создания содержит прежний результат без скрытого перезапуска.
        self.assertEqual(
            assignment_before,
            {
                stop["task_id"]: route["engineer_id"]
                for route in created.data["result"]["routes"]
                for stop in route["stops"]
            },
        )
        new_task = next(
            task for task in created.data["dataset"]["tasks"] if task["id"] == task_id
        )
        self.assertEqual(new_task["status"], "NOT_SENT")
        self.assertIsNone(new_task["current_engineer_id"])
        pending = next(
            item
            for item in created.data["result"]["unassigned"]
            if item["task_id"] == task_id
        )
        self.assertEqual(pending["reason_code"], "not_distribution_attempted")
        self.assertEqual(
            pending["message"],
            "С момента создания этой заявки не было попыток её распределения",
        )
        self.assertEqual(
            created.data["result"]["metrics"]["unassigned_task_count"],
            initial.data["result"]["metrics"]["unassigned_task_count"] + 1,
        )

        updated = self.client.post(
            "/api/v2/optimize/",
            {
                "solver": solver,
                "ignore_task_statuses": False,
                "preserve_assigned_tasks": True,
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        assignment_after = {
            stop["task_id"]: route["engineer_id"]
            for route in updated.data["result"]["routes"]
            for stop in route["stops"]
        }
        self.assertIn(task_id, assignment_after)
        self.assertTrue(
            all(assignment_after[old_id] == engineer_id for old_id, engineer_id in assignment_before.items())
        )

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
        # До проверки позднего сценария явно переносим operational-статусы
        # из контрольного источника отдельной пользовательской операцией.
        synced = self.client.post(
            "/api/v2/sync-reference-statuses/", {}, format="json"
        )
        self.assertEqual(synced.status_code, 200, synced.data)
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
        synced = self.client.post(
            "/api/v2/sync-reference-statuses/", {}, format="json"
        )
        self.assertEqual(synced.status_code, 200, synced.data)
        before = {
            task["id"]: task["status"]
            for task in synced.data["dataset"]["tasks"]
        }
        task_id = next(
            stop["task_id"]
            for route in synced.data["result"]["routes"]
            for stop in route["stops"]
            if before[stop["task_id"]] == "ASSIGNED"
        )

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
        recalculated = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        recalculated_ids = {
            stop["task_id"]
            for route in recalculated.data["result"]["routes"]
            for stop in route["stops"]
        }
        self.assertNotIn(task_id, recalculated_ids)
        after = {
            task["id"]: task["status"]
            for task in response.data["dataset"]["tasks"]
        }
        for other_task_id, status_before in before.items():
            if other_task_id == task_id:
                continue
            if status_before in {
                "COMPLETED",
                "CANCELLED",
                "EN_ROUTE",
                "IN_PROGRESS",
            }:
                self.assertEqual(after[other_task_id], status_before)
        restored = restore(Territory.objects.get(pk=self.territory.pk))
        self.assertFalse(restored._problem.preserve_assigned_tasks)

    def test_unavailable_engineer_receives_no_tasks(self) -> None:
        """Недоступность освобождает его маршрут и защищает чужую начатую работу."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        non_empty_routes = [
            route for route in initial.data["result"]["routes"] if route["stops"]
        ]
        self.assertGreaterEqual(len(non_empty_routes), 2)
        unavailable_route, protected_route = non_empty_routes[:2]
        engineer_id = unavailable_route["engineer_id"]
        released_task_ids = {
            stop["task_id"] for stop in unavailable_route["stops"]
        }
        protected_task_id = protected_route["stops"][0]["task_id"]
        protected_engineer_id = protected_route["engineer_id"]
        status_response = self.client.patch(
            "/api/v2/jobs/status/",
            {"task_id": protected_task_id, "status": "EN_ROUTE"},
            format="json",
        )
        self.assertEqual(status_response.status_code, 200, status_response.data)

        response = self.client.post(
            "/api/v2/replan/",
            {
                "event_type": "ENGINEER_UNAVAILABLE",
                "engineer_id": engineer_id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        unavailable_engineer = next(
            item
            for item in response.data["dataset"]["engineers"]
            if item["id"] == engineer_id
        )
        self.assertFalse(unavailable_engineer["is_active"])
        route = next(
            item for item in response.data["result"]["routes"]
            if item["engineer_id"] == engineer_id
        )
        self.assertEqual(route["stops"], [])
        assignment_after = {
            stop["task_id"]: route_item["engineer_id"]
            for route_item in response.data["result"]["routes"]
            for stop in route_item["stops"]
        }
        self.assertTrue(
            all(
                assignment_after.get(task_id) != engineer_id
                for task_id in released_task_ids
            )
        )
        self.assertEqual(
            assignment_after.get(protected_task_id),
            protected_engineer_id,
        )
        restored = restore(Territory.objects.get(pk=self.territory.pk))
        self.assertFalse(restored._problem.preserve_assigned_tasks)
        self.assertIn(engineer_id, restored._problem.unavailable_engineer_ids)
        self.assertFalse(
            Engineer.objects.get(
                territory=self.territory, engineer_id=engineer_id
            ).is_active
        )
        self.assertEqual(
            restored._problem.fixed_task_engineer_by_id.get(protected_task_id),
            protected_engineer_id,
        )
        recalculated = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        repeated_route = next(
            item
            for item in recalculated.data["result"]["routes"]
            if item["engineer_id"] == engineer_id
        )
        self.assertEqual(repeated_route["stops"], [])

    def test_emergency_event_creates_urgent_emergency_task(self) -> None:
        """Авария создаётся как NOT_SENT и перестраивает только будущий план."""
        initial = self.client.post(
            "/api/v2/optimize/",
            {"ignore_task_statuses": True},
            format="json",
        )
        self.assertEqual(initial.status_code, 200, initial.data)
        protected_route = next(
            route for route in initial.data["result"]["routes"] if route["stops"]
        )
        protected_task_id = protected_route["stops"][0]["task_id"]
        protected_engineer_id = protected_route["engineer_id"]
        status_response = self.client.patch(
            "/api/v2/jobs/status/",
            {"task_id": protected_task_id, "status": "EN_ROUTE"},
            format="json",
        )
        self.assertEqual(status_response.status_code, 200, status_response.data)

        response = self.client.post(
            "/api/v2/replan/",
            {
                "event_type": "EMERGENCY_TASK",
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
        # После расчёта авария либо назначена, либо явно возвращена в списке
        # неназначенных: она не может потеряться между созданием и solver.
        planned_task_ids = {
            stop["task_id"]
            for route in response.data["result"]["routes"]
            for stop in route["stops"]
        }
        unassigned_task_ids = {
            item["task_id"] for item in response.data["result"]["unassigned"]
        }
        self.assertIn("EMERGENCY-1", planned_task_ids | unassigned_task_ids)
        assignment_after = {
            stop["task_id"]: route["engineer_id"]
            for route in response.data["result"]["routes"]
            for stop in route["stops"]
        }
        self.assertEqual(
            assignment_after.get(protected_task_id),
            protected_engineer_id,
        )
        restored = restore(Territory.objects.get(pk=self.territory.pk))
        self.assertFalse(restored._problem.preserve_assigned_tasks)
        self.assertEqual(
            restored._problem.fixed_task_engineer_by_id.get(protected_task_id),
            protected_engineer_id,
        )

    def test_manual_reassignment_requires_preview_and_confirmation(self) -> None:
        """Preview показывает метрики, а план меняется только после подтверждения."""
        initial = self.client.post(
            "/api/v2/optimize/", {"ignore_task_statuses": True}, format="json"
        )
        # Фиксированная допустимая пара текущего набора: заявка из маршрута
        # E01 сохраняет окно и смену после переноса к E02.
        task_id = "yugo_tsentr-J46513"
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
