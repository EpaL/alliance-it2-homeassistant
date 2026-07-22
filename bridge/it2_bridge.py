#!/usr/bin/env python3
"""
it2_bridge.py — Bluetooth-to-MQTT bridge for the Alliance it2 transformer.

Runs on a small always-on Linux box (e.g. Raspberry Pi Zero 2 W) within
Bluetooth range of the it2. Holds a persistent BLE link to the transformer and
exposes it to Home Assistant as an auto-discovered MQTT light — keyless, local,
no Tuya key and no Alliance cloud.

Protocol (reverse-engineered; see ../PROTOCOL.md):
  write  -> characteristic FFF3 : [0xA5, verSeq, opcode, len, *params]
  notify <- characteristic FFF4 : [0xA5, ver, opcode, len, *data]
  auth   : opcode 16, params "123456" (default password the app uses)
  ON     : master openDevice [1,3,1,0,0] + all-channels [80,1,0x77,0]
  OFF    : master closeDevice [1,3,2,0,0] + all-channels [80,1,0x70,0]

Config comes from environment variables (see it2_bridge.env). Requires:
  pip install bleak aiomqtt
"""
import asyncio
import json
import logging
import os
import signal

from bleak import BleakScanner, BleakClient
import aiomqtt

# ----------------------------------------------------------------------------- config
def env(k, default=None):
    v = os.environ.get(k)
    return v if v not in (None, "") else default

MQTT_HOST     = env("MQTT_HOST", "127.0.0.1")
MQTT_PORT     = int(env("MQTT_PORT", "1883"))
MQTT_USERNAME = env("MQTT_USERNAME")
MQTT_PASSWORD = env("MQTT_PASSWORD")

DEVICE_NAME    = env("DEVICE_NAME", "Alliance")   # BLE advertised name to match
DEVICE_ADDRESS = env("DEVICE_ADDRESS")            # optional MAC override (skips scan)
NODE_ID        = env("NODE_ID", "it2_garden")     # unique id / topic root
FRIENDLY_NAME  = env("FRIENDLY_NAME", "Garden Lighting")
MODEL          = env("MODEL", "it2-300")
DISCOVERY_PREFIX = env("DISCOVERY_PREFIX", "homeassistant")

POLL_INTERVAL  = float(env("POLL_INTERVAL", "30"))   # seconds between state polls
RECONNECT_MIN  = 3.0
RECONNECT_MAX  = 60.0
ENABLE_BRIGHTNESS = env("ENABLE_BRIGHTNESS", "false").lower() == "true"  # experimental

LOG_LEVEL = env("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("it2")

# ----------------------------------------------------------------------------- BLE protocol
FFF3 = "0000fff3-0000-1000-8000-00805f9b34fb"
FFF4 = "0000fff4-0000-1000-8000-00805f9b34fb"
AUTH_PW = [49, 50, 51, 52, 53, 54]  # "123456"

# MQTT topics
T_STATE = f"it2/{NODE_ID}/state"
T_CMD   = f"it2/{NODE_ID}/set"
T_AVAIL = f"it2/{NODE_ID}/availability"
T_BRI_STATE = f"it2/{NODE_ID}/brightness/state"
T_BRI_CMD   = f"it2/{NODE_ID}/brightness/set"
T_DISCOVERY = f"{DISCOVERY_PREFIX}/light/{NODE_ID}/config"

def name_matches(name: str) -> bool:
    n = (name or "").lower()
    return n == DEVICE_NAME.lower() or n.startswith("it2") or n.startswith("xf")

class Seq:
    def __init__(self): self.pkg = 0
    def next(self) -> int:
        v = 0x10 + self.pkg
        self.pkg = 1 if self.pkg + 1 >= 15 else self.pkg + 1
        return v

def frame(seq: Seq, opcode: int, params=(), length=None) -> bytes:
    params = list(params)
    lb = len(params) if length is None else length
    return bytes([0xA5, seq.next(), opcode, lb, *params])

def parse_state_from_notify(data: bytes):
    """Return True/False (on/off) if this notification reveals it, else None."""
    if len(data) < 5 or data[0] != 0xA5:
        return None
    opcode = data[2]
    body = data[4:]
    if opcode == 2:                       # on/off reply: body[0] == 1 -> on
        return body[0] == 1
    if opcode == 128 and len(body) > 12:  # periodic telemetry: channels byte
        return (body[12] & 0x07) != 0     # 0x77 low nibble set = channels on
    return None

# ----------------------------------------------------------------------------- bridge
class Bridge:
    def __init__(self, mqtt: aiomqtt.Client):
        self.mqtt = mqtt
        self.loop = asyncio.get_running_loop()
        self.client = None
        self.seq = Seq()
        self.write_lock = asyncio.Lock()
        self.last_state = None

    async def publish_discovery(self):
        cfg = {
            "name": FRIENDLY_NAME,
            "unique_id": NODE_ID,
            "command_topic": T_CMD,
            "state_topic": T_STATE,
            "payload_on": "ON",
            "payload_off": "OFF",
            "availability_topic": T_AVAIL,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": {
                "identifiers": [NODE_ID],
                "name": "Alliance it2",
                "manufacturer": "Alliance Outdoor Lighting",
                "model": MODEL,
            },
        }
        if ENABLE_BRIGHTNESS:
            cfg.update({
                "brightness_command_topic": T_BRI_CMD,
                "brightness_state_topic": T_BRI_STATE,
                "brightness_scale": 100,
            })
        await self.mqtt.publish(T_DISCOVERY, json.dumps(cfg), qos=1, retain=True)
        log.info("published MQTT discovery -> %s", T_DISCOVERY)

    async def publish_availability(self, online: bool):
        await self.mqtt.publish(T_AVAIL, "online" if online else "offline", qos=1, retain=True)

    async def publish_state(self, on: bool):
        if on != self.last_state:
            self.last_state = on
            await self.mqtt.publish(T_STATE, "ON" if on else "OFF", qos=1, retain=True)
            log.info("state -> %s", "ON" if on else "OFF")

    # -- BLE lifecycle --------------------------------------------------------
    async def _resolve_address(self):
        if DEVICE_ADDRESS:
            return DEVICE_ADDRESS
        log.info("scanning for BLE name %r ...", DEVICE_NAME)
        found = await BleakScanner.discover(timeout=12.0, return_adv=True)
        for addr, (dev, adv) in found.items():
            if name_matches(adv.local_name or dev.name or ""):
                log.info("found it2 at %s (rssi %s)", addr, adv.rssi)
                return addr
        return None

    def _on_notify(self, _char, data: bytearray):
        st = parse_state_from_notify(bytes(data))
        if st is not None:
            # notification callback may run outside the loop thread on some
            # backends; hop back onto the loop safely.
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self.publish_state(st)))

    async def run_ble(self):
        backoff = RECONNECT_MIN
        while True:
            try:
                addr = await self._resolve_address()
                if not addr:
                    log.warning("it2 not found; retrying in %.0fs", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 1.7, RECONNECT_MAX)
                    continue
                log.info("connecting to %s ...", addr)
                async with BleakClient(addr) as client:
                    self.client = client
                    self.seq = Seq()
                    await client.start_notify(FFF4, self._on_notify)
                    await self._auth()
                    await self.publish_availability(True)
                    log.info("connected + authed")
                    backoff = RECONNECT_MIN
                    while client.is_connected:
                        await self._query_onoff()
                        await asyncio.sleep(POLL_INTERVAL)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("BLE session ended: %s", e)
            finally:
                self.client = None
                self.last_state = None
                try:
                    await self.publish_availability(False)
                except Exception:
                    pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.7, RECONNECT_MAX)

    async def _write(self, f: bytes, label=""):
        c = self.client
        if not c or not c.is_connected:
            log.warning("write %s dropped: not connected", label)
            return False
        async with self.write_lock:
            await c.write_gatt_char(FFF3, f, response=False)
            log.debug("-> %s %s", label, f.hex())
            await asyncio.sleep(0.3)
        return True

    async def _auth(self):
        await self._write(frame(self.seq, 16, AUTH_PW), "auth")

    async def _query_onoff(self):
        await self._write(frame(self.seq, 1, [0, 0, 0]), "get-onoff")

    # -- commands from MQTT ---------------------------------------------------
    async def set_power(self, on: bool):
        if not await self._write(frame(self.seq, 1, [1 if on else 2, 0, 0]),
                                 "master-on" if on else "master-off"):
            return
        if on:
            await self._write(frame(self.seq, 80, [0x77, 0], length=1), "chans-on")
        else:
            await self._write(frame(self.seq, 80, [0x70, 0], length=1), "chans-off")
        await self.publish_state(on)        # optimistic; confirmed by notify
        await self._query_onoff()

    async def set_brightness(self, level: int):
        level = max(0, min(100, level))
        await self._write(frame(self.seq, 82, [level]), f"bright {level}")
        await self.mqtt.publish(T_BRI_STATE, str(level), qos=1, retain=True)

    async def handle_commands(self):
        async for msg in self.mqtt.messages:
            topic = str(msg.topic)
            payload = msg.payload.decode(errors="ignore").strip()
            try:
                if topic == T_CMD:
                    await self.set_power(payload.upper() == "ON")
                elif ENABLE_BRIGHTNESS and topic == T_BRI_CMD:
                    await self.set_brightness(int(payload))
            except Exception as e:
                log.warning("command %s=%r failed: %s", topic, payload, e)

# ----------------------------------------------------------------------------- main
async def amain():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, stop.set)
        except NotImplementedError:
            pass

    will = aiomqtt.Will(T_AVAIL, "offline", qos=1, retain=True)
    while not stop.is_set():
        try:
            async with aiomqtt.Client(
                hostname=MQTT_HOST, port=MQTT_PORT,
                username=MQTT_USERNAME, password=MQTT_PASSWORD,
                will=will,
            ) as mqtt:
                log.info("connected to MQTT %s:%s", MQTT_HOST, MQTT_PORT)
                bridge = Bridge(mqtt)
                await bridge.publish_discovery()
                await bridge.publish_availability(False)  # until BLE is up
                await mqtt.subscribe(T_CMD)
                if ENABLE_BRIGHTNESS:
                    await mqtt.subscribe(T_BRI_CMD)

                tasks = [
                    asyncio.create_task(bridge.run_ble()),
                    asyncio.create_task(bridge.handle_commands()),
                    asyncio.create_task(stop.wait()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        except Exception as e:
            log.warning("MQTT session error: %s; reconnecting in 5s", e)

        if not stop.is_set():
            await asyncio.sleep(5)
    log.info("shutting down")

if __name__ == "__main__":
    asyncio.run(amain())
