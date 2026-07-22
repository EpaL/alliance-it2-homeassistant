#!/usr/bin/env python3
"""
it2ble.py — direct, keyless local control of an Alliance it2 transformer over
Bluetooth LE, reverse-engineered from the "it Pro" (com.alliance.it_pro) app.

No Tuya localKey, no cloud, no account needed. The app authenticates to the
device with a hardcoded default password "123456"; we do the same.

Protocol (write -> characteristic FFF3, notify <- characteristic FFF4):
    frame = [0xA5, 0x10|seq, opcode, paramLen, *params]
    seq   = rolling 1..14 (low nibble); high nibble 0x1 = protocol version.
    Device replies on FFF4, framed as [0xA5, ver, opcode, len, *data].

Commands:
    auth (default)   opcode 16  params "123456"      -> [A5,seq,16,6,49,50,51,52,53,54]
    turn ON          opcode 1   [1,0,0]
    turn OFF         opcode 1   [2,0,0]
    query on/off     opcode 1   [0,0,0]
    read status      opcode 3   []
    set brightness   opcode 82  [level 0..100]
    control channel  opcode 80  [channel, value]

Usage (run from YOUR OWN Terminal so macOS can grant Bluetooth permission):
    python3 it2ble.py scan
    python3 it2ble.py status   [--name it2-300 | --address <uuid>]
    python3 it2ble.py on
    python3 it2ble.py off
    python3 it2ble.py bright 50
    python3 it2ble.py channel 0 100
    python3 it2ble.py raw A5 10 01 03 01 00 00      # send an arbitrary frame
"""
import argparse, asyncio, sys
from bleak import BleakScanner, BleakClient

FFF3 = "0000fff3-0000-1000-8000-00805f9b34fb"  # write  (writeWithoutResponse)
FFF4 = "0000fff4-0000-1000-8000-00805f9b34fb"  # notify
DEFAULT_NAME = "it2-300"
AUTH_PW = [49, 50, 51, 52, 53, 54]  # "123456"

def is_it2(name: str) -> bool:
    n = (name or "").lower()
    return n.startswith("it2") or n.startswith("xf") or "itimer" in n or n == "alliance"

class Seq:
    def __init__(self): self.pkg = 0
    def next(self) -> int:
        v = 0x10 + self.pkg
        self.pkg = 1 if self.pkg + 1 >= 15 else self.pkg + 1
        return v

def frame(seq: Seq, opcode: int, params=(), length=None) -> bytes:
    # length defaults to the param count, but some commands (controlSubChannels)
    # send a nominal length byte that differs from the actual param count — the
    # app does this, so we replicate it exactly when `length` is given.
    params = list(params)
    lb = len(params) if length is None else length
    return bytes([0xA5, seq.next(), opcode, lb, *params])

def parse_notify(data: bytes):
    if len(data) >= 4 and data[0] == 0xA5:
        opcode = data[2]
        body = data[3 + 1:]  # after [A5, ver, opcode, len]
        return opcode, list(body)
    return None, list(data)

async def find_device(name, address, timeout=12.0):
    if address:
        return address
    print(f"[*] scanning {timeout:.0f}s for '{name}' ...", flush=True)
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for addr, (dev, adv) in found.items():
        nm = adv.local_name or dev.name or ""
        if (name and nm == name) or (not name and is_it2(nm)):
            print(f"[+] found {nm!r} at {addr} (rssi {adv.rssi})", flush=True)
            return addr
    return None

async def connect(name, address):
    addr = await find_device(name, address)
    if not addr:
        print("[!] it2 not found. Move closer, ensure it's powered, or pass --address.", flush=True)
        sys.exit(2)
    client = BleakClient(addr)
    await client.connect()
    print(f"[+] connected to {addr}", flush=True)

    notes = []
    def on_notify(_char, data: bytearray):
        opcode, body = parse_notify(bytes(data))
        notes.append((opcode, body, bytes(data)))
        print(f"    <- FFF4  opcode={opcode}  data={body}  raw={bytes(data).hex()}", flush=True)
    await client.start_notify(FFF4, on_notify)
    return client, notes

async def send(client, seq, opcode, params=(), length=None, label="", wait=0.4):
    f = frame(seq, opcode, params, length=length)
    print(f"    -> FFF3  {label:<10} {f.hex()}", flush=True)
    await client.write_gatt_char(FFF3, f, response=False)
    await asyncio.sleep(wait)

async def do_auth(client, seq):
    await send(client, seq, 16, AUTH_PW, label="auth")

# 3-channel "all channels" control via controlSubChannels (opcode 80).
# p0 = (affect-mask << 4) | on/off-states.  0x77 = affect all 3 + all on;
# 0x70 = affect all 3 + all off.  App sends nominal length byte 1.
async def open_all_channels(client, seq):
    await send(client, seq, 80, [0x77, 0], length=1, label="chans-on")

async def close_all_channels(client, seq):
    await send(client, seq, 80, [0x70, 0], length=1, label="chans-off")

async def cmd_scan(args):
    print("[*] scanning 12s ...", flush=True)
    found = await BleakScanner.discover(timeout=12.0, return_adv=True)
    hits = []
    for addr, (dev, adv) in found.items():
        nm = adv.local_name or dev.name or ""
        mark = "*" if is_it2(nm) else " "
        hits.append((mark, adv.rssi, addr, nm))
    for mark, rssi, addr, nm in sorted(hits, key=lambda x: (x[0] != "*", -x[1])):
        print(f"{mark} {addr}  rssi={rssi}  name={nm!r}")

async def cmd_status(args):
    client, notes = await connect(args.name, args.address)
    seq = Seq()
    try:
        await do_auth(client, seq)
        await send(client, seq, 1, [0, 0, 0], label="get-onoff")
        await send(client, seq, 3, [], label="read-status", wait=0.8)
        await asyncio.sleep(0.6)
    finally:
        await client.disconnect()

async def cmd_onoff(args, on: bool):
    client, notes = await connect(args.name, args.address)
    seq = Seq()
    try:
        await do_auth(client, seq)
        # master relay, then all channels (it2-300 is a 3-channel light modulator;
        # the master alone leaves the channels off, so no light)
        await send(client, seq, 1, [1 if on else 2, 0, 0], label="master-on" if on else "master-off")
        if on:
            await open_all_channels(client, seq)
        else:
            await close_all_channels(client, seq)
        await send(client, seq, 1, [0, 0, 0], label="get-onoff", wait=0.8)
        await asyncio.sleep(0.6)
        print(f"[+] sent {'ON' if on else 'OFF'} (master + channels)", flush=True)
    finally:
        await client.disconnect()

async def cmd_bright(args):
    lvl = max(0, min(100, args.level))
    client, notes = await connect(args.name, args.address)
    seq = Seq()
    try:
        await do_auth(client, seq)
        await send(client, seq, 82, [lvl], label=f"bright {lvl}", wait=0.8)
        await asyncio.sleep(0.5)
    finally:
        await client.disconnect()

async def cmd_channel(args):
    client, notes = await connect(args.name, args.address)
    seq = Seq()
    try:
        await do_auth(client, seq)
        await send(client, seq, 80, [args.channel, args.value], label="channel", wait=0.8)
        await asyncio.sleep(0.5)
    finally:
        await client.disconnect()

async def cmd_raw(args):
    body = bytes(int(x, 16) for x in args.bytes)
    client, notes = await connect(args.name, args.address)
    try:
        print(f"    -> FFF3  raw        {body.hex()}", flush=True)
        await client.write_gatt_char(FFF3, body, response=False)
        await asyncio.sleep(1.2)
    finally:
        await client.disconnect()

def main():
    # shared options so --name/--address work before OR after the subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--name", default=DEFAULT_NAME, help="BLE local name (default it2-300)")
    common.add_argument("--address", default=None, help="BLE address / CoreBluetooth UUID (skips scan)")

    ap = argparse.ArgumentParser(description="Keyless BLE control for the Alliance it2 transformer",
                                 parents=[common])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", parents=[common])
    sub.add_parser("status", parents=[common])
    sub.add_parser("on", parents=[common])
    sub.add_parser("off", parents=[common])
    p = sub.add_parser("bright", parents=[common]); p.add_argument("level", type=int)
    p = sub.add_parser("channel", parents=[common]); p.add_argument("channel", type=int); p.add_argument("value", type=int)
    p = sub.add_parser("raw", parents=[common]); p.add_argument("bytes", nargs="+", help="hex bytes, e.g. A5 10 01 03 01 00 00")
    args = ap.parse_args()

    runners = {
        "scan": cmd_scan, "status": cmd_status,
        "on": lambda a: cmd_onoff(a, True), "off": lambda a: cmd_onoff(a, False),
        "bright": cmd_bright, "channel": cmd_channel, "raw": cmd_raw,
    }
    asyncio.run(runners[args.cmd](args))

if __name__ == "__main__":
    main()
