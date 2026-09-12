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

Dashboard is at `http://<pi-lan-ip>:5000/` on the home network. Chromium kiosk uses `http://127.0.0.1:5000/` so it never leaves the Pi.

## After I push an update

Stop the running dashboard (Ctrl+C in that PuTTY window), then:

```bash
cd ~/canopy-station
git pull
source ~/home_sentinel/sentinel_env/bin/activate
python3 plant_dashboard.py
```

Watch for `Arduino on /dev/ttyUSB0` and `sensor raw … -> moisture …% light …%`. Refresh the kiosk (or rerun `./scripts/start_kiosk.sh`).

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

Light uses the same inverted scale (`lightDark` in a dark room, `lightDay` in daylight).

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
- If light is below **40%**, turn the grow lamp on
- Plant type from green cover: lush > 45%, standard > 25%, else succulent
- Auto water / lamp **wait** until a real sensor line has been parsed

Manual Water / Lamp buttons still work anytime.
