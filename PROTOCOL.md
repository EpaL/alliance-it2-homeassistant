# Alliance it2 — BLE control protocol

Reverse-engineered from the **it Pro** app (`com.alliance.it_pro`, React Native /
Hermes bundle). This lets you control the it2 transformer locally over Bluetooth
with no Tuya localKey, no Alliance cloud account, and no internet.

## Why not Tuya?
The it2 hardware is an ESP module that also happens to speak the Tuya v3.3 LAN
protocol, but **Alliance's app does not use Tuya at all**. It controls the device
over **Bluetooth LE** (and, for remote access, its own AWS IoT cloud keyed only by
the device's BLE MAC). The app's cloud stores only the BLE identity — no Tuya
localKey exists anywhere in the app or its cloud. Hence BLE is the route to local
control.

## Transport (GATT)
- **Write** commands to characteristic **`FFF3`** (`0000fff3-0000-1000-8000-00805f9b34fb`),
  write-without-response, chunked to 20 bytes (all commands here are shorter).
- **Subscribe** to characteristic **`FFF4`** (`0000fff4-...`) for notifications.
- Both live under service `FFF0`.

## Frame format (app → device)
```
[ 0xA5, verSeq, opcode, paramLen, param0, param1, ... ]
```
- `0xA5` — fixed start byte.
- `verSeq` = `0x10 + pkgId`, where `pkgId` rolls 1..14 and the high nibble `0x1`
  is the protocol version. So it's `0x10 | seq` (0x10, 0x11, ... 0x1E). The device
  uses the low nibble to match acknowledgements; exact value is not critical.
- `opcode` — command id (below).
- `paramLen` — number of parameter bytes that follow.
- no trailing checksum for these short commands.

Device → app notifications on FFF4 are framed as `[0xA5, ver, opcode, len, ...data]`.

## Auth
The app authenticates on connect with a **hardcoded default password `"123456"`**:
```
auth:  opcode 16, params "123456" (ASCII 49,50,51,52,53,54)
       -> A5 10 10 06 31 32 33 34 35 36
```
Send this once after connecting, before other commands. (There is a separate
`encrypt` opcode 18 used only to *change* the password — not needed for control.)

## Command reference (opcode / params)
| Action | opcode | params | example frame |
|---|---|---|---|
| auth (default) | 16 | `31 32 33 34 35 36` | `A5 10 10 06 31 32 33 34 35 36` |
| **turn ON** | 1 | `01 00 00` | `A5 11 01 03 01 00 00` |
| **turn OFF** | 1 | `02 00 00` | `A5 11 01 03 02 00 00` |
| query on/off | 1 | `00 00 00` | `A5 11 01 03 00 00 00` |
| read device status | 3 | (none) | `A5 11 03 00` |
| clear error status | 5 | `0F` | `A5 11 05 01 0F` |
| set brightness¹ | 82 | `<0..100>` | `A5 11 52 01 32` (=50%) |
| control sub-channel | 80 | `<ch> <val>` | `A5 11 50 02 00 64` |
| get sub-channel status | 80 | `00` | `A5 11 50 01 00` |
| set time | 22 | `yy mm dd wk hh mm ss` | |
| set timezone | 76 | `<tz>` | |
| get sunset/sunrise | 78 | (none) | |
| weekly schedule | 24 | `id wk hh mm ss action` | |
| set device name | 64 | `<16 bytes name>` | |

¹ In the app's command table but **not exposed by the app** for the it2-300 (no
brightness UI) — this unit is on/off-per-zone only. Present here for completeness.

### Notification semantics (device → app)
- on/off reply (opcode 1): data byte 0 = state (1=on, 2/0=off); later bytes carry
  per-channel status (`channels`, `channelsExtra`).
- sub-channel reply (opcode 80): `channelStatus`, `channelExtraStatus`.
- auth reply (opcode 16): data byte 0 = pass/fail.

## IMPORTANT: 3-channel devices (it2-300) — on/off needs the channels
The it2-300 is a 3-channel "light modulator". The master relay (`openDevice`
opcode 1) alone does **not** illuminate anything — the channels stay off. To turn
the lights on/off you must also send the channel command (`controlSubChannels`,
opcode 80) with a channel bitmask in `p0`:

- p0 = `(affect_mask << 4) | on_states`, low nibble = per-channel on bits.
- **all channels ON**  → `[0xA5, seq, 80, 0x01, 0x77, 0x00]`  (0x77 = affect 3 + all on)
- **all channels OFF** → `[0xA5, seq, 80, 0x01, 0x70, 0x00]`  (0x70 = affect 3 + all off)

(Note the length byte is a nominal `0x01` even though two param bytes follow — the
app sends it that way, so we do too.) A full ON is: `auth` → `openDevice[1,0,0]` →
`controlSubChannels 0x77`. Confirmed: on/off state byte in the reply flips 2→1 and
the channels byte flips 0x70→0x77.

**Verified working** on a real it2-300 over the Mac's Bluetooth (2026-07-18):
lights physically switch, telemetry shows load ramping.

### Per-zone control (verified on it2-300, 3 zones)
The channel byte `p0 = (affect_mask << 4) | on_states` lets you control zones
**independently** — the affect-mask (high nibble) selects which zones the command
touches, so other zones are left untouched. Bits: `bit0=zone1, bit1=zone2,
bit2=zone3`.

| Action | p0 | frame |
|---|---|---|
| all zones on | `0x77` | `A5 seq 50 01 77 00` |
| all zones off | `0x70` | `A5 seq 50 01 70 00` |
| zone 1 on / off | `0x11` / `0x10` | `A5 seq 50 01 11 00` / `... 10 00` |
| zone 2 on / off | `0x22` / `0x20` | |
| zone 3 on / off | `0x44` / `0x40` | |

Zone state comes back in the sub-channel reply (opcode `0x51`, byte 0 low nibble)
and the periodic telemetry (opcode `0x80`). Confirmed independent on a real
it2-300 (2026-07-21).

**No dimming:** the it2-300 is on/off relays per zone — it does **not** support
brightness. The `setBrightness` opcode (`0x52`) exists in the app's command table
(shared across the product line) but the official app exposes no brightness
control for this unit, and it is not implemented here.

## Notes / open points
- `verSeq` increments per command in the app; the device appears to treat it as a
  version+sequence tag. `it2ble.py` reproduces this.
- Whether the device strictly *requires* auth before accepting on/off is uncertain
  — `it2ble.py` always sends auth first (matching the app) to be safe.
- The it2-300 exposes 3 independent zones via the `controlSubChannels` affect-mask
  (see the per-zone table above). No dimming on this unit.
