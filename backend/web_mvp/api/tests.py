"""Минимальные API-тесты end-to-end MVP."""

from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from backend.web_mvp.api.services import optimization_service


class OptimizationApiTests(TestCase):
    """Проверяет загрузку dataset и запуск независимого solver."""

    def setUp(self) -> None:
        """Очищает in-memory состояние перед каждым тестом."""
        optimization_service.reset()
        optimization_service.use_osrm = False
        optimization_service.routing_provider = None
        self.client = APIClient()
        self.dataset_path = Path(__file__).resolve().parents[3] / "Югоцентр.json"

    def test_official_dataset_is_visible(self) -> None:
        """Официальный dataset доступен через API."""
        response = self.client.get("/api/dataset/official/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["dataset"]["engineers"]), 11)
        self.assertEqual(len(response.data["dataset"]["tasks"]), 56)

    def test_json_dataset_can_be_uploaded(self) -> None:
        """API принимает официальный JSON как multipart upload."""
        with self.dataset_path.open("rb") as dataset_file:
            response = self.client.post(
                "/api/dataset/upload/",
                {"file": dataset_file},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["dataset"]["source_name"], "Югоцентр.json")

    def test_optimize_returns_metrics_routes_and_unassigned_reasons(self) -> None:
        """Запуск OR-Tools возвращает маршрутный результат для dataset."""
        response = self.client.post("/api/optimize/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("metrics", response.data["result"])
        self.assertIn("routes", response.data["result"])
        self.assertIn("unassigned", response.data["result"])
        self.assertEqual(response.data["result"]["metrics"]["assigned_task_count"], 56)
        self.assertTrue(
            any(
                route["geometry"] is not None
                and route["geometry"]["type"] == "LineString"
                for route in response.data["result"]["routes"]
            )
        )

    @patch("LLM.query.explain_assignment", return_value="Заявка назначена Иванову.")
    @patch(
        "backend.web_mvp.api.services.ExplanationEngine.explain_task",
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
        optimize_response = self.client.post("/api/optimize/", {}, format="json")
        task_id = optimize_response.data["dataset"]["tasks"][0]["id"]

        response = self.client.post(
            f"/api/explain/{task_id}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["task_id"], task_id)
        self.assertEqual(
            response.data["explanation"],
            f"Заявка {task_id} назначена инженеру Иванов. Заявка назначена Иванову.",
        )
        self.assertTrue(response.data["developer_mode"])
        self.assertEqual(
            response.data["decision_trace"]["event_type"],
            "task_assignment_explanation",
        )

    @override_settings(DEVELOPER_MODE=False)
    @patch("LLM.query.explain_assignment", return_value="Причины назначения.")
    @patch(
        "backend.web_mvp.api.services.ExplanationEngine.explain_task",
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
        optimize_response = self.client.post("/api/optimize/", {}, format="json")
        task_id = optimize_response.data["dataset"]["tasks"][0]["id"]

        response = self.client.post(f"/api/explain/{task_id}/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["developer_mode"])
        self.assertNotIn("decision_trace", response.data)
        self.assertTrue(response.data["explanation"].startswith(f"Заявка {task_id}"))
