"""Watering safety guard: daily caps, min interval, implausible-reading lockout.

Pure logic (no Flask/serial) so it can be unit tested. plant_dashboard.py asks
`guard.check(...)` before every pump pulse and feeds every reading through
`guard.observe_reading(...)`.

Lockout persists to disk so a reboot doesn't clear it; only the manual reset
(POST /pump/reset or the kiosk button) does.
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_LIMITS = {
    "maxPulsesPerDay": 6,          # auto + manual pulses per local day
    "maxPumpMsPerDay": 15000,      # total pump on-time per local day
    "minPulseIntervalSec": 1800,   # auto pulses: at least 30 min apart
    "rawMin": 50,                  # analogRead below this = shorted / bogus
    "rawMax": 1000,                # above this = open circuit / unplugged probe
    "dryMarginRaw": 40,            # raw beyond moistureDry+margin = probe in air
    "jumpRaw": 200,                # sudden dry jump between consecutive samples
    "jumpWindowSec": 30,
    "noResponsePulses": 3,         # pulses in a row with no moisture rise
    "noResponseMinRise": 2.0,      # % rise expected after a pulse
    "noResponseSettleSec": 300,    # wait this long after a pulse before judging the rise
}


@dataclass
class WateringGuard:
    state_path: Path
    limits: dict = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    tz: ZoneInfo = ZoneInfo("America/Los_Angeles")
    day: str = ""
    pulses_today: int = 0
    pump_ms_today: int = 0
    last_auto_pulse: float = 0.0
    lockout: str | None = None
    lockout_at: float = 0.0
    no_response: int = 0
    _recent: deque = field(default_factory=lambda: deque(maxlen=20))
    _moist_at_pulse: float | None = None
    _pulse_at: float = 0.0

    # ---------- persistence ----------
    @classmethod
    def load(cls, state_path: Path, limits: dict | None = None) -> "WateringGuard":
        g = cls(state_path=Path(state_path))
        if limits:
            g.update_limits(limits)
        try:
            data = json.loads(g.state_path.read_text())
            for k in ("day", "pulses_today", "pump_ms_today", "last_auto_pulse",
                      "lockout", "lockout_at", "no_response"):
                if k in data:
                    setattr(g, k, data[k])
        except (OSError, ValueError):
            pass
        return g

    def save(self) -> None:
        data = {k: getattr(self, k) for k in (
            "day", "pulses_today", "pump_ms_today", "last_auto_pulse",
            "lockout", "lockout_at", "no_response")}
        try:
            self.state_path.write_text(json.dumps(data, indent=2) + "\n")
        except OSError:
            pass

    def update_limits(self, cfg: dict) -> None:
        for k in DEFAULT_LIMITS:
            if k in cfg:
                self.limits[k] = cfg[k]

    # ---------- helpers ----------
    def _roll_day(self, now: float) -> None:
        d = datetime.fromtimestamp(now, self.tz).strftime("%Y-%m-%d")
        if d != self.day:
            self.day = d
            self.pulses_today = 0
            self.pump_ms_today = 0

    def trip(self, reason: str, now: float | None = None) -> None:
        if self.lockout is None:
            self.lockout = reason
            self.lockout_at = now or time.time()
            self.save()

    def reset(self) -> None:
        self.lockout = None
        self.lockout_at = 0.0
        self.no_response = 0
        self._recent.clear()
        self.save()

    # ---------- readings ----------
    def observe_reading(self, raw: int, moisture_pct: float, moisture_dry: int,
                        now: float | None = None, pumping: bool = False) -> str | None:
        """Returns a lockout reason if this reading is implausible."""
        now = now or time.time()
        L = self.limits
        reason = None
        if raw < L["rawMin"] or raw > L["rawMax"]:
            reason = f"moisture raw {raw} out of range ({L['rawMin']}-{L['rawMax']}): probe shorted or unplugged"
        elif raw > moisture_dry + L["dryMarginRaw"]:
            reason = f"moisture raw {raw} drier than air calibration ({moisture_dry}): probe likely out of soil"
        elif not pumping:
            for t, r in self._recent:
                if now - t <= L["jumpWindowSec"] and raw - r >= L["jumpRaw"]:
                    reason = f"moisture jumped dry by {raw - r} raw in {int(now - t)}s: probe likely pulled"
                    break
        self._recent.append((now, raw))
        if (self._moist_at_pulse is not None and not pumping
                and now - self._pulse_at >= L.get("noResponseSettleSec", 0)):
            # first reading after the settle window decides "did it respond?"
            # (judging the very next sample, ~200 ms after the pump stops, gave
            # false "no rise" counts because water hadn't reached the probe yet)
            if moisture_pct - self._moist_at_pulse >= L["noResponseMinRise"]:
                self.no_response = 0
            else:
                self.no_response += 1
                if self.no_response >= L["noResponsePulses"]:
                    reason = reason or (f"{self.no_response} pulses with no moisture rise: "
                                        "reservoir empty, line off, or probe not in this pot")
            self._moist_at_pulse = None
            self.save()
        if reason:
            self.trip(reason, now)
        return reason

    # ---------- pump gate ----------
    def check(self, duration_ms: int, source: str, now: float | None = None) -> tuple[bool, str]:
        now = now or time.time()
        self._roll_day(now)
        L = self.limits
        if self.lockout:
            return False, f"locked out: {self.lockout}"
        if self.pulses_today >= L["maxPulsesPerDay"]:
            return False, f"daily pulse cap {L['maxPulsesPerDay']} reached"
        if self.pump_ms_today + duration_ms > L["maxPumpMsPerDay"]:
            return False, f"daily pump time cap {L['maxPumpMsPerDay']} ms reached"
        if source == "auto" and now - self.last_auto_pulse < L["minPulseIntervalSec"]:
            wait = int(L["minPulseIntervalSec"] - (now - self.last_auto_pulse))
            return False, f"min interval: next auto pulse in {wait}s"
        return True, "ok"

    def record_pulse(self, duration_ms: int, source: str, moisture_pct: float,
                     now: float | None = None) -> None:
        now = now or time.time()
        self._roll_day(now)
        self.pulses_today += 1
        self.pump_ms_today += int(duration_ms)
        if source == "auto":
            self.last_auto_pulse = now
            self._moist_at_pulse = moisture_pct
            self._pulse_at = now
        self.save()

    def status(self) -> dict:
        return {
            "lockout": self.lockout,
            "lockoutAt": self.lockout_at,
            "pulsesToday": self.pulses_today,
            "pumpMsToday": self.pump_ms_today,
            "maxPulsesPerDay": self.limits["maxPulsesPerDay"],
            "maxPumpMsPerDay": self.limits["maxPumpMsPerDay"],
        }
