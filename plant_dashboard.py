#!/usr/bin/env python3
"""Canopy station for Orange Pi 3 LTS + Arduino Nano.

800×480 HDMI kiosk. LAN only — do not port-forward.
Pump relay is inverted: HIGH = on. Default OFF at start.

Moisture/light use the Nano analogRead scale (0–1023). Calibrate in
station.json: probe in air → moistureDry, probe in water → moistureWet.
Capacitive probes read HIGH when dry and LOW when wet.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np
import serial
from flask import Flask, Response, jsonify, make_response, request

ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "station.json"
KIND_PATH = ROOT / "plant.kind"
LIGHT_PATH = ROOT / "light-today.json"
MOISTURE_PATH = ROOT / "moisture-week.json"
STATION_TZ = ZoneInfo("America/Los_Angeles")

# 10-bit analogRead defaults. Replace via kiosk Air/Water or station.json.
# Typical capacitive: air ~550–700, water ~220–320.
DEFAULTS = {
    "moistureDry": 600,
    "moistureWet": 250,
    "lightDark": 750,
    "lightDay": 120,
    "autoSeconds": 300,
    "waterPulseMs": 1000,
    "lightOnBelow": 40,
    "lightWindowStart": "07:00",
    "lightWindowEnd": "19:00",
    "lightDailyTarget": 6.0,
    "lightHysteresis": 0.15,
    "lightMinOnSec": 300,
    "lightOverride": "auto",
    "lampMoistDelta": 0,
    "flaskHost": "0.0.0.0",
    "flaskPort": 5000,
    "plantKind": "standard",
}

PROFILES = (
    {"id": "lush", "label": "Lush houseplant", "low": 45, "high": 75, "green": 0.45},
    {"id": "standard", "label": "Standard houseplant", "low": 40, "high": 70, "green": 0.25},
    {"id": "succulent", "label": "Succulent / low-water", "low": 20, "high": 50, "green": 0.0},
)

LINE_RE = re.compile(
    r"moisture[^0-9\-]*(-?\d+(?:\.\d+)?).*light[^0-9\-]*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
PAIR_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[|:,]\s*(-?\d+(?:\.\d+)?)")


def load_cfg() -> dict:
    cfg = dict(DEFAULTS)
    if CFG_PATH.exists():
        try:
            cfg.update(json.loads(CFG_PATH.read_text()))
        except Exception:
            pass
    return cfg


def save_cfg(cfg: dict) -> None:
    global CFG_MTIME
    out = dict(DEFAULTS)
    out.update(cfg)
    CFG_PATH.write_text(json.dumps(out, indent=2) + "\n")
    try:
        CFG_MTIME = CFG_PATH.stat().st_mtime
    except OSError:
        pass


CFG = load_cfg()
CFG_MTIME = CFG_PATH.stat().st_mtime if CFG_PATH.exists() else 0.0
LOCK = threading.Lock()
SER = None
CAP = None
JPEG = None
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
    "plant_id": PROFILES[1]["id"],
    "status": "Waiting for sensors",
    "status_tone": "muted",
    "camera": None,
    "serial": None,
    "last_auto": 0.0,
    "snapshot_at": 0.0,
    "last_line": "",
    "sensors_ok": False,
    "lamp_delta": 0,
}

# Learned when the lamp toggles: analog jump that is electrical, not soil.
LAMP_EDGE = {"at": 0.0, "before": None, "turning_on": False, "learned": False}
LIGHT = {
    "day": "",
    "acc": 0.0,
    "last_t": 0.0,
    "last_slot": 0.0,
    "samples": [],
    "lamp_since": None,
    "lamp_on_at": 0.0,
    "last_dt": 0.0,
    "last_intensity": 0.0,
    "last_raw": None,
    "source": "simulator",
}
MOIST = {
    "samples": [],
    "last_sample_t": 0.0,
    "last_pump": None,
    "last_source": None,
    "last_duration_ms": 1000,
    "source": "simulator",
}

_CPU_TEMP_PATH: Path | None = None
_CPU_TEMP_LOGGED = False


def _milli_to_c(raw: int) -> float | None:
    c = raw / 1000.0 if abs(raw) > 200 else float(raw)
    if 0 < c < 125:
        return round(c, 1)
    return None


def _temp_candidates() -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []

    def add(p: Path) -> None:
        try:
            r = p.resolve()
        except OSError:
            r = p
        if r in seen or not p.exists():
            return
        seen.add(r)
        ordered.append(p)

    add(Path("/etc/armbianmonitor/datasources/soctemp"))
    hwmon = Path("/sys/class/hwmon")
    if hwmon.is_dir():
        for p in sorted(hwmon.glob("hwmon*/temp*_input")):
            add(p)
    root = Path("/sys/class/thermal")
    if root.is_dir():
        ranked: list[Path] = []
        other: list[Path] = []
        for zone in sorted(root.glob("thermal_zone*")):
            t = zone / "temp"
            if not t.is_file():
                continue
            kind = ""
            try:
                kind = (zone / "type").read_text(encoding="utf-8").strip().lower()
            except OSError:
                pass
            if any(x in kind for x in ("cpu", "soc", "gpu")):
                ranked.append(t)
            else:
                other.append(t)
        for p in ranked + other:
            add(p)
    return ordered


def cpu_temp_c() -> float | None:
    """SoC temperature in °C (Allwinner H6 millidegrees, hwmon, or Armbian)."""
    global _CPU_TEMP_PATH, _CPU_TEMP_LOGGED
    paths = [_CPU_TEMP_PATH] if _CPU_TEMP_PATH is not None else _temp_candidates()
    for p in paths:
        if p is None:
            continue
        try:
            raw = int(p.read_text(encoding="utf-8").strip().split()[0])
        except (OSError, ValueError, IndexError):
            continue
        c = _milli_to_c(raw)
        if c is None:
            continue
        _CPU_TEMP_PATH = p
        if not _CPU_TEMP_LOGGED:
            print(f"cpu temp {c} °C from {p}", flush=True)
            _CPU_TEMP_LOGGED = True
        return c
    return None



def maybe_reload_cfg() -> None:
    global CFG, CFG_MTIME
    try:
        mtime = CFG_PATH.stat().st_mtime
    except OSError:
        return
    if mtime == CFG_MTIME:
        return
    CFG_MTIME = mtime
    CFG = load_cfg()
    CFG["plantKind"] = read_kind()
    print(
        f"reloaded station.json dry {CFG['moistureDry']} wet {CFG['moistureWet']} "
        f"dark {CFG['lightDark']} day {CFG['lightDay']} plant {CFG.get('plantKind')}",
        flush=True,
    )
    refresh_status()


def scale_inverted(raw, dry, wet) -> float:
    span = dry - wet
    if span == 0:
        return 0.0
    return max(0.0, min(100.0, (dry - raw) / span * 100.0))


def profile_by_id(kind) -> dict:
    key = str(kind or "").strip().lower()
    for p in PROFILES:
        if p["id"] == key:
            return p
    return PROFILES[1]


def read_kind() -> str:
    try:
        key = KIND_PATH.read_text(encoding="utf-8").strip().lower()
        if any(p["id"] == key for p in PROFILES):
            return key
    except OSError:
        pass
    return profile_by_id(CFG.get("plantKind"))["id"]


def write_kind(kind: str) -> None:
    profile = profile_by_id(kind)
    CFG["plantKind"] = profile["id"]
    try:
        KIND_PATH.write_text(profile["id"] + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"plant.kind save failed: {exc}", flush=True)
    try:
        save_cfg(CFG)
    except OSError as exc:
        print(f"plant save failed: {exc}", flush=True)


def current_profile() -> dict:
    return profile_by_id(read_kind())


def _hhmm(value: str, fallback: str) -> tuple[int, int]:
    raw = str(value or fallback)
    parts = raw.strip().split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return max(0, min(23, h)), max(0, min(59, m))
    except ValueError:
        parts = fallback.split(":")
        return int(parts[0]), int(parts[1])


def station_now() -> datetime:
    return datetime.now(STATION_TZ)


def day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or station_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=STATION_TZ)
    else:
        now = now.astimezone(STATION_TZ)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight, midnight + timedelta(days=1)


def light_slot(now: datetime | None = None) -> datetime:
    """Floor to Pacific xx:00 / xx:05 / xx:10 … — not UTC epoch/300."""
    now = now or station_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=STATION_TZ)
    else:
        now = now.astimezone(STATION_TZ)
    minute = now.minute - (now.minute % 5)
    return now.replace(minute=minute, second=0, microsecond=0)


def light_window_minutes() -> tuple[int, int]:
    sh, sm = _hhmm(CFG.get("lightWindowStart"), "07:00")
    eh, em = _hhmm(CFG.get("lightWindowEnd"), "19:00")
    return sh * 60 + sm, eh * 60 + em


def solar_progress(frac: float) -> float:
    p = max(0.0, min(1.0, frac))
    return 0.5 * (1.0 - math.cos(math.pi * p))


def expected_light_at(now: datetime | None = None) -> float:
    now = now or station_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=STATION_TZ)
    else:
        now = now.astimezone(STATION_TZ)
    start_m, end_m = light_window_minutes()
    mins = now.hour * 60 + now.minute + now.second / 60.0
    target = float(CFG.get("lightDailyTarget") or 6.0)
    if end_m <= start_m:
        return 0.0
    if mins <= start_m:
        return 0.0
    if mins >= end_m:
        return target
    return target * solar_progress((mins - start_m) / (end_m - start_m))


def expected_series_payload(now: datetime | None = None) -> list[dict]:
    now = now or station_now()
    start_m, end_m = light_window_minutes()
    target = float(CFG.get("lightDailyTarget") or 6.0)
    midnight, next_mid = day_bounds(now)
    start_ts = midnight.timestamp()
    end_ts = next_mid.timestamp()
    step = 5 * 60
    out = []
    t = start_ts
    while t <= end_ts + 1:
        mins = (t - start_ts) / 60.0
        if mins <= start_m:
            v = 0.0
        elif mins >= end_m:
            v = target
        else:
            v = target * solar_progress((mins - start_m) / max(1.0, end_m - start_m))
        out.append({"t": int(t * 1000), "v": round(v, 4), "lamp": False})
        t += step
    if not out or out[-1]["t"] < int(end_ts * 1000):
        out.append({"t": int(end_ts * 1000), "v": target, "lamp": False})
    return out


def in_light_window(now: datetime | None = None) -> bool:
    now = now or station_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=STATION_TZ)
    else:
        now = now.astimezone(STATION_TZ)
    start_m, end_m = light_window_minutes()
    mins = now.hour * 60 + now.minute + now.second / 60.0
    return start_m <= mins < end_m


LIGHT_SAMPLE_SEC = 300
LIGHT_KEEP = 2880


def prune_light_samples(samples: list, midnight_ms: int) -> list:
    return [p for p in samples if int(p.get("t") or 0) >= midnight_ms][-LIGHT_KEEP:]


def load_light_day() -> None:
    if not LIGHT_PATH.exists():
        return
    try:
        data = json.loads(LIGHT_PATH.read_text())
    except Exception:
        return
    today = station_now().strftime("%Y-%m-%d")
    if data.get("day") != today:
        return
    midnight, _ = day_bounds()
    midnight_ms = int(midnight.timestamp() * 1000)
    LIGHT["day"] = today
    LIGHT["acc"] = float(data.get("acc") or 0)
    LIGHT["samples"] = prune_light_samples(list(data.get("samples") or []), midnight_ms)
    LIGHT["lamp_since"] = data.get("lamp_since")
    LIGHT["last_t"] = float(data.get("last_t") or 0)
    LIGHT["last_slot"] = float(data.get("last_slot") or 0)
    if LIGHT["samples"]:
        last = LIGHT["samples"][-1]
        if not LIGHT["last_t"]:
            LIGHT["last_t"] = float(last["t"]) / 1000.0
        if not LIGHT["last_slot"]:
            LIGHT["last_slot"] = float(last["t"]) / 1000.0
        LIGHT["acc"] = float(last.get("v") or LIGHT["acc"])


def save_light_day() -> None:
    try:
        LIGHT_PATH.write_text(
            json.dumps(
                {
                    "day": LIGHT["day"],
                    "acc": LIGHT["acc"],
                    "samples": LIGHT["samples"][-LIGHT_KEEP:],
                    "lamp_since": LIGHT["lamp_since"],
                    "last_t": LIGHT["last_t"],
                    "last_slot": LIGHT["last_slot"],
                }
            )
            + "\n"
        )
    except OSError as exc:
        print(f"light-today save failed: {exc}", flush=True)


WEEK_MS = 7 * 24 * 3600 * 1000
MOIST_KEEP = 2500


def _week_start_ms(now: datetime) -> int:
    midnight, _ = day_bounds(now)
    start = midnight
    for _ in range(6):
        start = day_bounds(start - timedelta(hours=20))[0]
    return int(start.timestamp() * 1000)


def _week_end_ms(now: datetime) -> int:
    _, nxt = day_bounds(now)
    return int(nxt.timestamp() * 1000)


def simulated_moisture_week(now: datetime | None = None) -> list:
    now = now or station_now()
    start_ms = _week_start_ms(now)
    end_ms = int(now.timestamp() * 1000)
    step = 5 * 60 * 1000
    out = []
    v = 58.0
    last_pump = start_ms - 12 * 3600 * 1000
    t = start_ms
    day = now.strftime("%Y-%m-%d")
    while t <= end_ms:
        noise = (_u01(f"m-{day}-{t}") - 0.48) * 4.2
        v = max(14.0, min(90.0, v - 0.28 + noise))
        if v < 40 and t - last_pump > 9 * 3600 * 1000:
            out.append(
                {
                    "t": t,
                    "v": round(v, 2),
                    "pump": True,
                    "pump_event": "start",
                    "source": "auto",
                    "durationMs": 1000,
                    "raw": None,
                }
            )
            v = min(88.0, v + 12 + _u01(f"w-{t}") * 8)
            last_pump = t
            out.append(
                {
                    "t": t + 1000,
                    "v": round(v, 2),
                    "pump": False,
                    "pump_event": "stop",
                    "source": "auto",
                    "durationMs": 1000,
                    "raw": None,
                }
            )
            t += step
            continue
        out.append(
            {
                "t": t,
                "v": round(v, 2),
                "pump": False,
                "pump_event": None,
                "source": None,
                "raw": None,
            }
        )
        t += step
    return out[-MOIST_KEEP:]


def prune_moisture(samples: list, now_ms: int) -> list:
    cut = now_ms - WEEK_MS
    return [p for p in samples if int(p.get("t") or 0) >= cut][-MOIST_KEEP:]


def save_moisture_week() -> None:
    try:
        MOISTURE_PATH.write_text(
            json.dumps(
                {
                    "samples": MOIST["samples"][-MOIST_KEEP:],
                    "last_pump": MOIST["last_pump"],
                    "last_source": MOIST["last_source"],
                    "last_duration_ms": MOIST["last_duration_ms"],
                }
            )
            + "\n"
        )
    except OSError as exc:
        print(f"moisture-week save failed: {exc}", flush=True)


def load_moisture_week() -> None:
    if not MOISTURE_PATH.exists():
        return
    try:
        data = json.loads(MOISTURE_PATH.read_text())
    except Exception:
        return
    now_ms = int(station_now().timestamp() * 1000)
    MOIST["samples"] = prune_moisture(list(data.get("samples") or []), now_ms)
    MOIST["last_pump"] = data.get("last_pump")
    MOIST["last_source"] = data.get("last_source")
    MOIST["last_duration_ms"] = int(data.get("last_duration_ms") or 1000)


def append_moisture_sample(
    *,
    pump: bool = False,
    pump_event: str | None = None,
    source: str | None = None,
    duration_ms: int | None = None,
    persist: bool = True,
) -> None:
    """Record current moisture %. Pump events are extra immediate writes."""
    now_ms = int(time.time() * 1000)
    with LOCK:
        v = float(STATE["moisture"])
        raw = STATE["moisture_raw"]
        sensors_ok = bool(STATE["sensors_ok"])
        samples = list(MOIST["samples"])
    point = {
        "t": now_ms,
        "v": round(v, 2),
        "pump": bool(pump),
        "pump_event": pump_event,
        "source": source,
        "raw": int(raw) if raw is not None else None,
        "durationMs": duration_ms,
    }
    samples = prune_moisture(samples + [point], now_ms)
    with LOCK:
        MOIST["samples"] = samples
        MOIST["source"] = "hardware" if sensors_ok else "simulator"
        if pump_event is None:
            MOIST["last_sample_t"] = time.time()
        if pump_event == "start":
            MOIST["last_pump"] = time.time()
            MOIST["last_source"] = source
            MOIST["last_duration_ms"] = int(duration_ms or CFG.get("waterPulseMs") or 1000)
    if persist:
        save_moisture_week()


def moisture_week_payload() -> dict:
    now = station_now()
    now_ms = int(now.timestamp() * 1000)
    with LOCK:
        samples = list(MOIST["samples"])
        sensors_ok = bool(STATE["sensors_ok"])
        current = float(STATE["moisture"])
        raw = STATE["moisture_raw"]
        pump = bool(STATE["pump"])
        last_pump = MOIST["last_pump"]
        last_source = MOIST["last_source"]
        last_duration = MOIST["last_duration_ms"]
        src = MOIST.get("source") or "simulator"
    if sensors_ok:
        src = "hardware"
    if not samples and src != "hardware":
        samples = simulated_moisture_week(now)
        src = "simulator"
    vals = [float(p["v"]) for p in samples if p.get("pump_event") != "start"]
    profile = current_profile()
    return {
        "now": now_ms,
        "window": {
            "startMs": _week_start_ms(now),
            "endMs": _week_end_ms(now),
        },
        "samples": samples,
        "current": current,
        "raw": raw,
        "dry": int(CFG["moistureDry"]),
        "wet": int(CFG["moistureWet"]),
        "threshold": profile["low"],
        "high": profile["high"],
        "pump": pump,
        "lastPump": int(last_pump * 1000) if last_pump else None,
        "lastSource": last_source,
        "lastDurationMs": last_duration,
        "min7": round(min(vals), 1) if vals else 0,
        "max7": round(max(vals), 1) if vals else 0,
        "sampleCount": len(samples),
        "source": src,
        "unit": "%",
        "debug": {
            "raw": raw,
            "dry": int(CFG["moistureDry"]),
            "wet": int(CFG["moistureWet"]),
            "samples": len(samples),
            "source": src,
        },
    }


def light_today_payload() -> dict:
    now = station_now()
    midnight, next_mid = day_bounds(now)
    expected_now = expected_light_at(now)
    acc = float(LIGHT["acc"])
    lamp = bool(STATE["lamp"])
    return {
        "now": int(now.timestamp() * 1000),
        "window": {
            "start": "00:00",
            "end": "24:00",
            "startMs": int(midnight.timestamp() * 1000),
            "endMs": int(next_mid.timestamp() * 1000),
            "dayStart": CFG.get("lightWindowStart") or "07:00",
            "dayEnd": CFG.get("lightWindowEnd") or "19:00",
        },
        "target": float(CFG.get("lightDailyTarget") or 6.0),
        "expected": expected_series_payload(now),
        "actual": LIGHT["samples"],
        "accumulated": acc,
        "expectedNow": expected_now,
        "delta": acc - expected_now,
        "lamp": lamp,
        "lampSince": int(LIGHT["lamp_since"] * 1000) if LIGHT["lamp_since"] else None,
        "override": CFG.get("lightOverride") or "auto",
        "unit": "sun-h",
        "debug": {
            "raw": LIGHT.get("last_raw"),
            "intensity": LIGHT.get("last_intensity"),
            "dtH": LIGHT.get("last_dt"),
            "samples": len(LIGHT["samples"]),
            "source": LIGHT.get("source") or "simulator",
            "lastSample": LIGHT["samples"][-1]["t"] if LIGHT["samples"] else None,
            "lastSlot": int(LIGHT["last_slot"] * 1000) if LIGHT.get("last_slot") else None,
            "dark": int(CFG["lightDark"]),
            "day": int(CFG["lightDay"]),
        },
    }


def _u01(seed: str) -> float:
    n = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    return n / 0xFFFFFFFF


def simulated_intensity(now: datetime, lamp: bool = False) -> float:
    """Sky + cloud model. Must not call expected_light_at / solar_progress."""
    mins = now.hour * 60 + now.minute + now.second / 60.0
    day = now.strftime("%Y-%m-%d")
    if mins < 380 or mins > 1240:
        sky = 0.04
    elif mins < 500:
        sky = 0.04 + 0.52 * ((mins - 380) / 120.0)
    elif mins > 1110:
        sky = 0.5 * max(0.0, (1240 - mins) / 130.0)
    else:
        x = (mins - 500) / 610.0
        sky = 0.4 + 0.24 * math.sin(x * math.pi)
    cloud = 0.36 + 0.64 * _u01(f"{day}-{int(mins // 17)}")
    if _u01(f"{day}-c-{int(mins // 31)}") < 0.24:
        cloud *= 0.32
    intensity = max(0.0, min(1.0, sky * cloud))
    if lamp:
        intensity = min(1.0, intensity + 0.35)
    return intensity


def append_actual_sample(
    *,
    slot: datetime,
    now_wall: float,
    intensity: float,
    dt_h: float,
    lamp: bool,
    raw: int | None,
    source: str,
) -> None:
    """One Pacific 5-minute grid point. Actual += intensity × real Δt."""
    dt_sec = max(0.0, dt_h) * 3600.0
    added = max(0.0, intensity) * max(0.0, dt_h)
    LIGHT["acc"] += added
    LIGHT["last_t"] = now_wall
    LIGHT["last_slot"] = slot.timestamp()
    LIGHT["last_dt"] = dt_h
    LIGHT["last_intensity"] = intensity
    LIGHT["last_raw"] = raw
    LIGHT["source"] = source
    point = {
        "t": int(slot.timestamp() * 1000),
        "v": round(LIGHT["acc"], 4),
        "lamp": lamp,
        "intensity": round(intensity, 4),
        "dtH": round(dt_h, 6),
        "dtSeconds": round(dt_sec, 3),
        "added": round(added, 6),
        "expected": round(expected_light_at(slot), 4),
        "raw": raw,
    }
    samples = LIGHT["samples"]
    if samples and int(samples[-1]["t"]) == point["t"]:
        samples[-1] = point
    else:
        samples.append(point)
        LIGHT["samples"] = samples[-LIGHT_KEEP:]
    save_light_day()
    print(
        f"light sample {slot.strftime('%Y-%m-%d %H:%M:%S')} "
        f"raw={raw} intensity={intensity:.3f} dt={dt_sec:.1f}s "
        f"added={added:.4f} acc={LIGHT['acc']:.4f} lamp={int(lamp)}",
        flush=True,
    )


def maybe_light_sample() -> None:
    """Append only when the Pacific 5-minute slot advances. 24h, including nights."""
    now_dt = station_now()
    now_wall = time.time()
    today = now_dt.strftime("%Y-%m-%d")
    midnight, _ = day_bounds(now_dt)
    midnight_ms = int(midnight.timestamp() * 1000)
    if LIGHT["day"] != today:
        LIGHT["day"] = today
        LIGHT["acc"] = 0.0
        LIGHT["samples"] = prune_light_samples(LIGHT["samples"], midnight_ms)
        LIGHT["last_slot"] = 0.0
        LIGHT["last_t"] = now_wall
        LIGHT["lamp_since"] = now_wall if STATE["lamp"] else None
        LIGHT["lamp_on_at"] = now_wall if STATE["lamp"] else 0.0
        if LIGHT["samples"]:
            LIGHT["acc"] = float(LIGHT["samples"][-1].get("v") or 0)
            LIGHT["last_slot"] = float(LIGHT["samples"][-1]["t"]) / 1000.0
    slot = light_slot(now_dt)
    slot_epoch = slot.timestamp()
    if slot_epoch <= float(LIGHT.get("last_slot") or 0):
        return
    last = LIGHT["last_t"] or now_wall
    gap = now_wall - last
    # Late cycle: 480s is 480s, not 300. Huge gaps (reboot) add nothing.
    dt_h = 0.0 if gap < 0 or gap > 7200 else gap / 3600.0
    with LOCK:
        raw = STATE["light_raw"]
        lamp = bool(STATE["lamp"])
        sensors_ok = bool(STATE["sensors_ok"])
        calibrated = float(STATE["light"]) / 100.0
    if sensors_ok and raw is not None:
        intensity = calibrated
        source = "hardware"
    else:
        intensity = simulated_intensity(now_dt, lamp)
        source = "simulator"
    append_actual_sample(
        slot=slot,
        now_wall=now_wall,
        intensity=intensity,
        dt_h=dt_h,
        lamp=lamp,
        raw=int(raw) if raw is not None else None,
        source=source,
    )


def light_control() -> None:
    """Hysteresis / override every 1s. Does not wait for the 5-minute sample."""
    now_dt = station_now()
    now = time.time()
    with LOCK:
        lamp = bool(STATE["lamp"])
        sensors_ok = bool(STATE["sensors_ok"])
    override = str(CFG.get("lightOverride") or "auto").lower()
    if override == "auto" and not sensors_ok:
        return
    if override == "on":
        want = True
    elif override == "off":
        want = False
    else:
        expected = expected_light_at(now_dt)
        hyst = float(CFG.get("lightHysteresis") or 0.15)
        min_on = float(CFG.get("lightMinOnSec") or 300)
        behind = LIGHT["acc"] < expected - hyst
        if not in_light_window(now_dt):
            want = False
        elif behind:
            want = True
        elif lamp and LIGHT["lamp_on_at"] and now - LIGHT["lamp_on_at"] < min_on:
            want = True
        else:
            want = False
    if want != lamp:
        set_lamp(want)
        if want:
            LIGHT["lamp_on_at"] = now
            if not LIGHT["lamp_since"]:
                LIGHT["lamp_since"] = now
        else:
            LIGHT["lamp_on_at"] = 0.0
            LIGHT["lamp_since"] = None


def light_tick() -> None:
    maybe_light_sample()
    light_control()


load_light_day()
load_moisture_week()

_p0 = current_profile()
STATE["profile"] = _p0["label"]
STATE["plant_id"] = _p0["id"]


def health(moisture: float, profile: dict, sensors_ok: bool) -> tuple[str, str]:
    if not sensors_ok:
        return "Waiting for sensors", "muted"
    if moisture < profile["low"]:
        return "Too dry", "warn"
    if moisture > profile["high"]:
        return "Too wet", "warn"
    return "In range", "ok"


def refresh_status() -> None:
    with LOCK:
        moisture = STATE["moisture"]
        sensors_ok = STATE["sensors_ok"]
        profile = current_profile()
        short, tone = health(moisture, profile, sensors_ok)
        STATE["profile"] = profile["label"]
        STATE["plant_id"] = profile["id"]
        STATE["status"] = short
        STATE["status_tone"] = tone


def find_serial():
    for path in ("/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"):
        if os.path.exists(path):
            try:
                ser = serial.Serial(
                    path,
                    9600,
                    timeout=1,
                    dsrdtr=False,
                    rtscts=False,
                )
                time.sleep(2.0)
                ser.reset_input_buffer()
                return ser, path
            except Exception as exc:
                print(f"serial {path} failed: {exc}", flush=True)
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
    if not line:
        return None
    m = LINE_RE.search(line.replace(" ", ""))
    if m and m.group(1) is not None and m.group(2) is not None:
        return int(float(m.group(1))), int(float(m.group(2)))
    if "MOISTURE:" in line.upper() and "LIGHT" in line.upper():
        try:
            rest = re.split(r"moisture:", line, flags=re.I)[1]
            moist_s, light_s = re.split(r"\|?\s*light:", rest, maxsplit=1, flags=re.I)
            return int(float(moist_s.strip())), int(float(light_s.strip()))
        except Exception:
            pass
    m = PAIR_RE.search(line)
    if m:
        return int(float(m.group(1))), int(float(m.group(2)))
    return None


def send(cmd: str) -> None:
    ser = SER
    if ser is None:
        return
    try:
        ser.write((cmd + "\n").encode("ascii"))
        ser.flush()
    except Exception as exc:
        print(f"serial write failed: {exc}", flush=True)


def water_pulse(source: str = "home") -> None:
    duration_ms = int(CFG.get("waterPulseMs") or 1000)
    with LOCK:
        if STATE["pump"]:
            return
        STATE["pump"] = True
    if source not in ("home", "moisture", "auto"):
        source = "home"
    append_moisture_sample(
        pump=True,
        pump_event="start",
        source=source,
        duration_ms=duration_ms,
    )
    send("WATER_ON")
    time.sleep(max(0.2, duration_ms / 1000.0))
    send("WATER_OFF")
    with LOCK:
        STATE["pump"] = False
    append_moisture_sample(
        pump=False,
        pump_event="stop",
        source=source,
        duration_ms=duration_ms,
    )


def set_lamp(on: bool) -> None:
    with LOCK:
        already = bool(STATE["lamp"])
        before = STATE["moisture_raw"]
        STATE["lamp"] = on
        if already != on:
            LAMP_EDGE["at"] = time.time()
            LAMP_EDGE["before"] = before
            LAMP_EDGE["turning_on"] = on
            LAMP_EDGE["learned"] = False
    send("LIGHT_ON" if on else "LIGHT_OFF")


def analyze(frame) -> tuple[float, float, float]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    yellow = cv2.inRange(hsv, (15, 40, 40), (34, 255, 255))
    pixels = max(1, frame.shape[0] * frame.shape[1])
    g = float(np.count_nonzero(green)) / pixels
    y = float(np.count_nonzero(yellow)) / pixels
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dark = float(np.count_nonzero(gray < 40)) / pixels
    return g, y, dark


def apply_raw(m_raw: int, l_raw: int) -> tuple[float, float]:
    moisture = scale_inverted(m_raw, CFG["moistureDry"], CFG["moistureWet"])
    light = scale_inverted(l_raw, CFG["lightDark"], CFG["lightDay"])
    return moisture, light


def compensate_moisture(m_raw: int) -> int:
    """Remove the DC jump that appears when the grow lamp loads the 5V rail / EMI."""
    with LOCK:
        lamp = bool(STATE["lamp"])
        pump = bool(STATE["pump"])
        at = LAMP_EDGE["at"]
        before = LAMP_EDGE["before"]
        turning_on = LAMP_EDGE["turning_on"]
        learned = LAMP_EDGE["learned"]
    delta = int(CFG.get("lampMoistDelta") or 0)
    now = time.time()
    age = now - at if at else 999.0

    if at and age < 0.45:
        with LOCK:
            STATE["lamp_delta"] = delta
        if before is not None:
            return int(before)
        return m_raw

    if at and (not learned) and 0.45 <= age <= 1.8 and before is not None and not pump:
        sample = m_raw - int(before)
        new_delta = sample if turning_on else -sample
        if 8 <= abs(new_delta) <= 180:
            blended = int(round(0.45 * delta + 0.55 * new_delta)) if delta else int(new_delta)
            CFG["lampMoistDelta"] = blended
            save_cfg(CFG)
            delta = blended
            print(
                f"lamp moisture offset {blended} adc "
                f"(edge {new_delta:+d}, before {before} now {m_raw})",
                flush=True,
            )
        with LOCK:
            LAMP_EDGE["learned"] = True
            STATE["lamp_delta"] = delta

    used = m_raw - delta if lamp and delta else m_raw
    with LOCK:
        STATE["lamp_delta"] = delta if lamp else 0
    return used


def serial_loop() -> None:
    global SER
    while True:
        ser, path = find_serial()
        SER = ser
        with LOCK:
            STATE["serial"] = path
            if ser is None:
                STATE["sensors_ok"] = False
                STATE["last_line"] = ""
        if ser is None:
            print("No Arduino serial port found — retrying in 4s", flush=True)
            time.sleep(4)
            continue
        print(f"Arduino on {path}", flush=True)
        send("WATER_OFF")
        send("LIGHT_OFF")
        logged = 0
        silent_since = time.time()
        try:
            while True:
                try:
                    raw = ser.readline().decode("utf-8", errors="ignore").strip()
                except Exception as exc:
                    print(f"serial read failed: {exc}", flush=True)
                    break
                if not raw:
                    if time.time() - silent_since > 8 and logged < 3:
                        print(
                            "Arduino silent — no sensor lines. "
                            "Reflash arduino/canopy_nano.ino then plug the Nano back into the Pi.",
                            flush=True,
                        )
                        logged += 1
                    continue
                silent_since = time.time()
                with LOCK:
                    STATE["last_line"] = raw[:80]
                parsed = parse_line(raw)
                if not parsed:
                    if logged < 12:
                        print(f"unparsed serial: {raw!r}", flush=True)
                        logged += 1
                    continue
                m_raw, l_raw = parsed
                with LOCK:
                    pumping = bool(STATE["pump"])
                    prev_raw = STATE["moisture_raw"]
                if pumping and prev_raw is not None:
                    m_used = prev_raw
                else:
                    m_used = compensate_moisture(m_raw)
                moisture, light = apply_raw(m_used, l_raw)
                with LOCK:
                    STATE["moisture_raw"] = m_raw
                    STATE["light_raw"] = l_raw
                    STATE["moisture"] = moisture
                    STATE["light"] = light
                    STATE["sensors_ok"] = True
                refresh_status()
                if logged < 8:
                    print(
                        f"sensor raw {m_raw}/{l_raw} -> "
                        f"moisture {moisture:.1f}% light {light:.1f}%  "
                        f"(cal dry {CFG['moistureDry']} wet {CFG['moistureWet']})",
                        flush=True,
                    )
                    logged += 1
        finally:
            try:
                ser.close()
            except Exception:
                pass
            SER = None
            with LOCK:
                STATE["serial"] = None
                STATE["sensors_ok"] = False
            print("Arduino serial closed — reconnecting", flush=True)
            time.sleep(2)


def grab_snapshot() -> bool:
    """Open the USB camera, take one still, then release it.

    Same cadence as auto-water. Leaving V4L2 open would keep the sensor
    streaming and burn CPU on the Pi for nothing.
    """
    global JPEG, CAP
    cap, idx = find_camera()
    CAP = cap
    with LOCK:
        STATE["camera"] = idx
    if cap is None:
        print("snapshot: no camera on /dev/video0-2", flush=True)
        return False
    frame = None
    ok = False
    # First frames after open are often dark / auto-exposure settling.
    for _ in range(8):
        ok, frame = cap.read()
        if not ok:
            break
    try:
        cap.release()
    except Exception:
        pass
    CAP = None
    if not ok or frame is None:
        print("snapshot: read failed", flush=True)
        return False
    g, y, d = analyze(frame)
    _, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    JPEG = jpg.tobytes()
    with LOCK:
        STATE["green"] = g
        STATE["yellow"] = y
        STATE["dark"] = d
        STATE["snapshot_at"] = time.time()
    refresh_status()
    print(f"snapshot {len(JPEG)} bytes green {g:.2f} yellow {y:.2f}", flush=True)
    return True


def auto_loop() -> None:
    grab_snapshot()
    with LOCK:
        STATE["last_auto"] = time.time()
    while True:
        time.sleep(1)
        maybe_reload_cfg()
        try:
            # 1s worker: lamp control every tick; sample only on Pacific 5-min slots.
            light_tick()
        except Exception as exc:
            print(f"light tick: {exc}", flush=True)
        now = time.time()
        with LOCK:
            last = STATE["last_auto"]
            moisture = STATE["moisture"]
            sensors_ok = STATE["sensors_ok"]
        if last == 0:
            with LOCK:
                STATE["last_auto"] = now
            continue
        if now - last < CFG["autoSeconds"]:
            continue
        with LOCK:
            STATE["last_auto"] = now
        grab_snapshot()
        append_moisture_sample(persist=True)
        if not sensors_ok:
            continue
        profile = current_profile()
        if moisture < profile["low"]:
            threading.Thread(target=water_pulse, args=("auto",), daemon=True).start()


app = Flask(__name__)


def load_page(mode: str = "full") -> str:
    path = ROOT / "dashboard.html"
    if not path.exists():
        path = ROOT / "kiosk.html"
    html = path.read_text()
    kind = "kiosk" if mode == "kiosk" else "full"
    resp = make_response(html.replace("{{MODE}}", kind))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def home():
    return load_page("full")


@app.get("/kiosk")
def kiosk_page():
    return load_page("kiosk")


@app.get("/video")
@app.get("/snapshot")
def snapshot():
    frame = JPEG
    if frame is None:
        return "No camera", 503
    resp = Response(frame, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store, no-cache, max-age=0"
    return resp


@app.get("/status")
def status():
    with LOCK:
        s = dict(STATE)
    profile = current_profile()
    last = s["last_auto"] or time.time()
    auto_in = max(0.0, CFG["autoSeconds"] - (time.time() - last))
    expected_now = expected_light_at()
    acc = float(LIGHT["acc"])
    return jsonify(
        {
            "moisture": float(s["moisture"]),
            "light": float(s["light"]),
            "green": float(s["green"]),
            "yellow": float(s["yellow"]),
            "dark": float(s["dark"]),
            "pump": bool(s["pump"]),
            "lamp": bool(s["lamp"]),
            "profile": s["profile"],
            "plant_id": profile["id"],
            "status": s["status"],
            "status_tone": s["status_tone"],
            "low": profile["low"],
            "high": profile["high"],
            "camera": s["camera"],
            "serial": s["serial"],
            "auto_in": auto_in,
            "moisture_raw": s["moisture_raw"],
            "light_raw": s["light_raw"],
            "last_line": s["last_line"],
            "sensors_ok": s["sensors_ok"],
            "snapshot_at": float(s.get("snapshot_at") or 0),
            "moisture_dry": CFG["moistureDry"],
            "moisture_wet": CFG["moistureWet"],
            "lamp_delta": int(s.get("lamp_delta") or 0),
            "cpu_temp": cpu_temp_c(),
            "app": "plant-select",
            "light_acc": acc,
            "light_expected": expected_now,
            "light_delta": acc - expected_now,
            "light_override": CFG.get("lightOverride") or "auto",
        }
    )


@app.post("/water")
def water():
    body = request.get_json(silent=True) or {}
    source = str(body.get("source") or "home").strip().lower()
    if source not in ("home", "moisture", "auto"):
        source = "home"
    threading.Thread(target=water_pulse, args=(source,), daemon=True).start()
    return jsonify({"ok": True, "source": source})


@app.post("/light")
def light():
    with LOCK:
        on = not STATE["lamp"]
    set_lamp(on)
    CFG["lightOverride"] = "on" if on else "off"
    try:
        save_cfg(CFG)
    except OSError:
        pass
    LIGHT["lamp_since"] = time.time() if on else None
    LIGHT["lamp_on_at"] = time.time() if on else 0.0
    return jsonify({"ok": True, "lamp": on, "override": CFG["lightOverride"]})


@app.get("/moisture")
def moisture_page():
    path = ROOT / "moisture.html"
    if not path.exists():
        return "moisture.html missing", 404
    resp = make_response(path.read_text())
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/moisture/week")
def api_moisture_week():
    return jsonify(moisture_week_payload())


@app.get("/light")
def light_page():
    path = ROOT / "light.html"
    if not path.exists():
        return "light.html missing", 404
    resp = make_response(path.read_text())
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/light/today")
def api_light_today():
    return jsonify(light_today_payload())


@app.post("/api/light/override")
def api_light_override():
    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode") or "").strip().lower()
    if mode not in ("auto", "on", "off"):
        return jsonify({"ok": False, "error": "mode"}), 400
    CFG["lightOverride"] = mode
    try:
        save_cfg(CFG)
    except OSError:
        pass
    if mode == "on":
        set_lamp(True)
        LIGHT["lamp_since"] = time.time()
        LIGHT["lamp_on_at"] = time.time()
    elif mode == "off":
        set_lamp(False)
        LIGHT["lamp_since"] = None
        LIGHT["lamp_on_at"] = 0.0
    save_light_day()
    payload = light_today_payload()
    payload["ok"] = True
    return jsonify(payload)


@app.post("/api/light/config")
def api_light_config():
    body = request.get_json(silent=True) or {}
    if "windowStart" in body:
        CFG["lightWindowStart"] = str(body["windowStart"])
    if "windowEnd" in body:
        CFG["lightWindowEnd"] = str(body["windowEnd"])
    if "dailyTarget" in body:
        CFG["lightDailyTarget"] = float(body["dailyTarget"])
    if "hysteresis" in body:
        CFG["lightHysteresis"] = float(body["hysteresis"])
    try:
        save_cfg(CFG)
    except OSError:
        pass
    payload = light_today_payload()
    payload["ok"] = True
    return jsonify(payload)


@app.post("/calibrate/<kind>")
def calibrate(kind: str):
    """Store the current analog reading as air (dry) or water (wet)."""
    mapping = {
        "air": "moistureDry",
        "water": "moistureWet",
        "dark": "lightDark",
        "day": "lightDay",
        "moistureDry": "moistureDry",
        "moistureWet": "moistureWet",
    }
    key = mapping.get(kind)
    if kind in ("reset", "reset-moisture"):
        CFG["moistureDry"] = int(DEFAULTS["moistureDry"])
        CFG["moistureWet"] = int(DEFAULTS["moistureWet"])
        save_cfg(CFG)
        print("moisture cal reset", flush=True)
        return jsonify({
            "ok": True,
            "key": "reset",
            "dry": CFG["moistureDry"],
            "wet": CFG["moistureWet"],
        })
    if key is None:
        return jsonify({"ok": False, "error": "unknown kind"}), 400
    with LOCK:
        raw = STATE["moisture_raw"] if key.startswith("moisture") else STATE["light_raw"]
        if raw is None:
            return jsonify({"ok": False, "error": "no sensor reading yet"}), 400
        CFG[key] = int(raw)
        dry, wet = CFG["moistureDry"], CFG["moistureWet"]
        dark, day = CFG["lightDark"], CFG["lightDay"]
        m_raw, l_raw = STATE["moisture_raw"], STATE["light_raw"]
    if key.startswith("moisture") and dry == wet:
        return jsonify({"ok": False, "error": "air and water cannot be the same"}), 400
    if key.startswith("light") and dark == day:
        return jsonify({"ok": False, "error": "dark and bright cannot be the same"}), 400
    save_cfg(CFG)
    global CFG_MTIME
    try:
        CFG_MTIME = CFG_PATH.stat().st_mtime
    except OSError:
        pass
    if m_raw is not None and l_raw is not None:
        moisture, light = apply_raw(int(m_raw), int(l_raw))
        with LOCK:
            STATE["moisture"] = moisture
            STATE["light"] = light
        refresh_status()
    print(f"calibrated {key} = {raw}", flush=True)
    return jsonify({
        "ok": True,
        "key": key,
        "raw": int(raw),
        "dry": CFG["moistureDry"],
        "wet": CFG["moistureWet"],
        "dark": CFG["lightDark"],
        "day": CFG["lightDay"],
    })


@app.post("/plant/<kind>")
def set_plant(kind: str):
    profile = profile_by_id(kind)
    if str(kind or "").strip().lower() != profile["id"]:
        return jsonify({"ok": False, "error": "unknown plant"}), 400
    write_kind(profile["id"])
    refresh_status()
    print(f"plant {profile['id']} moisture {profile['low']}-{profile['high']}%", flush=True)
    return jsonify(
        {
            "ok": True,
            "plant_id": profile["id"],
            "profile": profile["label"],
            "low": profile["low"],
            "high": profile["high"],
        }
    )



def _poweroff_cmds() -> list[list[str]]:
    cmds: list[list[str]] = []
    systemctl = next(
        (p for p in ("/bin/systemctl", "/usr/bin/systemctl") if Path(p).is_file()),
        None,
    )
    if systemctl:
        cmds.append(["sudo", "-n", systemctl, "start", "canopy-poweroff.service"])
        cmds.append([systemctl, "--no-ask-password", "poweroff"])
    for p in ("/sbin/poweroff", "/usr/sbin/poweroff"):
        if Path(p).is_file():
            cmds.append(["sudo", "-n", p])
    cmds.append(["loginctl", "poweroff"])
    return cmds


def _do_poweroff() -> None:
    time.sleep(0.4)
    last = "no poweroff command tried"
    for cmd in _poweroff_cmds():
        print("poweroff try: " + " ".join(cmd), flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            print("poweroff started", flush=True)
            return
        last = (r.stderr or r.stdout or f"rc={r.returncode}").strip()
        print(f"poweroff skip rc={r.returncode} {last}", flush=True)
    print(f"poweroff failed: {last}", flush=True)


@app.post("/poweroff")
def poweroff():
    """Software halt. Relays drop with the board. Requires allow_poweroff.sh."""
    cmds = _poweroff_cmds()
    if not cmds:
        return jsonify({"ok": False, "error": "poweroff not found"}), 500
    threading.Thread(target=_do_poweroff, daemon=False).start()
    return jsonify({"ok": True})



@app.after_request
def no_store(resp):
    if request.path in ("/status", "/", "/kiosk", "/light", "/api/light/today", "/snapshot", "/video"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def main() -> None:
    threading.Thread(target=serial_loop, daemon=True).start()
    threading.Thread(target=auto_loop, daemon=True).start()
    print(
        f"Canopy kiosk on http://127.0.0.1:{CFG['flaskPort']}/  "
        "(LAN bind, do not port-forward)",
        flush=True,
    )
    app.run(
        host=CFG["flaskHost"],
        port=CFG["flaskPort"],
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
