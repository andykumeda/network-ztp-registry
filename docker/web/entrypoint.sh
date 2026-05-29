#!/bin/sh
set -e

ZTP_SERVER_IP="${ZTP_SERVER_IP:-10.10.10.10}"
ZTP_WEB_PORT="${ZTP_WEB_PORT:-80}"

# Substitute server IP and port into the ztp.py template so switches that
# don't receive the BOOT env var (older IOS / Python 3.6) still reach the
# correct server via the hardcoded fallback in the script.
# Write to /var/cache/ztp/ — the html root is a read-only bind mount.
mkdir -p /var/cache/ztp
sed \
    -e "s|%%ZTP_SERVER_IP%%|${ZTP_SERVER_IP}|g" \
    -e "s|%%ZTP_WEB_PORT%%|${ZTP_WEB_PORT}|g" \
    /etc/nginx/ztp.py.tpl > /var/cache/ztp/ztp.py

echo "[web] ztp.py ready — server=${ZTP_SERVER_IP} port=${ZTP_WEB_PORT}"

exec nginx -g "daemon off;"
