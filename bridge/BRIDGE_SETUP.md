# it2 → Home Assistant bridge (Raspberry Pi Zero 2 W)

A tiny always-on box in the cupboard next to the transformer holds the Bluetooth
link to the it2 and publishes it to Home Assistant over MQTT. The transformer
then appears as a normal HA **light** you can toggle, automate, and schedule —
all locally, no Tuya key and no Alliance cloud.

```
   it2 transformer  ──BLE──  Pi Zero 2 W (cupboard)  ──WiFi/MQTT──  Home Assistant
```

---

## 0. What you need
- Raspberry Pi Zero 2 W + microSD (8 GB+) + a 5V USB power supply in/near the cupboard.
- The it2 within ~10 m of the Pi (the cupboard is perfect).
- Home Assistant with the **Mosquitto broker** add-on (steps below).

> **Power & enclosure:** the Pi needs 5V USB power in the cupboard. If the cupboard
> is exposed to damp, put the Pi in a small sealed enclosure with a cable gland.
> The Pi Zero 2 W runs fine at outdoor temps but avoid direct condensation.

---

## 1. Flash Raspberry Pi OS Lite (headless)
Use **Raspberry Pi Imager**:
1. Choose **Raspberry Pi OS Lite (64-bit)** (no desktop needed).
2. Click the gear / "Edit settings" before writing and set:
   - **hostname**: `it2-bridge`
   - **Enable SSH** (password or key)
   - **username/password** (e.g. `pi` / your password)
   - **WiFi SSID + password** and your **country**
3. Write the card, boot the Pi, wait ~1 min, then from your Mac:
   ```
   ssh pi@it2-bridge.local
   ```

---

## 2. Set up the Mosquitto broker in Home Assistant
(Skip if you already run MQTT.)
1. HA → **Settings → Add-ons → Add-on Store → Mosquitto broker → Install → Start**
   (enable "Start on boot" and "Watchdog").
2. Create an MQTT user: HA → **Settings → People → Users → Add user**
   (e.g. username `it2bridge`, a password). Mosquitto uses HA users by default.
3. HA → **Settings → Devices & Services → Add Integration → MQTT** → point it at
   `core-mosquitto` if not auto-configured. Note the broker IP = your HA IP.

---

## 3. Install the bridge on the Pi
On the Pi (over SSH):
```bash
sudo apt update
sudo apt install -y python3-venv git bluetooth
# copy the bridge files to the Pi (from your Mac, in another terminal):
#   scp -r ~/Work/it2pro/bridge pi@it2-bridge.local:/tmp/bridge
sudo mkdir -p /opt/it2-bridge
sudo cp /tmp/bridge/it2_bridge.py /opt/it2-bridge/
sudo python3 -m venv /opt/it2-bridge/venv
sudo /opt/it2-bridge/venv/bin/pip install -r /tmp/bridge/requirements.txt
```

Create the config:
```bash
sudo cp /tmp/bridge/it2_bridge.env /etc/it2_bridge.env
sudo nano /etc/it2_bridge.env      # set MQTT_HOST / MQTT_USERNAME / MQTT_PASSWORD
sudo chmod 600 /etc/it2_bridge.env # it holds the MQTT password
```

---

## 4. Test it by hand first
```bash
sudo bash -c 'set -a; . /etc/it2_bridge.env; set +a; \
  LOG_LEVEL=DEBUG /opt/it2-bridge/venv/bin/python /opt/it2-bridge/it2_bridge.py'
```
You should see: `connected to MQTT` → `scanning for BLE name 'Alliance'` →
`found it2 at …` → `connected + authed` → `state -> ON/OFF`.
Then in HA, a **Garden Lighting** light should appear (Settings → Devices &
Services → MQTT). Toggle it — the transformer should respond within ~1 s.

Press Ctrl-C to stop the manual run.

> **Tip:** once it connects, copy the printed BLE address into
> `DEVICE_ADDRESS=…` in `/etc/it2_bridge.env` — connecting by MAC is faster and
> more reliable than scanning by name each time.

---

## 5. Run it as a service (auto-start, auto-restart)
```bash
sudo cp /tmp/bridge/it2-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now it2-bridge
systemctl status it2-bridge          # should be active (running)
journalctl -u it2-bridge -f          # live logs
```

The bridge now starts on boot, reconnects Bluetooth if it drops, and reconnects
MQTT if the broker restarts. HA shows the light as **unavailable** whenever the
BLE link is down (via the availability topic + last-will).

---

## 6. Using it in Home Assistant
- The entity is `light.garden_lighting` (from `FRIENDLY_NAME`). Add it to a
  dashboard, put it in automations, schedule sunset/sunrise, etc.
- State stays live: the bridge polls every `POLL_INTERVAL` seconds and also
  reacts to the transformer's own status pushes, so HA reflects changes even if
  something else (a schedule) toggles the lights.

---

## Notes & troubleshooting
- **The phone app vs the bridge:** the it2 typically allows one Bluetooth
  connection at a time. While the bridge is connected, the Alliance app may not
  be able to connect. To use the app, `sudo systemctl stop it2-bridge`, then
  `start` it again afterwards.
- **Not found / won't connect:** confirm range (`bluetoothctl` → `scan on` should
  list `Alliance`), and that no other device holds the connection. Set
  `DEVICE_ADDRESS` to the MAC.
- **Brightness/zones:** `ENABLE_BRIGHTNESS=true` exposes a brightness slider
  (opcode 82) — this is **experimental / unverified on hardware**. Turn on
  `LOG_LEVEL=DEBUG` and watch the FFF4 replies to confirm behaviour before
  relying on it. Per-zone control is in `../PROTOCOL.md` (opcode 80 bitmask) if
  you want separate entities per channel later.
- **Security:** `/etc/it2_bridge.env` holds your MQTT password — keep it `600`.
  The BLE side needs no secret (the device's auth is the app's default "123456").
