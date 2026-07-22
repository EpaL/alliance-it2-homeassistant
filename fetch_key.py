#!/usr/bin/env python3
"""
Fetch the it2 transformer's Tuya LOCAL KEY (and dump its datapoints) from the
Tuya IoT cloud, using API credentials from a linked cloud project.

Usage:
    export TUYA_API_KEY=xxxxxxxx        # Access ID / Client ID
    export TUYA_API_SECRET=xxxxxxxx     # Access Secret / Client Secret
    export TUYA_API_REGION=us           # cn | us | us-e | eu | eu-w | sg | in
    ./.venv/bin/python fetch_key.py

Prints the device name, local key, and current status DPs for device
11520472e09806c07154 (Alliance it2 at 192.168.1.228).
"""
import os, sys, json
import tinytuya

DEVICE_ID = "11520472e09806c07154"

key = os.environ.get("TUYA_API_KEY")
secret = os.environ.get("TUYA_API_SECRET")
region = os.environ.get("TUYA_API_REGION", "us")

if not key or not secret:
    sys.exit("Set TUYA_API_KEY and TUYA_API_SECRET (and optionally TUYA_API_REGION).")

c = tinytuya.Cloud(apiRegion=region, apiKey=key, apiSecret=secret)

devices = c.getdevices(verbose=False)
if isinstance(devices, dict) and devices.get("Error"):
    sys.exit(f"Cloud error (often wrong region — try eu/us/us-e): {json.dumps(devices)}")

print(f"\n=== Devices visible to this cloud project (region={region}) ===")
target = None
for d in devices:
    mark = "  <-- it2" if d.get("id") == DEVICE_ID else ""
    print(f"  {d.get('id')}  {d.get('name')!r}{mark}")
    if d.get("id") == DEVICE_ID:
        target = d

if not target:
    print("\n!! it2 not found in this project. The account that PAIRED the it2 must")
    print("   be the one linked to this project, and the data center/region must match.")
    print("   Re-run with a different TUYA_API_REGION, or link the correct app account.")
    sys.exit(1)

print("\n=== it2 device record ===")
print(json.dumps(target, indent=2))
print(f"\n>>> LOCAL KEY: {target.get('key')}")

# Pull the datapoint (DP) definitions + live status so we can map zones/dimming.
print("\n=== Cloud properties / status (DP map) ===")
for fn in ("getproperties", "getstatus", "getfunctions", "getdps"):
    if hasattr(c, fn):
        try:
            print(f"\n--- {fn} ---")
            print(json.dumps(getattr(c, fn)(DEVICE_ID), indent=2))
        except Exception as e:
            print(f"({fn} failed: {e})")
