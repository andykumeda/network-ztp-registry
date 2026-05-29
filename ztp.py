import cli
import os
import time
import re
import json
import urllib.request
from urllib.parse import urlparse


def ios_configure(commands):
    """Apply IOS configuration commands.

    Tries 'copy file running-config' first (works on C9300X and most platforms).
    Falls back to cli.configurep() if that fails (C9410R -- configurep prints
    errors but does not crash the script).
    """
    if isinstance(commands, str):
        commands = [commands]
    filtered = [c for c in commands if c.strip().lower() != 'end']
    if not filtered:
        return

    # Approach 1: write to file, merge via exec-mode copy
    cfg_path = '/bootflash/guest-share/ztp_apply.cfg'
    ios_path = 'bootflash:guest-share/ztp_apply.cfg'
    try:
        with open(cfg_path, 'w') as f:
            f.write('\n'.join(filtered) + '\n')
        cli.cli(f'copy {ios_path} running-config\n')
        return
    except Exception:
        pass
    finally:
        try:
            os.remove(cfg_path)
        except Exception:
            pass

    # Approach 2: cli.configurep -- does not raise on failure
    cli.configurep(filtered)

print("\n\n   *** Catalyst 9000 Zero Touch Provisioning Script ***   \n\n")

# --- Derive ZTP server base URL from DHCP BOOT URL ---
# Use netloc (host:port) so non-standard ports (e.g. 8080) are preserved.
# Fallback values are substituted at container startup by docker/web/entrypoint.sh;
# they are never the literal placeholder strings when served to a switch.
_ztp_server_ip = "%%ZTP_SERVER_IP%%"               # fallback host for registry API
_ztp_base_url  = "http://%%ZTP_SERVER_IP%%:%%ZTP_WEB_PORT%%"  # fallback for HTTP downloads
try:
    _boot_url = os.environ.get("BOOT", "")
    if _boot_url:
        _parsed = urlparse(_boot_url)
        if _parsed.hostname:
            _ztp_server_ip = _parsed.hostname
            # Reconstruct base URL preserving port (e.g. http://10.10.10.10:8080)
            _ztp_base_url = f"{_parsed.scheme}://{_parsed.netloc}"
except Exception:
    pass

# --- Fetch config.json from ZTP server ---
print(f"ZTP-DEBUG: BOOT={os.environ.get('BOOT', '<not set>')} base={_ztp_base_url}")
with urllib.request.urlopen(f"{_ztp_base_url}/config.json", timeout=10) as _r:
    _cfg = json.loads(_r.read())

required_version     = _cfg["required_ios_version"]
image_name           = _cfg["ios_image_name"]
ios_image_md5        = _cfg.get("ios_image_md5")
domain_name          = _cfg["domain_name"]
priv15_user          = _cfg["priv15_user"]
priv15_user_secret   = _cfg["priv15_user_secret"]
ansible_user         = _cfg["ansible_user"]
ansible_user_secret  = _cfg["ansible_user_secret"]
enable_secret        = _cfg["enable_secret"]
management_interface = _cfg["management_interface"]
print(f"ZTP config loaded: version={required_version} image={image_name}")

try:
    print ("Configure dynamic hostname\n\n")

    # Get the IP address assigned to management interface
    output = cli.cli(f"show ip interface brief | include {management_interface}")

    ### Get IP and switch model to set hostname to be unique

    # Step 1: Get full 'show version' output
    version_output = cli.cli("show version")

    # Priority 1: Match 'Model Number : C9606R'
    model_match = re.search(r'Model Number\s+:\s+(C9\d{3,4}[\w\-]*)', version_output)

    # Priority 2: If not found, match 'cisco C9606R ...'
    if not model_match:
        model_match = re.search(r'cisco\s+(C9\d{3,4}[\w\-]*)', version_output, re.IGNORECASE)

    # Priority 3: Fallback — match from Switch Ports Model table
    if not model_match:
        model_match = re.search(r'\*?\s*\d+\s+\d+\s+(C9\d{3,4}[\w\-]*)', version_output)

    # Final fallback
    switch_model = model_match.group(1) if model_match else "UNKNOWN"

    # Extract serial number for OpenGear log parsing
    serial_match = re.search(r'Processor board ID (\S+)', version_output)
    serial = serial_match.group(1) if serial_match else "UNKNOWN"
    print(f"ZTP-SERIAL: {serial}")
    print(f"ZTP-MODEL: {switch_model}")
    print(f"ZTP-PROGRESS: Detected {switch_model} (SN: {serial})")

    # Step 2: Look up the assigned hostname from the ZTP server registry.
    # Falls back to a generated name if the serial is not in the lookup table.
    _hostname_from_lookup = None
    try:
        with urllib.request.urlopen(
                f"http://{_ztp_server_ip}:5000/api/lookup/{serial}", timeout=5) as _r:
            _lookup = json.loads(_r.read())
            _hostname_from_lookup = _lookup.get('hostname')
    except Exception:
        pass  # Server unreachable or serial not found — use generated fallback

    # Step 3: Extract number (e.g., 9600 from C9606R)
    model_number_match = re.search(r'C(\d+)', switch_model)
    model_number = model_number_match.group(1) if model_number_match else switch_model

    # Step 4: Get last octet of DHCP IP (used as fallback if lookup returned nothing)
    ip_output = cli.cli(f"show ip interface brief | include {management_interface}")
    ip_match = re.search(r'(\d+\.\d+\.\d+)\.(\d+)', ip_output)
    last_octet = ip_match.group(2) if ip_match else "000"

    # Step 5: Set hostname — use registry name if available, else generated fallback
    final_hostname = _hostname_from_lookup or f"{model_number}-ZTP-{last_octet}"
    ios_configure([f"hostname {final_hostname}"])
    print(f"Success: Hostname set to: {final_hostname}")
    print(f"ZTP-PROGRESS: Hostname set to {final_hostname}")

    ios_configure(["ip routing"])
    ios_configure([f"ip domain name {domain_name}"])

    ios_configure([f"username {priv15_user} privilege 15 secret {priv15_user_secret}"])
    ios_configure([f"username {ansible_user} privilege 15 secret {ansible_user_secret}"])
    ios_configure([f"enable secret {enable_secret}"])

    ios_configure(["ip ssh version 2"])

    ios_configure(["line vty 0 15" , "login local", "transport input ssh", "end"])

    ios_configure(["netconf-yang", "end"])
    ios_configure(["iox", "end"])
    print("ZTP-PROGRESS: Credentials, SSH, NETCONF, IOX configured")

    print ("\n\n *** IP Address of Management Interface  *** \n\n")
    cli_command = f"show ip int {management_interface} | incl Internet"
    cli.executep(cli_command)

    ##############

    # Get the current IOS version
    print ("\n\n *** Checking IOS Version  *** \n\n")
    ios_version = cli.cli("show version | include IOS Software").strip()
    print(f"Current IOS Version: {ios_version}")
    version_num_m = re.search(r'Version (\S+),', ios_version)
    version_num = version_num_m.group(1) if version_num_m else ios_version
    print(f"ZTP-VERSION: {version_num}")

    print("ZTP-PROGRESS: Collecting hardware inventory")
    # Capture hardware inventory (chassis, supervisors, line cards, network modules)
    try:
        inv_output = cli.cli("show inventory")
        inv_items = []
        cur_inv = {}
        for inv_line in inv_output.split('\n'):
            inv_line = inv_line.strip()
            nm = re.match(r'NAME:\s*"([^"]+)"', inv_line)
            pm = re.match(r'PID:\s*(\S+)\s*,\s*VID:\s*\S*\s*,\s*SN:\s*(\S*)', inv_line)
            if nm:
                if cur_inv.get('pid'):
                    inv_items.append(cur_inv)
                slot_m = re.search(r'[Ss]lot\s+(\d+)', nm.group(1))
                cur_inv = {'name': nm.group(1)}
                if slot_m:
                    cur_inv['slot'] = slot_m.group(1)
            elif pm and cur_inv is not None:
                pid = pm.group(1).strip()
                sn  = pm.group(2).strip()
                # Only keep Catalyst 9000 series chassis/modules, plus Power Supplies and Fans
                if pid and re.match(r'(C9[0-9]|PWR|FAN)', pid):
                    cur_inv['pid'] = pid
                    cur_inv['sn']  = sn
        if cur_inv.get('pid'):
            inv_items.append(cur_inv)
        # Deduplicate: some platforms (C9300X stack, C9410R) report the same
        # chassis PID/SN under multiple NAME entries (e.g. "c93xx Stack" + "Switch 1")
        seen_hw = set()
        unique_items = []
        for item in inv_items:
            key = (item['pid'], item.get('sn', ''))
            if key not in seen_hw:
                seen_hw.add(key)
                unique_items.append(item)
        # Print each item on its own line — single-line JSON can exceed
        # the OpenGear portlog line-length limit (~1000 chars) causing truncation.
        print(f"ZTP-INV-BEGIN: {len(unique_items)}")
        for _idx, _item in enumerate(unique_items):
            print(f"ZTP-INV-ITEM-{_idx}: {json.dumps(_item)}")
        print("ZTP-INV-END")
    except Exception as inv_e:
        print(f"ZTP-INVENTORY-ERROR: {inv_e}")

    def ver_tuple(v):
        return tuple(int(x) for x in re.findall(r'\d+', v)[:3])

    current_ver = ver_tuple(version_num)
    required_ver = ver_tuple(required_version)

    if current_ver == required_ver:
        print(f"\n\n IOS {version_num} == {required_version}. No upgrade needed.\n\n")
        print("ZTP-PROGRESS: IOS current - staging complete")
    else:
        print(f"Upgrading IOS from {version_num} to {required_version} via TFTP...")
        print(f"ZTP-PROGRESS: Staging IOS upgrade to {required_version}")

        # Check both flash: and bootflash: (chassis platforms use bootflash:)
        image_found = False
        image_store = 'flash:'
        for storage in ['flash:', 'bootflash:']:
            try:
                dir_check = cli.cli(f"dir {storage}{image_name}")
                if image_name in dir_check and '%Error' not in dir_check:
                    image_found = True
                    image_store = storage
                    break
            except Exception:
                pass

        if image_found:
            print(f"\n\n   *** Image {image_name} already in {image_store}, skipping download ***   \n\n")
        else:
            # Determine which storage is available for the copy
            for storage in ['flash:', 'bootflash:']:
                try:
                    cli.cli(f"dir {storage}")
                    image_store = storage
                    break
                except Exception:
                    pass
            print(f"\n\n   *** Copy image to {image_store} ***   \n\n")
            print(f"ZTP-PROGRESS: Downloading {image_name} (this may take several minutes)")
            # Suppress destination filename prompt and overwrite confirmation
            # (this is a global config command, not exec)
            ios_configure(["file prompt quiet"])
            # Try HTTP first (faster, more reliable), fall back to TFTP
            copy_ok = False
            for proto in [f"{_ztp_base_url}/{image_name}",
                          f"tftp://{_ztp_server_ip}/{image_name}"]:
                try:
                    print(f"Trying: copy {proto} {image_store}{image_name}")
                    cli.executep(f"copy {proto} {image_store}{image_name}")
                    copy_ok = True
                    break
                except Exception as copy_err:
                    print(f"Copy failed ({proto}): {copy_err}")
            try:
                ios_configure(["no file prompt quiet"])
            except Exception:
                pass
            if not copy_ok:
                print(f"ZTP-FAILURE: Could not download {image_name}")
                raise RuntimeError(f"Image download failed for {image_name}")
            time.sleep(10)

        # Verify image exists before proceeding with upgrade
        try:
            verify_check = cli.cli(f"dir {image_store}{image_name}")
            image_verified = image_name in verify_check and '%Error' not in verify_check
        except Exception:
            image_verified = False

        if not image_verified:
            print(f"\n\n   *** ERROR: Image {image_name} not found in {image_store} after copy. Skipping upgrade. ***\n\n")
            print("ZTP-PROGRESS: Image not found on flash - upgrade skipped")
        else:

            # ── Bundle-mode upgrade: set boot variable and reload ──
            # Avoids `install add file ... activate commit` which hangs
            # inside EEM.  Bundle mode boots directly from the .bin image.
            print("\n\n   *** Setting boot variable to new image ***   \n\n")
            print("ZTP-PROGRESS: Setting boot variable for upgrade")
            ios_configure(["no boot system",
                           f"boot system {image_store}{image_name}",
                           "end"])
            cli.executep("write memory")
            time.sleep(5)

            print("\n\n   *** Triggering reload for upgrade ***   \n\n")
            print("ZTP-PROGRESS: Upgrade triggered - device will reboot")

            # Try direct reload first — send newlines to answer [confirm]
            try:
                cli.cli("reload\n\n")
            except Exception:
                pass

            # If cli.cli didn't trigger the reload (prompt not answered),
            # fall back to a minimal EEM applet that just reloads.
            # Unlike the install EEM, this completes in seconds.
            try:
                eem_commands = ['event manager applet ZTP_RELOAD',
                                'event none maxrun 60',
                                'action 1.0 cli command "enable"',
                                'action 2.0 cli command "reload" pattern "confirm"',
                                'action 3.0 cli command "y"',
                                ]
                ios_configure(eem_commands)
                cli.executep("write memory")
                time.sleep(5)
                cli.executep("event manager run ZTP_RELOAD")
            except Exception:
                pass

            # Keep script alive so PnP's post-script auto-reset cannot
            # interrupt the reload.  The reload kills this sleep.
            time.sleep(900)

    print("\n\n   *** Script complete ***   \n\n")
    print("\n\n   *** If you see this, just wait.  It will take a few minutes for the installation to start. ***   \n\n")

except Exception as ztp_err:
    # Emit a structured failure marker so the OpenGear poller can surface it in the UI
    err_type = type(ztp_err).__name__
    err_msg  = str(ztp_err).replace('\n', ' ').strip()
    print(f"ZTP-FAILURE: {err_type}: {err_msg}")
    print(f"ZTP-PROGRESS: FAILED - {err_type}: {err_msg}")
    raise
