#!/usr/bin/env python3
"""Attach to the already-running it Pro app and install the SSL-unpinning
script, then keep the session alive while the user logs in."""
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
# attach target: numeric pid as 2nd arg, else resolve by app identifier
arg_pid = None
if len(sys.argv) > 2:
    arg_pid = int(sys.argv[2])
target = arg_pid
if target is None:
    for app in dev.enumerate_applications():
        if app.identifier == PKG and app.pid:
            target = app.pid
            break
if not target:
    print("[!] app process not found — launch it first", flush=True)
    sys.exit(1)
print(f"[*] attaching to pid={target}", flush=True)
session = dev.attach(target)
with open(SCRIPT) as f:
    code = f.read()
script = session.create_script(code)
script.on("message", on_message)
script.load()
print("[*] script loaded — unpinning active. Log in now.", flush=True)
try:
    while True:
        time.sleep(2)
except KeyboardInterrupt:
    pass
