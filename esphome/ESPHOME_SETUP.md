# it2 bridge on ESP32-S3 with ESPHome

The ESP32-S3 in the cupboard holds the Bluetooth link to the it2 and appears in
Home Assistant natively (via the ESPHome integration — **no MQTT broker needed**,
unlike the Raspberry Pi option). Toggling the **Garden Lighting** switch sends the
verified BLE frames; live state comes from the transformer's own notifications.

Files: `it2.yaml` (the config), `secrets.yaml.example` (copy to `secrets.yaml`).

## One-time setup
1. **Install ESPHome** — easiest is the *ESPHome Device Builder* add-on in Home
   Assistant (Settings → Add-ons → Add-on Store), or `pip install esphome`.
2. **Secrets:** copy `secrets.yaml.example` → `secrets.yaml`, fill in your WiFi.
   Generate the API key with `openssl rand -base64 32`, and pick an OTA password.
   (The ESPHome dashboard can generate the API key for you.)
3. **First flash over USB:** plug the S3 into your computer with a USB-C cable
   (use the port labelled **USB**, not UART, if in doubt try either), and in the
   ESPHome dashboard "Install → Plug into this computer." After the first flash,
   all future updates go over WiFi (OTA).

## Get the it2's real Bluetooth MAC (important)
The `mac_address` in `it2.yaml` is a placeholder. After the first flash:
1. Open the device **Logs** in ESPHome.
2. Watch for lines like `[esp32_ble_tracker] Found device AA:BB:CC:DD:EE:FF` with
   name `Alliance`.
3. Put that MAC into `it2.yaml` → `ble_client: → mac_address:` and re-flash (OTA).

Once it connects you'll see `it2: connected + auth sent` in the logs.

## In Home Assistant
The device auto-appears: **Settings → Devices & Services → ESPHome** → adopt it.
You'll get a **Garden Lighting** switch. Toggle it — the transformer should
respond within ~1 second, and the switch reflects the true state (so it stays
correct even if a schedule or the app changes the lights).

## Notes
- **Validated:** this config passes `esphome config` on ESPHome 2026.7.0. The
  schema is checked, but the C++ lambdas (notification parsing + `ble_write`
  values) are only compiled at flash time — if the first compile complains about
  a lambda, set `logger: level: DEBUG`, grab the lines, and it's a one-line fix.
- **Phone app vs the bridge:** the it2 accepts one Bluetooth connection at a time.
  While the ESP32 is connected, the Alliance app won't connect. Power off the
  ESP32 (or remove its `ble_client`) if you need the app.
- **Reconnecting after a reflash / reboot:** when the ESP32 reboots (e.g. an OTA
  reinstall), the it2 keeps holding the now-dead connection and refuses the new
  one until its own link-supervision timeout expires. If control stops working
  after a flash and the log shows no `it2: connected + auth sent`, either wait
  ~30–60 s for the it2 to drop the stale link, or **power-cycle the transformer**
  (off ~15 s) to force it. This only happens on reboot — in steady-state
  operation the connection is held 24/7 and is stable. There is no ESPHome knob
  for this; it's device-side.
- **Classic ESP32 instead of S3?** Change `board:` to your board (e.g.
  `esp32dev`) and drop `flash_size: 16MB`. Everything else is identical.
- **Brightness / per-zone:** not included yet (opcode 82 / opcode 80 bitmask,
  unverified on hardware). Once the switch works we can add a brightness slider
  and/or three separate zone switches.
