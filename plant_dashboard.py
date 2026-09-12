#!/usr/bin/env python3
"""Canopy station for Orange Pi 3 LTS + Arduino Nano.

800×480 HDMI kiosk. LAN only — do not port-forward.
Pump relay is inverted: HIGH = on. Default OFF at start.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import serial
from flask import Flask, Response, jsonify

ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "station.json"

DEFAULTS = {
    "moistureDry": 49,
    "moistureWet": 21,
    "lightDark": 73,
    "lightDay": 10,
    "autoSeconds": 300,
    "waterPulseMs": 1000,
    "lightOnBelow": 40,
    "flaskHost": "0.0.0.0",
    "flaskPort": 5000,
}

PROFILES = (
    {"id": "lush", "label": "Lush houseplant", "low": 45, "high": 75, "green": 0.45},
    {"id": "standard", "label": "Standard houseplant", "low": 40, "high": 70, "green": 0.25},
    {"id": "succulent", "label": "Succulent / low-water", "low": 20, "high": 50, "green": 0.0},
)


def load_cfg() -> dict:
    cfg = dict(DEFAULTS)
    if CFG_PATH.exists():
        try:
            cfg.update(json.loads(CFG_PATH.read_text()))
        except Exception:
            pass
    return cfg


CFG = load_cfg()
LOCK = threading.Lock()
SER = None
CAP = None
STATE = {
    "moisture_raw": None,
    "light_raw": None,
    "moisture": 0.0,
    "light": 0.0,
    "green": 0.0,
    "yellow": 0.0,
    "dark": 0.0,
    "pump": False,
    "lamp": False,
    "profile": PROFILES[1]["label"],
    "status": "Waiting for sensors",
    "status_tone": "muted",
    "camera": None,
    "serial": None,
    "last_auto": 0.0,
}


def scale_inverted(raw, dry, wet) -> float:
    span = dry - wet
    if span == 0:
        return 0.0
    return max(0.0, min(100.0, (dry - raw) / span * 100.0))


def classify(green: float) -> dict:
    if green > 0.45:
        return PROFILES[0]
    if green > 0.25:
        return PROFILES[1]
    return PROFILES[2]


def health(green: float, moisture: float, profile: dict) -> tuple[str, str]:
    if green < 0.22:
        return "Thinning", "alert"
    if moisture < profile["low"]:
        return "Too dry", "warn"
    if moisture > profile["high"]:
        return "Too wet", "warn"
    return "In range", "ok"


def find_serial():
    for path in ("/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"):
        if os.path.exists(path):
            try:
                ser = serial.Serial(path, 9600, timeout=1)
                ser.reset_input_buffer()
                return ser, path
            except Exception:
                continue
    return None, None


def find_camera():
    for idx in (1, 2, 0):
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue
        ok, _ = cap.read()
        if ok:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            return cap, idx
        cap.release()
    return None, None


def parse_line(line: str):
    if "MOISTURE:" not in line:
        return None
    try:
        rest = line.split("MOISTURE:", 1)[1]
        moist_s, light_s = rest.split("|LIGHT:", 1)
        return int(float(moist_s.strip())), int(float(light_s.strip()))
    except Exception:
        return None


def send(cmd: str) -> None:
    ser = SER
    if ser is None:
        return
    try:
        ser.write((cmd + "\n").encode("ascii"))
    except Exception:
        pass


def water_pulse() -> None:
    with LOCK:
        if STATE["pump"]:
            return
        STATE["pump"] = True
    send("WATER_ON")
    time.sleep(max(0.2, CFG["waterPulseMs"] / 1000.0))
    send("WATER_OFF")
    with LOCK:
        STATE["pump"] = False


def set_lamp(on: bool) -> None:
    send("LIGHT_ON" if on else "LIGHT_OFF")
    with LOCK:
        STATE["lamp"] = on


def analyze(frame) -> tuple[float, float, float]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    yellow = cv2.inRange(hsv, (15, 40, 40), (34, 255, 255))
    pixels = frame.shape[0] * frame.shape[1]
    g = float(np.count_nonzero(green)) / pixels
    y = float(np.count_nonzero(yellow)) / pixels
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dark = float(np.count_nonzero(gray < 40)) / pixels
    return g, y, dark


def serial_loop() -> None:
    global SER
    ser, path = find_serial()
    SER = ser
    with LOCK:
        STATE["serial"] = path
    if ser is None:
        print("No Arduino serial port found")
        return
    print(f"Arduino on {path}")
    send("WATER_OFF")
    send("LIGHT_OFF")
    while True:
        try:
            raw = ser.readline().decode("utf-8", errors="ignore").strip()
        except Exception:
            time.sleep(0.2)
            continue
        parsed = parse_line(raw)
        if not parsed:
            continue
        m_raw, l_raw = parsed
        moisture = scale_inverted(m_raw, CFG["moistureDry"], CFG["moistureWet"])
        light = scale_inverted(l_raw, CFG["lightDark"], CFG["lightDay"])
        with LOCK:
            STATE["moisture_raw"] = m_raw
            STATE["light_raw"] = l_raw
            STATE["moisture"] = moisture
            STATE["light"] = light


def auto_loop() -> None:
    while True:
        time.sleep(1)
        now = time.time()
        with LOCK:
            last = STATE["last_auto"]
            moisture = STATE["moisture"]
            light = STATE["light"]
            green = STATE["green"]
            lamp = STATE["lamp"]
        if last == 0:
            with LOCK:
                STATE["last_auto"] = now
            continue
        if now - last < CFG["autoSeconds"]:
            continue
        with LOCK:
            STATE["last_auto"] = now
        profile = classify(green)
        if moisture < profile["low"]:
            threading.Thread(target=water_pulse, daemon=True).start()
        if light < CFG["lightOnBelow"] and not lamp:
            set_lamp(True)


def gen_frames(cap):
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        g, y, d = analyze(frame)
        profile = classify(g)
        with LOCK:
            moisture = STATE["moisture"]
            short, tone = health(g, moisture, profile)
            STATE["green"] = g
            STATE["yellow"] = y
            STATE["dark"] = d
            STATE["profile"] = profile["label"]
            STATE["status"] = short
            STATE["status_tone"] = tone
        _, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        yield (
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
        )


app = Flask(__name__)

def load_page() -> str:
    return (ROOT / "kiosk.html").read_text()



@app.get("/")
def home():
    return load_page()


@app.get("/video")
def video():
    cap = CAP
    if cap is None:
        return "No camera", 503
    return Response(gen_frames(cap), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/status")
def status():
    with LOCK:
        s = dict(STATE)
    profile = classify(s["green"])
    last = s["last_auto"] or time.time()
    auto_in = max(0.0, CFG["autoSeconds"] - (time.time() - last))
    return jsonify(
        {
            "moisture": s["moisture"],
            "light": s["light"],
            "green": s["green"],
            "yellow": s["yellow"],
            "dark": s["dark"],
            "pump": s["pump"],
            "lamp": s["lamp"],
            "profile": s["profile"],
            "status": s["status"],
            "status_tone": s["status_tone"],
            "low": profile["low"],
            "high": profile["high"],
            "camera": s["camera"],
            "serial": s["serial"],
            "auto_in": auto_in,
            "moisture_raw": s["moisture_raw"],
            "light_raw": s["light_raw"],
        }
    )


@app.post("/water")
def water():
    threading.Thread(target=water_pulse, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/light")
def light():
    with LOCK:
        on = not STATE["lamp"]
    set_lamp(on)
    return jsonify({"ok": True, "lamp": on})


def main() -> None:
    global CAP
    cap, cam_idx = find_camera()
    CAP = cap
    with LOCK:
        STATE["camera"] = cam_idx
    if cap is None:
        print("No camera found on /dev/video0-2")
    else:
        print(f"Camera index {cam_idx}")
    threading.Thread(target=serial_loop, daemon=True).start()
    threading.Thread(target=auto_loop, daemon=True).start()
    print(
        f"Canopy kiosk on http://127.0.0.1:{CFG['flaskPort']}/  "
        "(LAN bind, do not port-forward)"
    )
    app.run(host=CFG["flaskHost"], port=CFG["flaskPort"], threaded=True)


if __name__ == "__main__":
    main()
