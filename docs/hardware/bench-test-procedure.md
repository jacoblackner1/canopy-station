# Bench test procedure (before any plant is connected)

Do this every time the firmware, the pump, or the wiring changes, and on every new test unit. Record the results on the sheet at the bottom and commit a copy (`docs/hardware/bench-logs/<unit>-<date>.md`).

**Setup:** pump outlet into an **empty measuring cup**, inlet in a jar of water, everything on a towel or tray. Keep the plant pot out of the loop. Open the dashboard at `http://<pi-lan-ip>:5000/` and a terminal on the Pi:

```bash
sudo journalctl -u canopy-station -f        # live log; look for FAULT / LOCKOUT / BLOCKED lines
curl -s http://localhost:5000/status | python3 -m json.tool   # arduino_fault, watering, leak, low_water
```

Reset between tests: `curl -X POST http://localhost:5000/pump/reset`

## 0. Pre-checks
1. Power the Pi and Nano **without** the 12 V adapter plugged in. The pump must not twitch while the Nano boots.
2. Plug the 12 V in. The pump stays off.
3. `/status` shows `arduino_fault: 0`. If it shows `3`, the watchdog reset the Nano. Press reset once and note it.
4. Status lines in the journal end with `|FAULT:0|LEAK:-|LOW:-` (sensors disabled), or with `0`/`1` once their pins are set.

## 1. Cup test (normal pulse)
1. Press **Water** on the dashboard (or `curl -X POST http://localhost:5000/water`).
2. Expect: the pump runs for `waterPulseMs` (default 1000 ms) and stops by itself. `/status` → `watering.pulsesToday` goes up by 1.
3. Pass if it stops within ±0.2 s of the set time and nothing drips afterwards (if it does, check the check valve).

## 2. USB-pull failsafe (heartbeat)
1. Temporarily set `"waterPulseMs": 8000` in `station.local.json` (the service reloads it).
2. Press **Water**, and within 2 s **pull the Nano's USB cable from the Pi**. The Nano must stay powered from 12 V/VIN for this test. If the Nano is only powered over USB, instead stop the service mid-pulse with `sudo systemctl stop canopy-station`.
3. Expect: the pump stops within **about 3 s** of the pull (`HEARTBEAT_TIMEOUT_MS`), not 8 s.
4. Reconnect or restart. `/status` shows `arduino_fault: 2` and a lockout. The dashboard refuses to water until **reset**.
5. Hard cap: send `WATER_MS:20000` through a serial monitor with the service stopped, keep sending `PING` every second, and confirm it stops at **10 s** (`PUMP_MAX_MS`).
6. Set `waterPulseMs` back.

## 3. Probe-removal lockout
1. Probe in damp soil or a wet towel. Note the moisture % on the dashboard.
2. Pull the probe out into the air.
3. Expect within a few readings: the journal shows `WATERING LOCKOUT: ... probe likely out of soil` (or `jumped dry`), and **Water** is refused.
4. Put the probe back. The lockout **stays** until you press reset (intended).
5. Also unplug the probe connector. Expect `out of range ... unplugged` and a lockout.

## 4. Leak sensor (after its pin is set and flashed)
1. Set `"leakSensorEnabled": true` in `station.local.json`.
2. Start an 8 s pulse, then touch a wet paper towel to the sensor.
3. Expect: the pump stops **immediately**, `FAULT:4`, `LEAK:1`, and the lockout is "leak detected".
4. Reset while the sensor is still wet. It must **refuse**, and the fault stays 4. Dry it, then reset. It clears.
5. Unplug the sensor's S wire. It must read `LEAK:0` (dry) with the 10 k pull-down, and **never** float between 0 and 1.

## 5. Low-water float (after its pin is set and flashed)
1. Set `"lowWaterSensorEnabled": true`.
2. Lower the reservoir below the float. After about 2 s, `LOW:1`, and **Water** is refused with "reservoir low".
3. Refill. After about 2 s, `LOW:0`, and watering works with no reset needed.
4. Unplug the float wire. It must read `LOW:1` (fail-safe).
5. Start an 8 s pulse and drop the float mid-pulse. The pump stops.

## 6. mL-per-pulse calibration
1. Empty cup on a kitchen scale (1 g ≈ 1 mL water), tared.
2. Run **5 pulses** at `waterPulseMs: 1000`, waiting 10 s between them. Reset if the daily cap blocks you, or set `"maxPulsesPerDay": 20` temporarily.
3. Weigh the result: mL/pulse = grams ÷ 5. Repeat at 2000 ms to check it's linear.
4. Pick the target water per watering for the pot (e.g. 30–60 mL for a 6" pot). Then `waterPulseMs = target_mL / (mL per 1000 ms) × 1000`.
5. Set the daily caps from the measurement: `maxPumpMsPerDay` ≈ the most water the pot should ever get in a day ÷ mL-per-ms. Put the caps back to sane values (`maxPulsesPerDay` 6).
6. Send the numbers to JARVIS so the defaults in `station.example.json` can be tuned.

## Record sheet

```
Unit: ______  Date: ______  Firmware commit: ______  Pi commit: ______
Pump: ____________  Supply: ____________  Driver: ____________

0 Pre-checks       pump quiet at boot [ ]  fault=0 [ ]  status fields ok [ ]
1 Cup test         set ____ ms  measured ____ ms  drip after? Y / N        PASS / FAIL
2 USB pull         stopped after ____ s (≤3.5)  fault=2 [ ]  locked [ ]   PASS / FAIL
  10 s hard cap    stopped after ____ s (≤10.5)                            PASS / FAIL
3 Probe out        locked [ ]  reason: ____________                        PASS / FAIL
  Probe unplugged  locked [ ]                                              PASS / FAIL
4 Leak             stop immediate [ ]  reset refused while wet [ ]  unplugged=dry [ ]  PASS / FAIL / N/A
5 Low water        blocks [ ]  auto-clears [ ]  unplugged=low [ ]  mid-pulse stop [ ]  PASS / FAIL / N/A
6 Calibration      5 × 1000 ms = ____ g → ____ mL/pulse;  5 × 2000 ms = ____ g
                   chosen waterPulseMs ____  maxPumpMsPerDay ____
Notes:
```
