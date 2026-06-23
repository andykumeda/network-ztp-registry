# Ansible Network Automation

Professional Ansible playbooks for managing Cisco network infrastructure (IOS-XE and NX-OS devices).

## Features

- **Multi-Platform Support**: Auto-detects and configures both IOS-XE (Catalyst switches, ISR routers) and NX-OS (Nexus switches)
- **Security-First Design**: Ansible Vault integration, SSH key authentication, no_log for sensitive data
- **Production-Ready**: Idempotent, error handling, proper state management
- **Modular Architecture**: Organized playbooks with tag-based selective execution
- **Comprehensive Coverage**: User management, backups, baseline config, monitoring, reporting

## Quick Start

### Prerequisites

- Ansible 2.9+ with Cisco collections:
  ```bash
  ansible-galaxy collection install cisco.ios
  ansible-galaxy collection install cisco.nxos
  ```
- Network devices accessible via SSH
- Ansible Vault password file (for encrypted variables)

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/ansible-network-automation.git
   cd ansible-network-automation
   ```

2. **Configure inventory**:
   ```bash
   cp inventory.example hosts
   # Edit hosts file with your device IPs and groups
   ```

3. **Configure variables**:
   ```bash
   cp playbooks/group_vars/all.example playbooks/group_vars/all
   # Edit group_vars/all with your environment settings
   # Encrypt sensitive values with ansible-vault
   ```

4. **Set up vault password**:
   ```bash
   echo "your_vault_password" > ~/.ansible/vault_pass.txt
   chmod 600 ~/.ansible/vault_pass.txt
   # Update ansible.cfg to point to your vault password file
   ```

## Usage

### Run Complete Site Configuration
```bash
ansible-playbook playbooks/site.yml
```

### Run Specific Configurations
```bash
# Only configure users
ansible-playbook playbooks/site.yml --tags users

# Only baseline configuration
ansible-playbook playbooks/site.yml --tags common

# Only SNMP configuration
ansible-playbook playbooks/site.yml --tags snmp
```

### Target Specific Devices
```bash
# Run on specific location
ansible-playbook playbooks/site.yml --limit dc1

# Run on specific device type
ansible-playbook playbooks/site.yml --limit switches

# Combine location and type
ansible-playbook playbooks/site.yml --limit "dc1&switches"
```

### Backup Configurations
```bash
ansible-playbook playbooks/backup_configs.yml
# Backups saved to ./backups/<hostname>_<timestamp>.cfg
```

### Check Version Compliance
```bash
ansible-playbook playbooks/version_checker.yml
# Report saved to playbooks/upgrade_report.txt
```

## Playbook Overview

### Core Playbooks

| Playbook | Purpose | Key Features |
|----------|---------|--------------|
| `site.yml` | Main orchestration | Runs all site configurations with tags |
| `common.yml` | Baseline infrastructure | Banner, DNS, NTP, SSH, timezone, crypto keys |
| `users_unified.yml` | User management | Multi-platform, SSH keys, auto-cleanup |
| `backup_configs.yml` | Configuration backup | Timestamped backups, multi-platform |
| `version_checker.yml` | Version reporting | OS version compliance checking |
| `snmpv3.yml` | SNMP configuration | SNMPv3 with auth and encryption |
| `logging.yml` | Syslog configuration | Centralized logging setup |

### Utility Playbooks

Located in `playbooks/utilities/`:
- `passchange.yml` - Change ansible user password
- `rename_user.yml` - Generic user rename/replacement
- `disable_mcpuser.yml` - Disable specific user account
- `remove_pubkey.yml` - Remove SSH public keys

## Architecture

### Inventory Structure
```
hosts
├── Location Groups (dc1, dc2, lab)
└── Functional Groups (switches, routers, core)
```

### Variable Hierarchy
```
group_vars/
├── all              # Global variables (encrypted with Ansible Vault)
├── all.example      # Example template
└── users            # User definitions (encrypted with Ansible Vault)
```

### Playbook Organization
```
playbooks/
├── site.yml                    # Main orchestration
├── common.yml                  # Baseline config
├── users_unified.yml           # User management
├── backup_configs.yml          # Config backups
├── version_checker.yml         # Version reporting
├── snmpv3.yml                  # SNMP config
├── logging.yml                 # Syslog config
├── utilities/                  # One-off utilities
└── group_vars/                 # Variable files
```

## Security Best Practices

- **Ansible Vault**: All sensitive data (passwords, SNMP community strings) encrypted
- **SSH Keys**: Preferred authentication method for users
- **no_log**: Prevents sensitive data from appearing in logs
- **Type 9 Passwords**: Uses scrypt hashing for IOS-XE (most secure)
- **SNMPv3**: Authentication and encryption enabled
- **SSH v2**: Enforced on all devices

## Skills Demonstrated

- **Multi-Vendor Automation**: IOS-XE and NX-OS platform abstraction
- **Advanced Ansible**: Conditionals, loops, facts, delegation, vault integration
- **Network Modules**: ios_user, ios_config, ios_banner, ios_system, nxos_user, etc.
- **Idempotent Design**: Safe for repeated execution
- **Error Handling**: Graceful failures and validation
- **Modular Architecture**: Reusable, organized, maintainable code
- **Security Focus**: Vault encryption, SSH keys, secure protocols

## Requirements

- Ansible 2.9+
- Python 3.6+
- Cisco IOS-XE devices (Catalyst 9000 series tested)
- Cisco NX-OS devices (Nexus 9000 series tested)
- SSH access to network devices
- Privilege 15 / network-admin access

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Test your changes
4. Submit a pull request

## Author

Network automation playbooks developed for enterprise Cisco infrastructure management.

## Acknowledgments

- Cisco Ansible Collections: cisco.ios and cisco.nxos
- Ansible Community for best practices and modules
