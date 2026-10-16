# Jacob's return checklist (Canopy)

Everything below needs Jacob personally: approvals, money, hands on hardware, or decisions only he can make. The research, code, tests, and docs behind each item are already done and pushed. Nothing has been ordered or charged.

Prepared Oct 16, 2026.

## 1. Review and merge the PR stack (bottom up)
The PRs are stacked, each based on the one before it. Merge in this order, or review them all and merge the top one into `main`.

- [ ] #1 Firmware pump failsafes (`fix/firmware-pump-failsafe`, timed pulses, heartbeat, watchdog, fault latch)
- [ ] #2 Watering limits (`fix/watering-limits`, daily caps, min interval, probe-out lockout)
- [ ] #3 Per-unit calibration moved to untracked `station.local.json` (`fix/local-calibration`)
- [ ] #4 12 V pump migration write-up (`docs/pump-12v-migration`)
- [ ] Review follow-ups (`fix/review-followups`, serial write lock, settle window, watchdog reset detection)
- [ ] Leak and low-water sensors, disabled until pins are set (`feat/leak-lowwater-sensors`)
- [ ] 12 V BOM with verified links and the bench-test procedure (`docs/bench-test-bom-checklist`)
- [ ] This checklist (`docs/return-checklist`)

All 19 tests pass on the top of the stack (`python -m pytest -q`).

## 2. Decide and place the parts order (you order, bots don't)
Full list with links: [docs/hardware/bom-12v.md](hardware/bom-12v.md). Prices were checked Oct 15 and change, so recheck at checkout.

- [ ] Decide how many units to build now (bench unit only, or the small test-user batch). The test-unit plan budgets about $170 per unit.
- [ ] Pick the low-water sensor: ProSense FLS-VM-200 float ($18, total $73.81 per unit) or Adafruit #3397 Optomax optical ($39.95, total $95.76 per unit).
- [ ] Driver cable: Adafruit #3893 JST-to-header cable was out of stock Oct 15. Either recheck it or plan to solder a 0.1" header onto the #5648 driver.
- [ ] Place the orders (about 6 stores; Adafruit alone covers pump, driver, diodes, barrel jack, and leak sensor for $34.35).

## 3. Build and wire (after parts arrive)
Wiring: [docs/hardware/pump-12v-migration.md](hardware/pump-12v-migration.md).

- [ ] Choose the Nano pins for the sensors (D2 leak and D3 low-water are suggested).
- [ ] Add a 10 kΩ pull-down from the leak sensor's S pin to GND so an unplugged sensor reads dry.
- [ ] Drill a ~3/8" hole in the reservoir lid or wall and mount the float so its contacts are closed while water is above the switch point (a cut wire then reads "low").
- [ ] Put the 1 A fast-blow fuse in line on the 12 V supply.

## 4. Flash and deploy
- [ ] In `arduino/canopy_nano.ino` set `PIN_LEAK` and `PIN_LOW_WATER` (they are `-1` now), then re-flash the Nano.
- [ ] On the Orange Pi, **before** the first pull that includes PR #3, run `scripts/migrate_local_config.sh` so this unit's calibration is saved to `station.local.json`.
- [ ] Then `git pull` and `sudo systemctl restart canopy-station` (a pull alone doesn't reload the running code).
- [ ] In `station.local.json` set `"leakSensorEnabled": true` and `"lowWaterSensorEnabled": true`. If a sensor is enabled while its firmware pin is still `-1`, watering stays blocked on purpose.

## 5. Bench test before any plant is connected
Procedure and record sheet: [docs/hardware/bench-test-procedure.md](hardware/bench-test-procedure.md).

- [ ] Sections 0 to 6: pre-checks, cup test, USB-pull failsafe and 10 s hard cap, probe-removal lockout, leak sensor, low-water float, and mL-per-pulse calibration.
- [ ] Fill in the record sheet and commit it as `docs/hardware/bench-logs/<unit>-<date>.md`.
- [ ] Send the calibration numbers (mL per pulse, chosen `waterPulseMs`, `maxPumpMsPerDay`) to JARVIS so the defaults in `station.example.json` can be tuned.

## 6. Decisions only you can make
- [ ] Check Boeing's outside-activities / side-project policy (and whether it needs a disclosure) before Canopy is sold or shown to test users outside work.
- [ ] Shopify test store (My Store, `wv7ejn-02`): the three Canopy products stay as drafts until the hardware and software are solid. Decide when to revisit, and whether the Cloud Plan needs a subscriptions app for monthly billing.
