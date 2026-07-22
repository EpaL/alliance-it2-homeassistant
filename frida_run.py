#!/usr/bin/env python3
"""Spawn the it Pro app under Frida with an SSL-unpinning script and keep the
session alive so its cert pinning stays disabled while the user logs in and
mitmproxy captures the decrypted cloud traffic."""
import sys, time, frida

PKG = "com.alliance.it_pro"
SCRIPT = sys.argv[1] if len(sys.argv) > 1 else "ssl_unpin.js"

def on_message(msg, data):
    if msg["type"] == "send":
        print("[script] " + str(msg["payload"]), flush=True)
    elif msg["type"] == "error":
        print("[error] " + msg.get("stack", str(msg)), flush=True)

dev = frida.get_usb_device(timeout=10)
print(f"[*] device: {dev.name}", flush=True)
pid = dev.spawn([PKG])
print(f"[*] spawned {PKG} pid={pid}", flush=True)
session = dev.attach(pid)
with open(SCRIPT) as f:
    code = f.read()
script = session.create_script(code)
script.on("message", on_message)
script.load()
dev.resume(pid)
print("[*] resumed — app running with unpinning active. Log in now.", flush=True)
# keep alive
try:
    while True:
        time.sleep(2)
except KeyboardInterrupt:
    pass
