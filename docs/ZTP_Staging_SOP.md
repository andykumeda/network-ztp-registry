# Switch Staging Standard Operating Procedure

**Zero Touch Provisioning (ZTP) — Cisco Catalyst 9000 Series**

---

## 1. Purpose & Scope

This SOP describes how to stage Cisco Catalyst 9000-series switches using the Network Zero Touch Provisioning (ZTP) system. ZTP automatically applies the base configuration and correct IOS-XE version. The staging operator cables the device, enters the asset tag (MTAG) into the registry, prints the label, and repackages the switch.

Supported models:

- Cisco Catalyst C9300 / C9300X (24- and 48-port access switches)
- Cisco Catalyst C9410R (modular chassis, up to 8 power supplies)
- Cisco Catalyst C9606R (modular chassis)

Up to 7 switches can be staged simultaneously.

---

## 2. Prerequisites

### Equipment & Cables

- Windows laptop connected to the ZTP network (192.0.2.0/24)
- PuTTY (or equivalent SSH terminal application) — for optional console monitoring
- Web browser (Chrome or Edge recommended)
- Console cables — RJ45 rollover, one per switch
- Ethernet patch cables — one per switch
- Label printer loaded with 4" × 6" labels

### System Access

- ZTP Dashboard URL: **http://192.0.2.253:8080**
- OpenGear console server IP: **192.0.2.253**

> **NOTE:** The dashboard URL may change if the ZTP host is updated. Confirm the current URL with your supervisor if the page does not load.

---

## 3. Physical Connections

Perform the following steps for each switch. The OpenGear CM8100 console server supports up to 7 simultaneous staging sessions (console ports 2–8).

1. **Connect the console cable:** Run an RJ45 rollover cable from the switch CONSOLE port to an available OpenGear console port (ports 2–8). Note the port number.
2. **Connect the Ethernet cable:** Run an Ethernet patch cable from the switch GigabitEthernet0/0 port to the OpenGear Ethernet port that corresponds to the same numbered slot.
3. **Connect all power supplies:** Plug in ALL power supply cables. See Section 8 for model-specific PSU counts.

> **IMPORTANT:** Do NOT connect the switch to any other network ports during staging. Only GigabitEthernet0/0 should be connected, and only to the OpenGear.

---

## 4. Power On and Monitor

1. Power on the switch(es) by connecting the power cables to a live outlet.
2. **(Optional) Monitor console output via PuTTY:**
    - Open PuTTY → Connection type: SSH
    - Host Name: `192.0.2.253` → Open
    - Log in with your OpenGear credentials
    - Type: `connect portN` (where N is the port number from Step 3.1)
    - You will see boot output scrolling — no action required
3. ZTP runs automatically. Do not interact with the switch console during provisioning.
4. Wait for provisioning to complete. Expected durations:
    - Base provisioning (no IOS upgrade): ~5–10 minutes
    - IOS upgrade required: additional ~15–20 minutes (switch will reboot automatically)

> **NOTE:** If the switch prompts "Press RETURN to get started" at the console, do NOT press Enter. ZTP handles the boot automatically via the PnP protocol.

---

## 5. Dashboard Registration

Once ZTP completes, the switch appears in the registry dashboard with a **Pending** status. You must enter the MTAG to mark the device **Complete**.

1. Open a web browser and navigate to: **http://192.0.2.253:8080**
2. Locate the device in the table — it will show a yellow **Pending** badge.
3. Find the MTAG:
    - Check the label on the outside of the shipping box, or
    - Check the physical asset tag attached to the switch chassis
    - The MTAG format is typically: `IT-YYYY-NNNNN` (e.g., `IT-2024-00123`)
4. Click the device row to open the details panel.
5. Fill in the required fields:
    - **MTAG:** enter the asset tag number from Step 5.3
    - **Notes:** enter any relevant notes (e.g., PO number, destination rack, special instructions)
6. Click **Save**. The status badge will change from **Pending** to **Complete**.

> **NOTE:** Verify the device hostname and serial number shown on the dashboard match the information on the box before entering the MTAG. If there is a mismatch, stop and contact your supervisor.

---

## 6. Label Printing

1. Click the printer icon in the device row, or open the device modal and click **Print Label**.
2. A browser print dialog will open. Select the label printer and confirm the paper size is set to 4" × 6".
3. Print the label.
4. Affix the label to the outside of the shipping box in a clearly visible location.

---

## 7. Disconnect and Repackage

1. Unplug all power supply cables from the switch.
2. Disconnect the Ethernet patch cable from switch GigabitEthernet0/0.
3. Disconnect the console cable from the switch CONSOLE port.
4. Repackage the switch in its original box. Confirm all of the following are included:
    - All power supply cables and adapters
    - Rack ears and mounting hardware (if originally included)
    - SFP/QSFP transceivers (if originally included)
    - Any accessories or documentation in the original packaging
5. Seal the box. The affixed label from Section 6 should remain visible.

---

## 8. Model-Specific Notes

### Power Supply Requirements

| Model | PSU Requirement |
|-------|----------------|
| C9300 / C9300X | 2 PSU slots — connect both |
| C9606R | 2 PSU slots — connect both |
| C9410R | Up to 8 PSU slots — connect ALL PSUs present in the box |

> **WARNING — C9410R:** This chassis has multiple PSU bays. All power supplies shipped with the unit must be connected before powering on. Failure to do so may prevent the switch from booting correctly.

---

## 9. Troubleshooting

**Device does not appear in dashboard after 15 minutes**

- Check console output via PuTTY (Section 4, Step 2) for error messages
- Verify the Ethernet cable is connected to GigabitEthernet0/0 (not another port)
- Verify the console cable is connected to the switch CONSOLE port
- Check the dashboard for a Failed Devices section at the bottom of the page
- Contact your supervisor if the issue persists

**Device shows "upgrading" status for more than 30 minutes**

- IOS upgrade is in progress — this is normal for some switch models
- Do not disconnect power — wait for the device to reboot and re-appear as Pending
- If status does not change after 45 minutes total, contact your supervisor

**Dashboard URL does not load**

- Verify your laptop is connected to the ZTP network (192.0.2.0/24)
- Try pinging 192.0.2.253 from a Command Prompt
- Contact your supervisor for the current dashboard URL
