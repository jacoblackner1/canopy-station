# 12 V pump build: bill of materials (per unit)

Status: **nothing has been ordered.** Jacob approves and places every order himself.
Prices and stock were checked on **Oct 15, 2026**. They are pre-tax and pre-shipping, and they change, so recheck each link at checkout.

This replaces the 120 V pump and the hobby relay. Nothing in the enclosure runs above 12 V. Wiring is in [pump-12v-migration.md](pump-12v-migration.md). Firmware support for the leak and low-water sensors is in the `feat/leak-lowwater-sensors` PR, where the sensors are disabled until you set their pins.

## Recommended list

| # | Part | Pick | Qty | Price | Link |
|---|---|---|---|---|---|
| 1 | Pump | Adafruit #1150 peristaltic pump, 12 V DC. Self-priming, liquid only touches the tube, includes 2 × ½ m silicone tube with barbs | 1 | $24.95 (in stock) | https://www.adafruit.com/product/1150 |
| 2 | 12 V supply | 12 V DC **2 A** UL-listed switching adapter, 5.5 × 2.1 mm center-positive (Protection Depot) | 1 | $9.99 | https://www.protectiondepot.com/12VDC-2A-Power-Supply.html |
| 3 | Pump driver (replaces relay) | Adafruit #5648 STEMMA MOSFET driver. AO3406 N-FET, 1N4007 flyback diode built in, 3–30 V load, 3 V+ logic, active-HIGH like the current D8 | 1 | $3.95 (in stock) | https://www.adafruit.com/product/5648 |
| 4 | Flyback diode (spare / for a discrete-FET build) | Adafruit #755 1N4001, 10-pack | 1 pack | $1.50 | https://www.adafruit.com/product/755 |
| 5 | Fuse holder | Vetco 5 × 20 mm in-line fuse holder, 16 AWG leads | 1 | $2.99 | https://vetco.net/products/vupn643__5x20mm_fuse_holder_line_mount_16awg |
| 6 | Fuse | Witonics 5 × 20 mm **1 A fast-blow** glass fuse, 5-pack | 1 pack | $4.99 | https://witonics.com/products/glass-fuses-5x20mm-fast-blow-axial-1a |
| 7 | Power connector | Adafruit #368 female 2.1 mm barrel jack to screw terminal | 1 | $2.00 (in stock) | https://www.adafruit.com/product/368 |
| 8 | Leak sensor | Adafruit #4965 simple water detection sensor (digital out, 3–5 V). Goes flat in the drip tray | 1 | $1.95 (in stock) | https://www.adafruit.com/product/4965 |
| 9 | Low-water float switch | ProSense FLS-VM-200 vertical float switch. Reed, SPST, N.O./N.C. selectable by flipping the float, 1/8" NPT top mount, 1.63" stem | 1 | $18.00 (24 available) | https://www.automationdirect.com/adc/shopping/catalog/process_control_-a-_measurement/level_sensors_-a-_controllers/float_level_switches/fls-vm-200 |
| 10 | Anti-siphon | Imagitarium airline check valve, 3/16" (4 mm) tube (Petco) | 1 | $3.49 | https://www.petco.com/product/imagitarium-airline-check-valve |

**Recommended total: $73.81 per unit**, before tax and shipping. Shipping comes from 6 stores; Adafruit alone covers items 1, 3, 4, 7 and 8 ($34.35).

The tubing that ships with the #1150 pump is enough for the bench test and one pot, so there is no separate tubing line. It isn't food-grade or sterile, so rinse it before first use. Wire, jumpers and heat-shrink come from your existing stock.

## Notes before ordering
- **Driver input cable.** The #5648 takes signal and power on a JST PH 3-pin connector, or on a 0.1" header you solder on. Adafruit's matching JST-to-male-header cable (#3893) was **out of stock** on Oct 15. Solder the header and use Dupont jumpers, or check #3893 again at checkout.
- **Check-valve fit.** The #1150 tube is silicone of about 3/16" (4 mm) ID. The valve is barbed for 3/16" airline tube. Confirm the fit with a cup test, and add a zip tie if the joint drips.
- **Float mounting.** The FLS-VM-200 needs a ~3/8" hole in the reservoir lid or wall for its 1/8" NPT body and nut. Mount it so the contacts are **closed while water is above the switch point**. Then a cut wire reads "low" and the pump stays off. The firmware defaults assume this.
- **Leak sensor polarity.** The #4965 output goes HIGH when wet. The firmware defaults are `LEAK_ACTIVE_LOW = false` and `LEAK_PULLUP = false`. Add a 10 kΩ pull-down from S to GND so an unplugged sensor reads dry instead of floating. Prove that with the bench test.

## Cheaper or alternative options (not verified as recommended)
| Part | Option | Price | Link |
|---|---|---|---|
| Pump | Kamoer NKP-12V-S10B peristaltic, ~80 ml/min, 0.25 A. Earlier research found it for $19.06, but no live US listing was re-verified on Oct 15 (Indian stores list it at ₹398–₹590) | ~$19 | e.g. https://www.theengineerstore.in/products/12v-nkp-dc-s10b-mini-peristaltic-pump |
| 12 V supply | Anlapus 12 V 2 A, 5.5 × 2.1 mm | $9.99 | https://www.anlapus.com/products/asp-1220a2-us |
| Low-water | Adafruit #3397 Optomax optical level switch (no moving parts, 4.5–15.4 V supply, output 0 V when wet) | $39.95 | https://www.adafruit.com/product/3397 |

Swapping the Optomax in for the float makes the total **$95.76**. Its output goes LOW when it is submerged, so "low water" means the output is HIGH, which is still active-HIGH and fail-safe.

## Per-unit cost impact
The current test-unit plan budgets about $170 per unit. This list replaces the 120 V pump and relay module, and it adds two sensors and a fuse. Reusing the Nano, Orange Pi, probes, camera and enclosure, the pump path costs about **$74** each.
