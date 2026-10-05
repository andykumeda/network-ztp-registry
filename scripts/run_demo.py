#!/usr/bin/env python3
"""Launch synthetic inventory with isolated state and disabled integrations."""
import importlib.util
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]


def configure_demo(root, state_dir):
    os.environ.update({
        'ITSM_ENABLED': 'false', 'ANSIBLE_RUN_ENABLED': 'false',
        'APP_BIND_HOST': '127.0.0.1', 'DB_PATH': str(state_dir / 'devices.db'),
        'POLLER_STATE_PATH': str(state_dir / 'poller-state.json'),
        'LOOKUP_SOURCE': 'csv', 'LOOKUP_CSV_PATH': str(root / 'model-sn.csv'),
        'SLOT_LOC_CSV_PATH': str(root / 'model-loc.csv'),
    })


def seed_missing_devices(client, devices):
    existing = {device['serial'] for device in client.get('/api/devices').get_json()}
    for device in devices:
        if device['serial'] not in existing:
            response = client.post('/api/devices', json=device)
            if response.status_code != 201:
                raise RuntimeError('Synthetic seed failed')
            existing.add(device['serial'])


def main():
    if sys.version_info < (3, 10):
        print('Python 3.10 or newer is required. See docs/demo.md.')
        return 1
    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', 5055))
    except OSError:
        print('Port 5055 is already in use. Use the running demo or stop it first.')
        return 1
    state_dir = ROOT / '.demo'
    state_dir.mkdir(exist_ok=True)
    configure_demo(ROOT, state_dir)
    sys.path.insert(0, str(ROOT))
    import server
    server.init_db()
    server.migrate_db()
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts/seed_demo.py')
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with server.app.test_client() as client:
        seed_missing_devices(client, seed.DEVICES)
    print('Synthetic demo: http://127.0.0.1:5055/')
    print('ITSM and Ansible disabled. Ctrl+C stops the server; data is preserved.')
    server.app.run(host='127.0.0.1', port=5055, debug=False, threaded=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
