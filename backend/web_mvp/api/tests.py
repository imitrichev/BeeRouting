"""Минимальные API-тесты end-to-end MVP."""

from pathlib import Path

from django.test import TestCase
from rest_framework.test import APIClient

from .services import optimization_service


class OptimizationApiTests(TestCase):
    """Проверяет загрузку dataset и запуск независимого solver."""

    def setUp(self) -> None:
        """Очищает in-memory состояние перед каждым тестом."""
        optimization_service.reset()
        optimization_service.use_osrm = False
        optimization_service.routing_provider = None
        self.client = APIClient()
        self.dataset_path = Path(__file__).resolve().parents[3] / "yugo_center.json"

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
        self.assertEqual(response.data["dataset"]["source_name"], "yugo_center.json")

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
