# Alliance it2 — local control (no cloud, no Tuya key)

Local Bluetooth control of the **Alliance Outdoor Lighting it2** intelligent
lighting transformer, reverse-engineered from the official **it Pro** app
(`com.alliance.it_pro`). Turns your it2 into a native **Home Assistant** entity
over an ESP32 — **no Tuya localKey, no Alliance cloud account, no internet.**

```
Home Assistant ──WiFi/API── ESP32-S3 ──Bluetooth LE── it2 transformer ── lights
```

You get a master **Garden Lighting** switch plus **independent per-zone
switches** (Zone 1/2/3) in Home Assistant — finer control than the official app
itself. (The it2-300 is on/off-per-zone; it has no dimming.)

## Why this exists

The it2 hardware speaks the Tuya v3.3 LAN protocol, but Alliance's app doesn't
use Tuya at all — it controls the device over **Bluetooth LE** (and, for remote
access, its own AWS IoT cloud keyed only by the device's BLE identity). There is
**no Tuya localKey anywhere in the app or its cloud**, so the usual "extract the
localKey and use tinytuya" route is a dead end. Instead, this project
reverse-engineers the app's BLE command protocol and drives the device directly.

See [`PROTOCOL.md`](PROTOCOL.md) for the full protocol writeup.

## Compatibility

Developed and verified on an **it2-300**. The **it2-150** (and other it2-series
units) use the same app, firmware family, and BLE protocol, so the master on/off
and the setup should work unchanged — the 150 is essentially the same controller
at a lower transformer wattage. The one thing that may differ is the **number of
zones**: this config exposes three zone switches, so on a unit with fewer zones
the extra zone switch(es) simply won't do anything (the master switch and on/off
are unaffected). Verified reports for other models welcome — open an issue.

## What's here

| Path | What it is |
|---|---|
| [`esphome/it2.yaml`](esphome/it2.yaml) | **The main deliverable** — ESPHome config for an ESP32-S3 that bridges the it2 to Home Assistant natively (no MQTT). |
| [`esphome/ESPHOME_SETUP.md`](esphome/ESPHOME_SETUP.md) | Step-by-step: flash the ESP32, find the BLE MAC, adopt in HA. |
| [`PROTOCOL.md`](PROTOCOL.md) | The reverse-engineered BLE protocol (opcodes, framing, auth, zones). |
| [`it2ble.py`](it2ble.py) | Standalone Python/`bleak` CLI to control the it2 from a computer (`on`/`off`/`status`/`channel`). Great for testing. |
| [`bridge/`](bridge) | Alternative: a Raspberry Pi BLE→MQTT bridge (`it2_bridge.py` + systemd unit + setup guide) if you'd rather use a Pi than an ESP32. |
| `ble_scan.py`, `ble_signal.py` | BLE scanning / signal-strength helpers used during setup. |
| `tuya_key.js`, `ssl_unpin.js`, `frida_*.py`, `fetch_key.py` | The reverse-engineering scripts (Frida SSL-unpinning, heap scan, Tuya cloud attempt) that were used to work all this out. Kept for reference. |

## Quick start (ESP32 + Home Assistant)

1. Flash an **ESP32-S3** with [`esphome/it2.yaml`](esphome/it2.yaml) via ESPHome.
2. On first boot, read your it2's BLE MAC from the logs (see the setup guide) and
   put it in `ble_client: → mac_address:`.
3. Mount the ESP32 within Bluetooth range of the transformer, powered locally.
4. Adopt the device in Home Assistant — you get a **Garden Lighting** master
   switch plus **Garden Zone 1/2/3** switches.

Full details in [`esphome/ESPHOME_SETUP.md`](esphome/ESPHOME_SETUP.md).

## Protocol in one paragraph

Write commands to GATT characteristic `FFF3`, subscribe to `FFF4` for
notifications. Frames are `[0xA5, seq, opcode, len, ...params]`. The app
authenticates with a hardcoded default password `"123456"` (opcode `0x10`).
On = master `[0x01,0x03,0x01,0,0]` then channels `[0x50,0x01,0x77,0]`;
off swaps in `0x02` / `0x70`. The channel byte is `(affect_mask << 4) | on_states`
(bit0=zone1…), so `0x11`/`0x22`/`0x44` drive each zone independently. The it2
advertises a **static random** BLE address (starts `0xFF`), unrelated to its WiFi
MAC.

## Notes / gotchas

- The it2 accepts **one** BLE connection at a time — while the ESP32/Pi is
  connected, the Alliance phone app can't connect (power the bridge down to use
  the app).
- You must supply your own device's BLE MAC (find it via the ESP32 scan logs or
  an app like nRF Connect); the value in the config is one specific unit's.
- The `it Pro` APK and `frida-server` binaries are **not** included here — get
  them from their official sources.

## Disclaimer

Not affiliated with, endorsed by, or supported by Alliance Outdoor Lighting or
Tuya. This is independent interoperability work for controlling hardware you own,
provided as-is with no warranty. Reverse-engineering for interoperability;
you are responsible for how you use it. "Alliance", "it2", and "it Pro" are
trademarks of their respective owners.

## License

[MIT](LICENSE)
