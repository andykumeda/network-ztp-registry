#!/bin/bash
# health-check.sh — verify all ZTP services are running on a host
#
# Usage:
#   ./health-check.sh --host 192.0.2.14                    check Linux server (direct)
#   ./health-check.sh --host 192.0.2.253                   check OpenGear (direct)
#   ./health-check.sh --host 192.0.2.253 --via 192.0.2.14   check OpenGear via proxy
#
# --via: run HTTP checks over SSH on an intermediate host (useful when the target
#        is not directly reachable from the local machine over HTTP).
#        SSH to the target for the container check still uses your local SSH config
#        (ProxyJump etc.) as normal.
#
# Exit code: 0 if all checks pass, 1 if any fail.

HOST=""
VIA=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --via)  VIA="$2";  shift 2 ;;
    *)
      echo "Usage: $0 --host <ip> [--via <proxy-ip>]"
      exit 1
      ;;
  esac
done

if [[ -z "$HOST" ]]; then
  echo "Error: --host is required."
  echo "Usage: $0 --host <ip> [--via <proxy-ip>]"
  exit 1
fi

# Determine SSH user based on host
case "$HOST" in
  192.0.2.14)  SSH_USER="ztpadmin" ;;
  192.0.2.253) SSH_USER="root" ;;
  *)               SSH_USER="root" ;;
esac

# Determine proxy SSH user
case "$VIA" in
  192.0.2.14)  VIA_USER="ztpadmin" ;;
  *)               VIA_USER="root" ;;
esac

PASS=0
FAIL=0

http_check() {
  local label="$1"
  local url="$2"
  local http_code

  if [[ -n "$VIA" ]]; then
    # Run curl on the proxy host — pass args directly (no quoted string) to avoid
    # quoting issues with %{http_code} through the SSH command channel
    http_code=$(ssh -o ConnectTimeout=5 -o BatchMode=yes \
      "${VIA_USER}@${VIA}" \
      curl -s -o /dev/null --write-out '%{http_code}' --connect-timeout 5 "${url}" \
      2>/dev/null)
  else
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null)
  fi

  if [[ "$http_code" == "200" ]]; then
    echo "  [PASS] ${label}"
    ((PASS++))
  else
    echo "  [FAIL] ${label} — HTTP ${http_code:-no response} (${url})"
    ((FAIL++))
  fi
}

container_check() {
  local label="$1"
  local name_filter="$2"
  local result
  result=$(ssh -o ConnectTimeout=5 -o BatchMode=yes \
    "${SSH_USER}@${HOST}" \
    "docker ps --filter name=${name_filter} --filter status=running --format '{{.Names}}'" \
    2>/dev/null)
  if echo "$result" | grep -q "$name_filter"; then
    echo "  [PASS] ${label}"
    ((PASS++))
  else
    echo "  [FAIL] ${label} — container not running"
    ((FAIL++))
  fi
}

echo "ZTP health check — ${HOST}${VIA:+ (HTTP via ${VIA})}"
echo "─────────────────────────────────"

http_check    "Registry API   " "http://${HOST}:5000/api/devices"
http_check    "Web / nginx     " "http://${HOST}:8080/config.json"
http_check    "Live sessions   " "http://${HOST}:5000/api/live-sessions"
container_check "DHCP container " "dhcp"

echo "─────────────────────────────────"

if [[ $FAIL -eq 0 ]]; then
  echo "  All checks passed (${PASS}/${PASS})"
  exit 0
else
  echo "  ${FAIL} check(s) failed — see above"
  exit 1
fi
