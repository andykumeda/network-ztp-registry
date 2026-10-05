import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('run_demo', ROOT / 'scripts/run_demo.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class DemoRunnerTests(unittest.TestCase):
    def test_configuration_disables_inherited_integrations(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'ITSM_ENABLED': 'true', 'ANSIBLE_RUN_ENABLED': 'true',
            'DB_PATH': 'existing-user-database.db', 'LOOKUP_SOURCE': 'none',
        }):
            state = Path(tmp)
            runner.configure_demo(ROOT, state)
            self.assertEqual(os.environ['ITSM_ENABLED'], 'false')
            self.assertEqual(os.environ['ANSIBLE_RUN_ENABLED'], 'false')
            self.assertEqual(os.environ['DB_PATH'], str(state / 'devices.db'))
            self.assertEqual(os.environ['LOOKUP_SOURCE'], 'csv')

    def test_reseeding_preserves_edits_without_duplicate_serials(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_db, old_state = server.DB, server.POLLER_STATE
            try:
                server.DB = str(Path(tmp) / 'devices.db')
                server.POLLER_STATE = str(Path(tmp) / 'poller-state.json')
                server.init_db()
                server.migrate_db()
                devices = [{'serial': 'SYNTHETIC-DEMO', 'hostname': 'DEMO',
                            'model': 'DEMO', 'asset_tag': ''}]
                with server.app.test_client() as client:
                    runner.seed_missing_devices(client, devices)
                    device_id = client.get('/api/devices').get_json()[0]['id']
                    response = client.put(f'/api/devices/{device_id}', json={'asset_tag': 'KEPT'})
                    self.assertEqual(response.status_code, 200)
                    runner.seed_missing_devices(client, devices)
                    saved = client.get('/api/devices').get_json()
                    self.assertEqual(len(saved), 1)
                    self.assertEqual(saved[0]['asset_tag'], 'KEPT')
            finally:
                server.DB, server.POLLER_STATE = old_db, old_state

    def test_busy_port_exits_before_state_setup(self):
        with patch.object(runner.socket, 'socket') as socket, \
                patch.object(runner, 'configure_demo') as configure:
            socket.return_value.__enter__.return_value.bind.side_effect = OSError('busy')
            self.assertEqual(runner.main(), 1)
            configure.assert_not_called()
