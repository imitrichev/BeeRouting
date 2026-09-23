"""Интеграционные проверки постоянного состояния и изоляции районов."""
import json
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from rest_framework.test import APIClient
from backend.web_mvp.api.services import OFFICIAL_DATASET_PATH
from backend.optimization import CoordinateRoutingProvider
from .services import import_dataset, restore
from .models import Territory


class PersistentPlanningTests(TestCase):
    """Проверяет настоящее построение плана с локальными матрицами."""
    def setUp(self):
        self.client = APIClient()
        self.territory = import_dataset(OFFICIAL_DATASET_PATH.read_bytes(), 'Югоцентр.json')
        self.provider = patch('backend.web_mvp.api.services.create_osrm_provider_from_environment',
                              side_effect=lambda coordinates, **kw: CoordinateRoutingProvider(coordinates, speed_km_per_hour=30))
        self.provider.start()
        restored_provider = patch('backend.web_mvp.api_v2.services.optimization.create_osrm_provider_from_environment',
            side_effect=lambda coordinates, **kw: CoordinateRoutingProvider(coordinates, speed_km_per_hour=30))
        restored_provider.start()
        self.addCleanup(restored_provider.stop)
        self.addCleanup(self.provider.stop)

    def url(self, action):
        return f'/api/v2/{action}/?territory={self.territory.code}'

    def test_persistence_and_region_isolation(self):
        result = self.client.post(self.url('optimize'), {'ignore_task_statuses': True}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.territory.refresh_from_db()
        fresh = restore(self.territory)
        self.assertEqual(fresh._result.assigned_task_count, 56)
        self.assertIsNotNone(fresh._problem)
        payload = json.loads(OFFICIAL_DATASET_PATH.read_bytes())
        payload['territory_code'] = 'another'
        payload['territory_name'] = 'Другой район'
        second = import_dataset(json.dumps(payload).encode(), 'other.json')
        self.assertNotIn('result', second.response)
        with patch('backend.web_mvp.api.services.ORToolsOptimizer.optimize', side_effect=AssertionError('Повторный расчёт')):
            restored = self.client.get(self.url('dataset'))
        self.assertEqual(restored.data['result'], result.data['result'])
        self.assertEqual(len(self.client.get('/api/v2/territories/').data), 2)

    def test_creation_and_cancellation_survive_restore(self):
        response = self.client.post(self.url('tasks'), {
            'id':'NEW', 'work_type':'LOCAL', 'latitude':55.7, 'longitude':37.6,
            'window_start':'12:00', 'window_end':'18:00',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.post(self.url('replan'), {
            'event_type':'TASK_CANCELLED', 'task_id':'NEW', 'planning_time':'09:00',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.territory.refresh_from_db()
        self.assertEqual(next(t for t in restore(self.territory)._scenario.tasks if t.id=='NEW').status.value, 'CANCELLED')

    def test_manual_preview_confirm_and_stale_proposal(self):
        response = self.client.post(self.url('optimize'), {'ignore_task_statuses':True}, format='json')
        self.assertEqual(response.status_code, 200)
        preview = self.client.post(self.url('manual-reassignment/preview'), {
            'task_id':'yugo_tsentr-J78540', 'engineer_id':'yugo_tsentr-E02',
        }, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        confirmed = self.client.post(self.url('manual-reassignment/confirm'), {
            'proposal_id':preview.data['proposal_id'],
        }, format='json')
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        route = next(r for r in confirmed.data['result']['routes'] if r['engineer_id']=='yugo_tsentr-E02')
        self.assertIn('yugo_tsentr-J78540', [s['task_id'] for s in route['stops']])
        repeated = self.client.post(self.url('manual-reassignment/confirm'), {
            'proposal_id':preview.data['proposal_id'],
        }, format='json')
        self.assertEqual(repeated.status_code, 422)

    def test_emergency_unavailable_and_explanation(self):
        emergency = self.client.post(self.url('replan'), {
            'event_type':'EMERGENCY_TASK', 'planning_time':'09:00',
            'task':{'id':'URGENT', 'work_type':'EMERGENCY', 'latitude':55.7,
                    'longitude':37.6, 'window_start':'09:00', 'window_end':'20:00'},
        }, format='json')
        self.assertEqual(emergency.status_code, 200, emergency.data)
        engineer = next(r['engineer_id'] for r in emergency.data['result']['routes'] if r['stops'])
        unavailable = self.client.post(self.url('replan'), {
            'event_type':'ENGINEER_UNAVAILABLE', 'engineer_id':engineer, 'planning_time':'09:00',
        }, format='json')
        self.assertEqual(unavailable.status_code, 200, unavailable.data)
        route = next(r for r in unavailable.data['result']['routes'] if r['engineer_id']==engineer)
        self.assertEqual(route['stops'], [])
        with patch('LLM.query.explain_assignment', return_value='Проверенное объяснение.'):
            explanation = self.client.post(self.url('explain/URGENT'), {}, format='json')
        self.assertEqual(explanation.status_code, 200, explanation.data)
        self.assertIn('URGENT', explanation.data['explanation'])

    def test_failed_event_does_not_change_saved_state(self):
        old = self.client.get(self.url('dataset')).data
        response = self.client.post(self.url('replan'), {
            'event_type':'TASK_CANCELLED','task_id':'absent','planning_time':'09:00',
        }, format='json')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(old, self.client.get(self.url('dataset')).data)

    def test_colleague_viewsets_filters_selectors_and_persistent_rebuild(self):
        """CRUD/filters коллеги работают поверх того же persistent scenario."""
        engineers = self.client.get(
            f'/api/v2/engineers/?territory={self.territory.code}'
        )
        self.assertEqual(engineers.status_code, 200, engineers.data)
        self.assertEqual(len(engineers.data), 11)

        skills = self.client.get('/api/v2/selectors/skills/')
        self.assertEqual(skills.status_code, 200, skills.data)
        self.assertEqual(len(skills.data), 3)

        engineer = self.territory.engineers.order_by('id').first()
        changed = self.client.patch(
            f'/api/v2/engineers/{engineer.pk}/',
            {'start_address': 'Новый адрес офиса'},
            format='json',
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.territory.refresh_from_db()
        restored = restore(self.territory)
        engineer.refresh_from_db()
        self.assertEqual(engineer.start_address, 'Новый адрес офиса')
        self.assertIn(
            engineer.engineer_id,
            {item.id for item in restored._scenario.engineers},
        )
        self.assertIsNone(restored._result)

    def test_colleague_management_command_populates_persistent_state(self):
        """Команда ORM-импорта оставляет район готовым для planning API."""
        call_command(
            'load_dispatch_dataset', str(OFFICIAL_DATASET_PATH), verbosity=0
        )
        self.territory.refresh_from_db()
        restored = restore(self.territory)
        self.assertEqual(len(restored._scenario.engineers), 11)
        self.assertEqual(len(restored._scenario.tasks), 56)
        self.assertTrue(self.territory.response['dataset'])

    def test_official_reload_clears_state_and_imports_three_regions(self):
        """Повторная загрузка удаляет изменённый план и создаёт три района."""
        created = self.client.post(self.url('tasks'), {
            'id': 'TEMPORARY', 'work_type': 'LOCAL',
            'latitude': 55.7, 'longitude': 37.6,
            'window_start': '12:00', 'window_end': '18:00',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)

        response = self.client.post('/api/v2/dataset/official/', {}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Territory.objects.count(), 3)
        self.assertEqual(
            {item['code'] for item in response.data['reloaded_territories']},
            {'vostok', 'yugo_vostok', 'yugo_tsentr'},
        )
        reloaded = Territory.objects.get(code='yugo_tsentr')
        task_ids = {item['id'] for item in reloaded.response['dataset']['tasks']}
        self.assertNotIn('TEMPORARY', task_ids)
        self.assertNotIn('result', reloaded.response)

    def test_control_distribution_derives_time_from_in_progress_windows(self):
        """Контрольный режим берёт позднейшее начало окна активной работы."""
        expected = max(
            task.window_start
            for task in restore(self.territory)._scenario.tasks
            if task.status.value == 'IN_PROGRESS'
        )

        response = self.client.post(
            self.url('optimize'),
            {'ignore_task_statuses': False},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['planning_options']['planning_time'], expected)
