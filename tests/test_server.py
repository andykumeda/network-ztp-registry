import os
from pathlib import Path
import tempfile
import unittest


os.environ['ANSIBLE_RUN_ENABLED'] = 'false'
os.environ['ITSM_ENABLED'] = 'false'

import server


class ServerPortfolioTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        server.DB = str(Path(self.temp_dir.name) / 'devices.db')
        server.POLLER_STATE = str(Path(self.temp_dir.name) / 'poller-state.json')
        server.ANSIBLE_RUN_ENABLED = False
        server.init_db()
        server.migrate_db()
        self.client = server.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_device(self, **overrides):
        payload = {
            'hostname': 'DEMO-SWITCH-001',
            'model': 'C9300-DEMO-48',
            'serial': 'SYNTHETIC-DEMO',
            'ip_address': '192.0.2.101',
            'building': 'DEMO-A',
            'room': 'AREA-01',
        }
        payload.update(overrides)
        response = self.client.post('/api/devices', json=payload)
        self.assertEqual(response.status_code, 201)
        return response.get_json()['id']

    def test_device_round_trip_and_security_headers(self):
        self.create_device()

        response = self.client.get('/api/devices')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0]['hostname'], 'DEMO-SWITCH-001')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        self.create_device(notes='=HYPERLINK("https://example.invalid")')

        response = self.client.get('/api/devices/export.csv')

        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.get_data(as_text=True))

    def test_ansible_execution_is_disabled_by_default(self):
        device_id = self.create_device()

        response = self.client.post(
            '/api/ansible/run',
            json={'device_id': device_id, 'playbook': '---\n- hosts: all'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('disabled', response.get_json()['error'].lower())


if __name__ == '__main__':
    unittest.main()
