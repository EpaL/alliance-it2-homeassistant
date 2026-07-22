#!/usr/bin/env python3
"""Scan for the Alliance it2 over BLE and print candidates."""
import asyncio
from bleak import BleakScanner

async def main():
    print("[*] scanning 12s ...", flush=True)
    devices = await BleakScanner.discover(timeout=12.0, return_adv=True)
    found = []
    for addr, (dev, adv) in devices.items():
        name = adv.local_name or dev.name or ""
        mfg = adv.manufacturer_data
        uuids = adv.service_uuids
        interesting = ("it2" in name.lower() or "xf" in name.lower()
                       or any("fff0" in (u or "").lower() for u in uuids))
        line = f"{addr}  rssi={adv.rssi}  name={name!r}  svc={uuids}  mfg={ {k:v.hex() for k,v in mfg.items()} }"
        if interesting:
            found.append(("*", line))
        else:
            found.append((" ", line))
    print(f"[*] {len(found)} devices seen\n", flush=True)
    for mark, line in sorted(found, reverse=True):
        print(f"{mark} {line}")

asyncio.run(main())
