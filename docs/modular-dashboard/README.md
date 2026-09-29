# Modular Canopy dashboard — Grok Build brief

**Approved 2026-09-29** by Jacob. Implement Grove Grid (home) + Focus Rail (detail). Bay Rack and Map & Pane are parked.

**Mockup images** (full set) live here because binary upload to this repo needs a Contents-write token:
https://github.com/jacoblackner1/canopy-cloudflare-access/tree/main/docs/modular-dashboard

Raw asset URLs:
- https://raw.githubusercontent.com/jacoblackner1/canopy-cloudflare-access/main/docs/modular-dashboard/assets/A-grove-grid-overview.jpg
- https://raw.githubusercontent.com/jacoblackner1/canopy-cloudflare-access/main/docs/modular-dashboard/assets/B-focus-rail-detail.jpg
- https://raw.githubusercontent.com/jacoblackner1/canopy-cloudflare-access/main/docs/modular-dashboard/assets/C-7day-chart-overlay.jpg
- https://raw.githubusercontent.com/jacoblackner1/canopy-cloudflare-access/main/docs/modular-dashboard/assets/D-add-plant-flow.jpg
- https://raw.githubusercontent.com/jacoblackner1/canopy-cloudflare-access/main/docs/modular-dashboard/assets/00-current-snapshot-ref.jpg
- https://raw.githubusercontent.com/jacoblackner1/canopy-cloudflare-access/main/docs/modular-dashboard/assets/00-current-7day-ref.jpg

App code to change is still this repo (`plant_dashboard.py`, `dashboard.html`, etc.).

## Product goals

- Support **multiple plants** without rebuilding the UI.
- Each plant is a module that can attach optional **sensor suites** on the Orange Pi (camera, moisture+light, pump).
- Keep the interaction language of today’s single-plant app.

## Must retain from current app

**Required behaviors**

1. **SNAPSHOT** plant photo with timestamp badge — not LIVE video.
2. Optional **Lamp** badge on the snapshot when the lamp is on.
3. Sensor bars (**Moisture**, **Light**, and green/yellow metrics) — **tap Moisture or Light → 7-day history chart** (same pattern for both). Do not remove this drill-down.
4. **Water 1s** and **Lamp** controls.
5. Plant profiles: **Lush | Standard | Succulent** with moisture target range text.
6. Header: **Canopy** + **CPU °C** + clock.
7. Dark UI with sage green accents; **phone / portrait first**.

## Approved screen flow

```
Grove Grid (home)
  ├─ tap plant card → Focus Rail (detail)
  │     └─ tap Moisture/Light bar → 7-day chart overlay
  └─ tap Add plant → Add plant sheet
        └─ name + profile + optional suite chips → Create → back to Grove
```

### A — Grove Grid overview

- Header: Canopy, CPU, clock.
- Grid of plant cards: SNAPSHOT thumb + time, name, status chip (In range / Needs water), mini moisture & light bars, Open.
- Dashed **Add plant** card.

### B — Focus Rail detail

- Plant dropdown + **+ Add plant**.
- SNAPSHOT cam + timestamp (+ Lamp badge if on).
- STATUS / In range; tappable moisture/light/green/yellow; **tap for 7-day** hint on moisture.
- Water 1s / Lamp; Auto; raw debug line OK to keep for Pi builds.
- Lush | Standard | Succulent; moisture target range; Shut down.

### C — 7-day chart overlay

- Modal/overlay over Focus Rail when a bar is tapped.
- Title plant + metric; line chart; close **X**.
- Light uses the same overlay pattern with light series data.

### D — Add plant / attach suite

- Sheet/modal: plant name, profile preset, optional suite chips (**Camera**, **Moisture+Light**, **Pump**) attached to the Orange Pi.
- Create plant / Cancel.

## Implementation notes for Grok Build

- Prefer extending `plant_dashboard.py` / `dashboard.html` (and related pages) rather than a greenfield app.
- Model plants as a list/config (name, profile, attached modules, sensor bindings).
- Grove is the index route; Focus Rail is per-plant detail (existing single-plant view becomes this).
- Chart data: reuse whatever backs `moisture.html` / `light.html` today; open as overlay or existing chart pages.
- Cloudflare Access stays outside this UI (login is already handled by the tunnel package).

## Out of scope this round

- Bay Rack hardware-first layout
- Room map navigation
- New primary controls beyond Water / Lamp / profiles / add-plant
- Storefront / 3D product imagery
