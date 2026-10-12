# Pump: 120 V AC → 12 V DC migration

**Why:** the current pump is 120 V mains switched by a hobby relay module next to
water. A leak, a splashed relay board, or a loose screw terminal puts mains near
the reservoir. For tester units nothing in the build should be above 12 V
except the sealed, UL-listed wall adapter.

Pricing: only the Adafruit driver price was looked up (Oct 12, 2026). Everything
marked **est.** is an estimate. Check current listings before ordering.

## Bill of materials (per unit)

| Part | Recommendation | Price |
|---|---|---|
| Pump (preferred) | **Kamoer NKP 12 V peristaltic** (NKP-DC-S10B ~80 ml/min or NKP-DC-S08 ~55 ml/min, 0.25 A). It's self-priming, can run dry briefly without damage, and the liquid only touches the tube. | ~$10–20 US **est.** (found at ₹387–₹590 on Indian stores, e.g. [tntecomp NKP-DC-S08](https://www.tntecomp.com/products/kamoer-12v-0-25a-55ml-min-silicone-tube-liquid-pump)) |
| Pump (higher flow) | Kamoer KPP2-12-B10, ~150 ml/min, 0.3–0.5 A ([listing](https://www.tntecomp.com/products/kamoer-12v-0-3-0-5a-150ml-bpt-tube-double-head-liquid-peristaltic-pump)) | ~$25–40 **est.** |
| Alt: diaphragm | Generic 12 V mini diaphragm pump (385-type). Cheaper and faster but louder, and it wears if run dry | ~$8–12 **est.** |
| Driver | **[Adafruit MOSFET Driver #5648](https://www.adafruit.com/product/5648)**: AO3406 N-MOSFET, built-in 1N4007 flyback diode, 3–30 V load, 3 V+ logic, 1.5 A continuous | **$3.95** (looked up) |
| Fuse | Inline blade or 5×20 mm fuse holder on the +12 V lead, **1 A** fast-blow for a 0.25–0.5 A pump | ~$5 **est.** |
| Supply | UL-listed 12 V **2 A** wall adapter (barrel 5.5×2.1) with headroom for the pump and an optional 12 V LED lamp | ~$10 **est.** |
| 5 V for Nano/Pi | Keep the Pi's own supply, or a 12→5 V buck (≥3 A if it also powers the Pi) | ~$5 **est.** |
| Low-water sensor | Non-contact capacitive liquid-level sensor (XKC-Y25 type) taped to the reservoir wall, or a float switch | ~$5–10 **est.** |
| Leak sensor | Two exposed probes / water-sensor strip in the drip tray under the reservoir, read on a spare analog/digital pin | ~$2–5 **est.** |
| Misc | Silicone tubing to suit pump, check valve (stops siphoning when the pump is off), drip loop, wire ferrules | ~$5 **est.** |

**Per-unit pump-path total:** about $45–80 (estimate). That replaces the
relay plus the 120 V pump, so the net change to the ~$170 unit cost is small.

## Wiring

```
12 V adapter (+) ──[1 A fuse]──► Driver V+ ──► Pump (+)
                                 Driver OUT– ◄── Pump (–)      (MOSFET low-side switch)
12 V adapter (–) ──────────────► Driver GND ──┬── Nano GND     (COMMON GROUND required)
Nano D8 ───────────────────────► Driver SIG   │
                                              └── (10 kΩ D8→GND pull-down if the board lacks one)
Low-water sensor OUT ──► Nano D4 (INPUT_PULLUP if open-collector)
Leak probe ──► Nano A2
```

Notes:
- The driver is **active-HIGH**, which matches the current firmware (HIGH = pump on), so no logic change is needed.
- The flyback diode is on the board. If you build a discrete MOSFET circuit instead, put a 1N4007/1N5819 across the pump (cathode to +12 V) and use a **logic-level** FET (e.g. IRLZ44N / AO3400), not an IRF520.
- A pull-down on D8 keeps the pump off while the Nano is resetting or being flashed.
- Put the fuse as close to the adapter as practical. Keep all electronics **above** the water line, in an enclosure, with a drip loop on every wire and tube that enters it.
- The reservoir should sit lower than the plant outlet, or there should be a check valve, so the line can't siphon after the pump stops.
- Bench-test with the pump in a cup before you connect it to a plant. Measure ml per pulse and set `waterPulseMs` and the daily caps from that measurement (see watering limits PR).

## Firmware follow-ups (after the hardware arrives)
- Read the low-water sensor and refuse `WATER_*` when it's low (add `LOW:1` to the status line).
- Read the leak probe and refuse to pump while it's wet (`LEAK:1`). The Pi then locks out and alerts.
- These are not in the current PRs because the pins and sensor type aren't fixed yet.
