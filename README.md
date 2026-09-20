# Canopy station

Local plant station for **Orange Pi 3 LTS** + **Arduino Nano**. HDMI dashboard is locked to **800 × 480**. Stays on home Wi-Fi — do not port-forward.

Pump relay is inverted: **HIGH = on**, **LOW = off**. `setup()` holds the pin LOW so the 120V pump stays off at boot. Cut **hot only**. Use **COM + NO**. Leave NC empty.

## One-time setup (PuTTY)

```bash
cd ~
sudo apt update
sudo apt install -y git python3-venv python3-opencv
git clone https://github.com/jacoblackner1/canopy-station.git
cd canopy-station
python3 -m venv ~/home_sentinel/sentinel_env
source ~/home_sentinel/sentinel_env/bin/activate
pip install -r requirements.txt
chmod +x scripts/run_station.sh scripts/start_kiosk.sh
```

If `~/home_sentinel/sentinel_env` already exists from earlier work, skip the `python3 -m venv` line.

Flash `arduino/canopy_nano.ino` to the Nano from the Arduino IDE on your PC (USB). Wiring:

| Nano | Thing |
|------|--------|
| A0 | capacitive moisture analog |
| A1 | light sensor analog |
| D8 | 5V relay IN (pump) |
| D9 | review / grow light |
| 5V / GND | sensor + relay power as you already have it |

## Each time you start the station

If `install_hdmi.sh` already ran, the dashboard is a service — do **not** start a second `python3 plant_dashboard.py` (you will get `Address already in use` on port 5000).

```bash
sudo systemctl status canopy-station --no-pager
```

Manual start is only for a first-time machine with no service yet:

```bash
cd ~/canopy-station
source ~/home_sentinel/sentinel_env/bin/activate
python3 plant_dashboard.py
```

On another PuTTY window (or after the dashboard is up), start the HDMI kiosk:

```bash
cd ~/canopy-station
./scripts/start_kiosk.sh
```

Dashboard is at `http://<pi-lan-ip>:5000/` on a phone or computer — full screen, with Water and Lamp. Tap **Moisture** for the 7-day chart, Set air / Set water, and another Water 1s. Tap **Light** for today’s light. HDMI is stats only.

**Remote access** (optional): Cloudflare Tunnel + Access, no router port-forward. Same UI after email OTP. See [docs/REMOTE-ACCESS.md](docs/REMOTE-ACCESS.md).

```bash
cd ~/canopy-station
git pull
sudo ./scripts/install_tunnel.sh
```

Then create the named tunnel, fill `/etc/cloudflared/config.yml`, and put Access on the hostname. LAN `:5000` and HDMI stay as they are.


The HDMI panel is stats only (camera + meters, no buttons). This image has **no desktop** — HDMI stays on the Armbian splash because nothing owns the screen. The installer now puts a tiny kiosk compositor on tty1 (cage if available, otherwise X + openbox) so Chromium can actually take HDMI.

```bash
cd ~/canopy-station
git pull
sudo ./scripts/install_hdmi.sh
sudo reboot
```

Stop the manual `python3 plant_dashboard.py` first (Ctrl+C) — the installer starts it as a service. After reboot the panel should be Canopy, not Armbian. Phone and computer keep Water / Lamp at `http://<pi-lan-ip>:5000/`; calibration lives on `/moisture` and `/light`.

If HDMI is still Armbian:

```bash
~/canopy-station/scripts/probe_display.sh
journalctl -u canopy-kiosk -n 80 --no-pager
cat ~/canopy-station/kiosk.log
```

## After I push an update

```bash
cd ~/canopy-station
git pull
sudo systemctl restart canopy-station
```

Do not run `python3 plant_dashboard.py` while the service is up — port 5000 is already taken, and the extra process will also steal (or fail to open) the camera.

**Shut down from the phone/computer page** (not HDMI). Tap **Shut down**, then tap again within 5 seconds. Same as `sudo poweroff` — HDMI goes dark, pump and lamp drop off. If the button said it failed, the one-time permission was missing. Run:

```bash
cd ~/canopy-station
git pull
sudo ./scripts/allow_poweroff.sh
sudo systemctl restart canopy-station
```


Watch with:

```bash
journalctl -u canopy-station -f
```

Watch for `Arduino on /dev/ttyUSB0` and `sensor raw … -> moisture …% light …%`. Refresh the kiosk (or rerun `./scripts/start_kiosk.sh`).

## Plant type (moisture targets)

On the phone/computer page pick **Lush**, **Standard**, or **Succulent**. HDMI shows the name only. Auto-water uses that plant’s band:

| Plant | Moisture |
|-------|----------|
| Lush houseplant | 45–75% |
| Standard houseplant | 40–70% |
| Succulent / low-water | 20–50% |

The choice is saved even after a reboot. **git pull is not enough** — the running station keeps the old code until you restart:

```bash
cd ~/canopy-station
git pull
sudo systemctl restart canopy-station
```

Then hard-refresh the phone/computer page. HDMI has no picker. If the type snaps back, the old process is still on port 5000 — restart, don’t start a second `python3`.

## Camera snapshot

The dashboard shows a **still**, not a live stream. A new frame is taken on the same tick as auto-water (default **5 minutes**, `autoSeconds` in `station.json`). Green / yellow meters come from that still. Between ticks the USB camera is closed so the Pi is not encoding video all day.

The badge on the photo shows when the last still was taken. HDMI and phone/computer share that image.

## Soil moisture

The Moisture bar on the phone/computer page still shows instantaneous %. Tap it to open `/moisture` — a **7-day** polyline of measured moisture (nights included), a dashed irrigate threshold, and pump marks. **Set air / Set water** live on that page only. Home keeps the 1-second Water button; `/moisture` has the same action (`POST /water`, same relay). HDMI keeps the bar, no chart.

## Today's light

The Light bar on the phone/computer page still shows instantaneous level. Tap it to open `/light` — a **24-hour** chart of accumulated sun-hours (Pacific midnight to midnight). **Actual** is sampled every **5 minutes** on the Pacific clock (`xx:00`, `xx:05`, `xx:10` …) from the photoresistor (or a labeled simulator if the Arduino is missing) and drawn as a smooth line through those points — not a copy of the expected curve. A late cycle uses the real elapsed seconds, then the grid resumes. Expected is a solar-shaped ramp 07:00–19:00. Auto lamp still follows that daytime window every second (sampling period ≠ lamp control). **Set dark / Set bright** on that page capture the current ADC as 0% and 100%. HDMI keeps the bar, no chart.

## Calibrate moisture (this is what makes the % accurate)

The Nano sends **analog 0–1023**. Capacitive probes read **high in air, low in water**. The percentage is:

`(dry − current) / (dry − wet) × 100`

Your old `49 / 21` values were on a 0–100 scale, so a real reading of ~497 looked like 0%. Use the analog numbers from PuTTY (`sensor raw 497/548` — first number is moisture).

**On the kiosk (easiest):**

1. Hold the probe in **air** for 5 seconds. Tap **Set air**.
2. Dunk the probe in a **glass of water** for 5 seconds. Tap **Set water**.
3. Put the probe back in the pot. Moisture should sit somewhere between 0% and 100%.

**Or edit `station.json`:**

```json
"moistureDry": 600,
"moistureWet": 250
```

Replace 600 with the air number and 250 with the water number (water must be the smaller one). Save. The dashboard reloads this file on its own.

Light uses the same inverted scale (`lightDark` in a dark room, `lightDay` in daylight). Calibrate moisture with the **lamp off**.

## Lamp makes moisture jump

Capacitive probes sit on the same 5V rail as the grow lamp / relay. Turning the lamp on sags that rail (and throws EMI at the probe), so analog moisture jumps even though the soil did not. A ~13% drop the instant the lamp comes on is this, not the plant.

The dashboard now **learns that jump** the first time you toggle the lamp and subtracts it while the lamp is on. Footer shows `lamp −47` when the offset is active.

Toggle **Lamp on** then **Lamp off** once after a pull. PuTTY should print `lamp moisture offset … adc`. After that the moisture bar should hold still when the lamp changes.

Keep sensor wires away from the lamp cord. Do not power a LED strip from the Nano’s 5V pin — give the lamp its own supply and share ground only.

## If pump / lamp work but moisture and light stay blank

## If pump / lamp work but moisture and light stay blank

1. `git pull` and restart `python3 plant_dashboard.py`.
2. Bottom-right of the kiosk now says one of:
   - `raw 497 / 548` — sensors are live
   - `saw: …` — a line arrived but did not parse
   - `Arduino silent — reflash Nano` — upload [arduino/canopy_nano.ino](https://github.com/jacoblackner1/canopy-station/blob/main/arduino/canopy_nano.ino)
   - `no Arduino` — USB serial not found

## Auto rules

- Water pulse is **1 second**
- Every **5 minutes**, if soil is below that plant type’s low mark, pulse once
- If today’s accumulated light is behind the expected curve, turn the grow lamp on (5-minute minimum). Night: off.
- Plant type is the Lush / Standard / Succulent button — the camera never picks it
- Auto water / lamp **wait** until a real sensor line has been parsed

Manual Water / Lamp buttons still work anytime.
