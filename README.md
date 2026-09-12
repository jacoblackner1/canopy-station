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

```bash
cd ~/canopy-station
git pull
source ~/home_sentinel/sentinel_env/bin/activate
python3 plant_dashboard.py
```

Your calibration lives in `station.json` (air 49 / water 21, dark 73 / daylight 10). Edit that file rather than the Python if a number changes.

## Auto rules (same as the working station)

- Water pulse is **1 second**
- Every **5 minutes**, if soil is below that plant type’s low mark, pulse once
- If light is below **40%**, turn the grow lamp on
- Plant type from green cover: lush > 45%, standard > 25%, else succulent

Manual Water / Lamp buttons still work anytime.
