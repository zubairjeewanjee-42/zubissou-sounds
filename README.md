# Zubissou Listening

> A single-page music console that scores a hand-curated canon against a
> seven-axis taste model, then drives playback through the Spotify Web API.

**Live:** [zubissou-sounds.pages.dev](https://zubissou-sounds.pages.dev/) (Cloudflare Access-gated)
**Author:** Zubair Jeewanjee

---

## Overview

A zero-backend, ~8,900-line static web app that re-implements music discovery as the
*inverse of an algorithmic feed*. Where streaming services optimize for the next click,
this dashboard surfaces records that fit a user-specified moment — a seven-dimensional
intent vector (mood, energy, familiarity, era, density, head↔body, place) scored against
a hand-curated canon, then resolved to track URIs and dispatched to a Spotify Connect device.

Built as a personal capstone to demonstrate end-to-end product thinking: data modeling,
visual analytics, OAuth flows, multi-device playback dispatch, mobile-first responsive design,
and the discipline of shipping a polished surface from a single HTML file.

---

## Architecture

### Frontend — single static asset

- **One HTML file** (~8,900 lines, ~315 KB pre-gzip) containing all markup, inline CSS,
  and inline JavaScript. Deliberate choice: zero build pipeline, deterministic deploys,
  edge-cacheable as a single artifact. Trade-off accepted: longer time-to-interactive on
  first load (no code-splitting), no module isolation.
- **No framework** — vanilla DOM APIs, event delegation, IIFE-scoped modules.
- **State** lives in two layers: in-memory globals (`knobState`, `zsCurrentPresetId`,
  `zsBrowserDeviceId`) and localStorage for user-persistent settings (mode, preferred
  device, volume, vinyl view, collapsed sections).
- **CDN dependencies (3):** Chart.js for the radar/scatter/stacked-area/bar visualizations,
  Fuse.js for weighted fuzzy search over the canon, Spotify Web Playback SDK for in-browser
  audio output on desktop.

### Data layer

`assets/data/` is a versioned JSON corpus:

- `top-100-albums.json` — the canonical canon (97 entries, 88 with `spotify_id` and `cover_url`)
- `top-100-songs.json` — track-level supplement
- `birth-year-1984.json` — 20 birth-year reference entries
- `curators/{slug}/` — per-curator track exports from the scraper pipeline
- `xray/index.json` — XRAY.fm shows + track-level corpus for the breadth fingerprint
- `SCHEMA.md` — single source of truth for the album/track schema

### Spotify integration

- **Auth: OAuth 2.0 PKCE flow** — public-client pattern, no client secret in code.
  Code verifier hashed with SHA-256, base64url-encoded. Token + refresh stored in
  localStorage; refresh negotiated transparently when the access token expires.
- **Scopes (13):** `user-read-private`, `user-read-email`, `user-top-read`,
  `user-read-recently-played`, `user-read-playback-state`, `user-modify-playback-state`,
  `user-read-currently-playing`, `streaming`, `user-library-read`, `user-library-modify`,
  `playlist-read-private`, `playlist-read-collaborative`, `playlist-modify-public`,
  `playlist-modify-private`.
- **Playback dispatch is device-aware:**
  - On desktop browsers, registers the Web Playback SDK as a Spotify Connect device and
    plays in-tab.
  - On iOS Safari (where the SDK is blocked), routes playback to an external Connect
    device via the Web API, presented through a DEVICES picker that lists and persists
    a preferred target.
  - Volume control issues `PUT /me/player/volume?volume_percent=…&device_id=…` against
    the current target, debounced to 200 ms.
- **Rate-limit posture:** all reads go through `cachedSpotifyFetch`, a TTL-keyed wrapper
  with stale-while-revalidate semantics. Bulk operations (`/audio-features`, `/search`
  in loops) are explicitly avoided because the app runs in Spotify's Development Mode
  (the May 2025 policy gates Extended Quota at 250K MAU).

### The seven-knob model

Each knob is a normalized [0, 100] axis. A `knobTouched` boolean tracks user intent
(an untouched knob is treated as "open" — it does not contribute to scoring).

```
MOOD       0 = melancholy        100 = euphoric
ENERGY     0 = ambient           100 = driving
FAM↔EXP    0 = canon             100 = unknown
ERA        ←——— snapped decades + landmark single years ———→
DENSITY    0 = sparse            100 = wall of sound
HEAD↔BODY  0 = cerebral          100 = groove
PLACE      ←——— 22 regions + 1 Easter-egg planet ———→
```

`buildChannelSelection(opts)` is the playback router. Branches on a `mode` argument:

- **RECORDS** — top 10 albums by composite score; each album expanded to its track list
  (`GET /albums/{id}/tracks?limit=12`); plays as albums-in-order.
- **SETS** — track-level mix. If a preset is dialed in *and* curator-track coverage
  exists for that preset, returns those track URIs shuffled. Otherwise pulls 30 matching
  canon albums, takes one track per album, shuffles, returns 40. Never plays a full
  album in order.

The scoring function is multiplicative across touched knobs only; PLACE acts as a
hard region filter when set, and ERA snaps to seminal-year anchors (1969, 1991, 2001…)
for distance calculation rather than continuous year math.

### Visual analytics (Chart.js)

Six charts, each with a custom palette drawn from a unified `GENRE_BUCKETS` + `REGION_COLORS`
table so the visual language stays consistent across surfaces:

| Surface | Chart | Color axis |
|---|---|---|
| Taste Profile | Radar | brass (single dataset) |
| Taste Map | Scatter | head↔body gradient |
| Across Time | Stacked area | genre bucket |
| World of the Canon | Horizontal bar | per-region from `REGION_COLORS` |
| My Fingerprint | Horizontal bar | per-artist from genre palette; opacity = cross-source spread |
| Listening Heatmap | Custom 7×24 grid | density gradient |

### Curator integration

Independent curator corpora are scraped offline (see `scripts/`) and exported to JSON.
At runtime, a `CURATOR_PRESET_AFFINITY` map links scraped playlist names to preset IDs;
on a SETS-mode preset selection, the relevant curator tracks are pulled, validated for
Spotify URI shape, and merged with canon picks before shuffling.

### Mobile-first responsive system

CSS organized around two breakpoints (`560px`, `400px`) plus a `prefers-reduced-motion`
guard on every animation. Action row uses CSS `order` for modular stacking
(transport → volume → 4 aux buttons). Section headers use CSS Grid
(`minmax(0, 1fr) minmax(0, 38%)`) so meta text occupies a predictable footprint
regardless of copy length. Heavy sections (Vinyl Wall, My Spotify Playlists) are
collapsible on mobile via a JS-injected toggle, with state persisted per-section in
localStorage.

---

## Data enrichment pipeline (Python)

Stdlib-only, resumable, incremental-save scripts in `scripts/`:

- `enrich_lastfm.py` — Last.fm track metadata enrichment (playcount, listeners, top tags,
  wiki blurb). Resumable via `fetched_at` timestamps. ~5 req/s with 250ms backoff.
- `enrich_spotify.py` — One-off enrichment of canon entries with `spotify_id` + cover URL
  via the Spotify Search API.
- `scrape_xray.py` — XRAY.fm show + tracklist scraper (regex + minimal DOM walking, no
  Selenium). Outputs `assets/data/xray/index.json`.
- `scrape_spotify_curator.py` — Spotify user-as-curator scraper. Uses the public embed
  page (`open.spotify.com/embed/playlist/{id}`) to extract `__NEXT_DATA__`, parses the
  JSON-LD-ish track list, normalizes to the schema. This was the workaround for Spotify's
  May 2025 Dev Mode tightening that 403s the `/users/{id}/playlists` endpoint.
- `process_ad_data.py` — Aquarium Drunkard post + carousel processor. Builds the fuzzy
  match index used by the Codex drawer.

All scripts emit progress lines on stdout, write incrementally (`SAVE_EVERY = 25`),
and handle `KeyboardInterrupt` by flushing before exit.

---

## Deployment

- **Hosting:** Cloudflare Pages, Git-connected to the GitHub repo. Pushes to `main`
  trigger automatic builds.
- **Build:** None — Cloudflare serves the repo root as static assets.
- **Routing:** `_redirects` rewrites `/` to `/zubissou-sounds.html`.
- **Security headers:** `_headers` sets CSP, X-Frame-Options, Referrer-Policy,
  Permissions-Policy, and Strict-Transport-Security.
- **Access control:** Cloudflare Access policy in front of the public URL —
  email-allowlisted authentication required to view the site.

---

## Performance

- Single asset, gzipped, served from Cloudflare edge.
- Chart.js render is lazy — analytics charts populate after the canon JSON loads.
- Spotify reads are TTL-cached in memory for the session.
- Knob drag uses pointer events with a per-pointer-type multiplier (0.7 mouse,
  0.35 touch) to compensate for finger occlusion on small screens.
- All animations are GPU-cheap (`transform`, `opacity`, `box-shadow`) and respect
  `prefers-reduced-motion`.

---

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) — multi-tenant product pivot.

---

*The names of the curators stay off the record. The records make their way in.*

— Z.
