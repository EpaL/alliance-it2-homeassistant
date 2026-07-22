#!/usr/bin/env python3
"""Continuous BLE signal meter for the Alliance it2. Walk it around and watch
the RSSI to find a spot with a reliable signal (aim for better than ~-85 dBm).
Ctrl-C to stop."""
import asyncio
from bleak import BleakScanner

TARGET = "alliance"  # advertised name (case-insensitive substring)

def bar(rssi):
    # crude signal bar: -50 great .. -100 dead
    n = max(0, min(20, int((rssi + 100) / 2.5)))
    quality = "GREAT" if rssi > -75 else "OK" if rssi > -85 else "WEAK" if rssi > -92 else "UNUSABLE"
    return f"[{'#'*n}{'.'*(20-n)}] {rssi:>4} dBm  {quality}"

async def main():
    print("scanning for 'Alliance' — walk the ESP's candidate spots. Ctrl-C to stop.\n", flush=True)
    seen = 0
    while True:
        found = await BleakScanner.discover(timeout=3.0, return_adv=True)
        hit = None
        for _addr, (dev, adv) in found.items():
            nm = (adv.local_name or dev.name or "")
            if TARGET in nm.lower():
                hit = adv.rssi
                break
        if hit is not None:
            seen += 1
            print(f"  {bar(hit)}", flush=True)
        else:
            print("  [....................]   --   not seen this sweep", flush=True)

asyncio.run(main())
