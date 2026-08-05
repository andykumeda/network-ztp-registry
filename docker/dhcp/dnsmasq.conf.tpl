# dnsmasq DHCP configuration for Cisco Catalyst ZTP
# Values are substituted from environment variables at container startup.
# See .env.example for the full list of variables.

# Don't use the host's /etc/resolv.conf or /etc/hosts
no-resolv
no-hosts

# Bind only to the ZTP server address so dnsmasq finds the right interface
# even when the IP is assigned to an interface alias (e.g. net1:static8).
listen-address=%%ZTP_SERVER_IP%%
bind-interfaces

# DHCP lease range and duration
dhcp-range=%%DHCP_RANGE_START%%,%%DHCP_RANGE_END%%,255.255.255.0,8h

# Default gateway
dhcp-option=option:router,%%DHCP_ROUTER%%

# DNS servers (switches use these for domain resolution after provisioning)
dhcp-option=option:dns-server,%%DHCP_DNS%%

# ── Cisco Zero Touch Provisioning ──────────────────────────────────────────────
#
# Option 67 (boot-file-name): the switch's PnP agent downloads this URL and
# executes it as the ZTP script.  ztp.py reads the BOOT environment variable
# (set by the PnP agent to this URL) to derive the ZTP server IP, so this
# value must point at the correct server address.
dhcp-option=option:bootfile-name,"http://%%ZTP_SERVER_IP%%:%%ZTP_WEB_PORT%%/ztp.py"

# Log all DHCP transactions (visible via docker logs ztp-dhcp)
log-dhcp
