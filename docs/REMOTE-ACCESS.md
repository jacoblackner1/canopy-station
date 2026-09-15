# Canopy remote access (Cloudflare Tunnel + Access)

Outside the house: `https://canopy.<your-domain>` → Cloudflare Access email OTP → the **same** dashboard that already runs at `http://<pi>:5000/`.

This does **not** rebuild Canopy. It does **not** open a router port. Water / Lamp stay privileged — Access is the login.

```
Browser → Cloudflare Access → Cloudflare Tunnel
       → cloudflared on the Pi → http://127.0.0.1:5000
```

Verified in `plant_dashboard.py`: Flask binds **`0.0.0.0:5000`**. LAN phones still use that. The tunnel uses loopback `http://127.0.0.1:5000` so it hits the same process.

Companion repo: [canopy-cloudflare-access](https://github.com/jacoblackner1/canopy-cloudflare-access)

## 1. On the Pi (once)

```bash
cd ~/canopy-station
git pull
sudo ./scripts/install_tunnel.sh
```

That installs `cloudflared`, writes `/etc/cloudflared/config.yml` from the example, and enables a systemd unit (`After=canopy-station.service`). It does not change `canopy-kiosk` or LAN `:5000`.

## 2. Create a named tunnel

On the Pi (it prints a URL — open that URL on your phone to approve):

```bash
cloudflared tunnel login
cloudflared tunnel create canopy
```

Copy the printed **UUID**. Credentials land as a JSON file (often `~/.cloudflared/<UUID>.json`). Move it onto the service account — **do not commit it**:

```bash
sudo cp ~/.cloudflared/<UUID>.json /etc/cloudflared/<UUID>.json
sudo chown cloudflared:cloudflared /etc/cloudflared/<UUID>.json
sudo chmod 600 /etc/cloudflared/<UUID>.json
```

## 3. Fill placeholders

```bash
sudo nano /etc/cloudflared/config.yml
```

| Placeholder | Replace with |
|-------------|--------------|
| `TUNNEL_UUID_HERE` | UUID from `tunnel create` (both `tunnel:` and `credentials-file:`) |
| `canopy.EXAMPLE.com` | Your hostname, e.g. `canopy.yourdomain.com` |

Leave `service: http://127.0.0.1:5000` as-is.

Point DNS at the tunnel:

```bash
cloudflared tunnel route dns canopy canopy.yourdomain.com
```

Start it:

```bash
sudo ~/canopy-cloudflare-access/scripts/validate-config.sh
sudo systemctl restart cloudflared
sudo systemctl status cloudflared --no-pager
```

## 4. Cloudflare Access (required)

Zero Trust → Access → Applications → **Self-hosted**

- Domain: the same hostname
- Policy **Allow**, Include **Emails** = only your address
- Require **One-time PIN**
- Do not Allow “Everyone”

Incognito from cellular data: you must see the Access login, not the live camera.

Details: [docs/ACCESS-POLICY.md](https://github.com/jacoblackner1/canopy-cloudflare-access/blob/main/docs/ACCESS-POLICY.md)

## 5. Validate

On the Pi:

```bash
~/canopy-cloudflare-access/scripts/healthcheck.sh http://127.0.0.1:5000
```

From a phone **off Wi-Fi**: `https://canopy.yourdomain.com` → email OTP → Water / Lamp / live cam.

From home Wi-Fi: `http://<pi-lan-ip>:5000/` still works with **no** Cloudflare.

Reboot the Pi once. `cloudflared` and `canopy-station` should both come back.

## Cut remote access quickly

```bash
sudo systemctl stop cloudflared
```

## Secrets — never git

- `/etc/cloudflared/*.json`
- `~/.cloudflared/cert.pem`
- tunnel install tokens

`plant_dashboard.py` stays LAN-bound plus loopback. Do not port-forward 5000.
