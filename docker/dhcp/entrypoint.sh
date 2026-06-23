#!/bin/sh
set -e

# Substitute environment variables into the dnsmasq config template.
# All variables have defaults that match the reference environment (192.0.2.0/24).
ZTP_SERVER_IP="${ZTP_SERVER_IP:-192.0.2.14}"
ZTP_WEB_PORT="${ZTP_WEB_PORT:-80}"
DHCP_RANGE_START="${DHCP_RANGE_START:-192.0.2.100}"
DHCP_RANGE_END="${DHCP_RANGE_END:-192.0.2.200}"
DHCP_ROUTER="${DHCP_ROUTER:-192.0.2.1}"
DHCP_DNS="${DHCP_DNS:-8.8.8.8,8.8.4.4}"
DHCP_INTERFACE="${DHCP_INTERFACE:-eth0}"

sed \
    -e "s|%%ZTP_SERVER_IP%%|${ZTP_SERVER_IP}|g" \
    -e "s|%%ZTP_WEB_PORT%%|${ZTP_WEB_PORT}|g" \
    -e "s|%%DHCP_RANGE_START%%|${DHCP_RANGE_START}|g" \
    -e "s|%%DHCP_RANGE_END%%|${DHCP_RANGE_END}|g" \
    -e "s|%%DHCP_ROUTER%%|${DHCP_ROUTER}|g" \
    -e "s|%%DHCP_DNS%%|${DHCP_DNS}|g" \
    /etc/dnsmasq.conf.tpl > /etc/dnsmasq.conf

# OpenGear assigns management IPs via old-style ifconfig aliases (e.g. net1:static8).
# getifaddrs() returns these under the alias name, so if_nametoindex("net1:static8") = 0,
# causing dnsmasq to see net1 as having no address and refuse to serve DHCP on it.
#
# Fix: delete the aliased address and re-add it directly on the interface (no alias label),
# so getifaddrs() returns it under the real interface name and dnsmasq can match it.
# Brief connectivity loss during the del→add is acceptable at container startup.
ALIAS_LABEL=$(ip -4 addr show dev "${DHCP_INTERFACE}" | awk "/inet ${ZTP_SERVER_IP}\\//{print \$NF}")
if [ -n "${ALIAS_LABEL}" ] && [ "${ALIAS_LABEL}" != "${DHCP_INTERFACE}" ]; then
    echo "[dhcp] ${ZTP_SERVER_IP} is on alias '${ALIAS_LABEL}'; re-adding on '${DHCP_INTERFACE}'"
    ip addr del "${ZTP_SERVER_IP}/24" dev "${DHCP_INTERFACE}"
    ip addr add "${ZTP_SERVER_IP}/24" brd + dev "${DHCP_INTERFACE}" scope global
fi

echo "[dhcp] Starting dnsmasq on interface ${DHCP_INTERFACE}"
echo "[dhcp] ZTP server: ${ZTP_SERVER_IP}"
echo "[dhcp] DHCP range: ${DHCP_RANGE_START} - ${DHCP_RANGE_END}"

exec dnsmasq --no-daemon --log-dhcp --interface="${DHCP_INTERFACE}"
