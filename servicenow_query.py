#!/usr/bin/env python3
"""Query ServiceNow to inspect records pushed by ZTP.

Tries ServiceNow's standard Table API against `u_mgn_staging`. Requires the
service account to have read access on the import table. If that fails, the
script also tries a GET on the custom scripted REST endpoint as a fallback.

Usage:
  python3 servicenow_query.py                # last 10 records (cmdb_ci_ip_switch)
  python3 servicenow_query.py <serial>       # filter by serial_number
  python3 servicenow_query.py --limit 50     # bump result cap
  python3 servicenow_query.py --raw          # dump full JSON, no summary
  python3 servicenow_query.py --table u_mgn_staging   # override table

Credentials are read from the environment (or from /opt/ztp/.env if present):
  SERVICENOW_URL   — full scripted REST endpoint (used to derive instance host)
  SERVICENOW_USER
  SERVICENOW_PASS
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _load_dotenv(path: str) -> None:
    """Populate os.environ from a .env file if present. Only sets keys that
    aren't already in the environment."""
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f'{user}:{password}'.encode()).decode()
    return f'Basic {token}'


def _instance_host(scripted_url: str) -> str:
    """Extract `https://<instance>.service-now.com` from the scripted REST URL."""
    p = urllib.parse.urlparse(scripted_url)
    if not p.scheme or not p.netloc:
        raise SystemExit(f'SERVICENOW_URL looks malformed: {scripted_url!r}')
    return f'{p.scheme}://{p.netloc}'


def _http_get(url: str, auth: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        method='GET',
        headers={'Accept': 'application/json', 'Authorization': auth},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _query_table_api(host: str, auth: str, table: str,
                     serial: str | None, limit: int) -> list:
    """Standard ServiceNow Table API query."""
    params = {
        'sysparm_limit':         str(limit),
        'sysparm_display_value': 'true',
        'sysparm_exclude_reference_link': 'true',
    }
    if serial:
        # ServiceNow supports `field=value` or encoded query string
        params['sysparm_query'] = f'serial_number={serial}^ORDERBYDESCsys_created_on'
    else:
        params['sysparm_query'] = 'ORDERBYDESCsys_created_on'
    url = f'{host}/api/now/table/{table}?{urllib.parse.urlencode(params)}'
    data = _http_get(url, auth)
    return data.get('result', [])


def _summarize(records: list) -> None:
    if not records:
        print('No records found.')
        return
    # Candidate fields across both our push payload (u_mgn_staging) and the
    # CMDB destination table (cmdb_ci_ip_switch). Only fields actually present
    # in the first record are rendered, so one summarizer works for both.
    candidates = [
        'serial_number', 'name', 'hostname', 'model_number', 'model',
        'ip_address', 'u_building', 'building', 'u_room', 'room',
        'install_status', 'status', 'provisioned_at', 'sys_updated_on', 'sys_created_on',
    ]
    fields = [f for f in candidates if f in records[0]]
    widths = {f: max(len(f), *(len(str(r.get(f, ''))) for r in records)) for f in fields}
    header = '  '.join(f.ljust(widths[f]) for f in fields)
    print(header)
    print('-' * len(header))
    for r in records:
        print('  '.join(str(r.get(f, '')).ljust(widths[f]) for f in fields))
    print(f'\n{len(records)} record(s).')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('serial', nargs='?', help='filter by serial_number')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--table', default='cmdb_ci_ip_switch',
                        help='ServiceNow table to query (default: cmdb_ci_ip_switch)')
    parser.add_argument('--raw', action='store_true',
                        help='dump full JSON response instead of summary')
    args = parser.parse_args()

    _load_dotenv('/opt/ztp/.env')

    url  = os.environ.get('SERVICENOW_URL', '').strip()
    user = os.environ.get('SERVICENOW_USER', '').strip()
    pwd  = os.environ.get('SERVICENOW_PASS', '')
    if not (url and user and pwd):
        print('ERROR: SERVICENOW_URL, SERVICENOW_USER, SERVICENOW_PASS must be set',
              file=sys.stderr)
        return 2

    auth = _auth_header(user, pwd)
    host = _instance_host(url)

    print(f'Querying {host}/api/now/table/{args.table} '
          f'(serial={args.serial or "<any>"} limit={args.limit})\n')

    try:
        records = _query_table_api(host, auth, args.table, args.serial, args.limit)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:500]
        print(f'HTTP {e.code} from Table API: {body}', file=sys.stderr)
        if e.code in (401, 403):
            print('\nService account may not have read access on u_mgn_staging.',
                  file=sys.stderr)
            print('Ask the SN admin for `rest_service` or read on the staging table.',
                  file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f'Network error: {e.reason}', file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(records, indent=2, default=str))
    else:
        _summarize(records)
    return 0


if __name__ == '__main__':
    sys.exit(main())
