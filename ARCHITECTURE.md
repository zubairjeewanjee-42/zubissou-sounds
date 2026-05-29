# Zubissou Sounds — The Listening Station
## Architecture Summary v1

**Vision.** A personal listening station rendered as an analog hi-fi console. Press one button, the Model curates a radio block from your canon + trusted human curators + Spotify; a DJ (Pelé) narrates between tracks. Tune seven knobs to override. Tap a song to drop into the Codex — lyrics, meaning, chords, credits. Build saved playlists in the Workshop. Drop screenshots of music recs into the Inbox. Two skins: gallery-white by day, warm kissa by night. Same room, different lighting.

---

## Information Architecture

**One front door. Three side rooms.**

- **The Console** *(home)* — silent on arrival. Seven knobs, intent bar, big chrome PLAY button. Knobs preset by context (weather, time, day-of-week, location, recent telemetry).
- **Zubissou Radio** *(what PLAY does)* — the Model assembles a queue from Codex + Canon + XRAY + Spotify; AI DJ Pelé optionally narrates between tracks via ElevenLabs. *Voice = Phase 2; silent radio = Phase 1.*
- **The Codex** *(drawer)* — tap any song → drawer slides up from below with lyrics (Genius), meaning, chord progressions, production credits (Discogs), artist context (MusicBrainz/Last.fm/Wikipedia), Zubair's own notes. Persists locally; grows over time into a personal music encyclopedia.
- **The Workshop** *(side room)* — "+BUILD" nameplate. Named playlists, AI co-pilot (concept-first seed, also seed song / seed artist / mood entry), human-in-loop preview/approve, AI-generated cover art + description, vibe-coherence + energy-curve audit.
- **The Vinyl Wall** *(side panel)* — spine-view of Top-100 + Birth-Year + future catalogs, browsable, tap to load into Codex.
- **The IG Inbox** *(side door)* — drop screenshot / paste text / drop YouTube link → OCR + parse → candidate songs queued into weekly Explore radio block. *Phase 2.*

---

## The Seven Knobs

Front of console. Big tactile dials. Brass bezels, white indicator pip on rim, McIntosh-blue glow when active.

| # | Knob | Low ◀ ─── ▶ High |
|---|---|---|
| 1 | **MOOD** | melancholy ◀──▶ euphoric |
| 2 | **ENERGY** | ambient ◀──▶ driving |
| 3 | **FAMILIAR / EXPLORE** | your canon ◀──▶ never heard |
| 4 | **ERA** | pre-1970 ◀──▶ 2026 |
| 5 | **DENSITY** | sparse / single voice ◀──▶ wall of sound |
| 6 | **HEAD / BODY** | cerebral / lyrics-driven ◀──▶ physical / groove-driven |
| 7 | **PLACE** | country-level dial: ~40 musical regions (Brazil, Mali, Tuareg-Sahel, Lagos, Tokyo, Seoul, Havana, Detroit, Memphis, ECM-Scandi, Berlin, etc.) + "any" |

**Open knob semantic** — leaving a dial untouched (centered) tells the model "you decide." Touching a dial = override.

**Intent bar** (above the knobs) — free-text strip: *"their Beatles", "new contemporary", "the dark stuff", "for cooking"*. Refines or overrides knob math. The knobs are structure; the intent bar is soul.

---

## Day / Night Mode

A **silver bat-handle toggle switch** at top-center of the console — labeled `DAY` (down) / `NIGHT` (up). Click flips it. 600ms cinematic lighting dissolve.

- **DAY** — overheads on. Gallery-white walls. Even illumination. Cream VU meters cold-lit. Type: Inter / IBM Plex sans, black on white. **Same console, brightly lit.**
- **NIGHT** — overheads off. Kissa amber pendants on. **Tubes glow warm orange.** VU meters illuminated deep cream-amber. Vinyl wall edge-lit, shadowed. Pelé's nameplate gets a small reading lamp. Type: warm cream on deep walnut. **Same console, in the dark.**

The kissa equipment is *physically present* in both states. Only the lighting differs. Wes-Anderson DNA persists as **UI chrome**: Futura-caps knob nameplates, symmetric layout, Pelé as titled character ("DJ Pelé dos Santos — Curator").

---

## The Model

**Approach D: RAG over Codex + Spotify + XRAY, narrated by an LLM.**

```
PRESS PLAY
   │
   ▼
1. CONTEXT GATHER
   ├─ Knob positions (with open-knob inferences)
   ├─ Intent bar text
   ├─ Time / weather / day-of-week / location
   ├─ Recent telemetry (last 50 plays, last 20 skips, last 10 knob configurations)
   └─ User profile vector (running approve/reject stats)
   │
   ▼
2. CANDIDATE RETRIEVAL
   ├─ Local Codex hits (canon + birth-year + previously-enriched songs)
   ├─ XRAY tracklists matching place/era/mood (trusted human curators)
   ├─ Spotify recommendations API (audio-feature targets from knobs)
   └─ IG Inbox queue (pending discoveries)
   │
   ▼
3. LLM CURATION (Claude/GPT, ~$0.01–0.02 per block)
   ├─ Select & order 8–15 tracks for ~45–60 min block
   ├─ Diagnose vibe drift / energy curve
   ├─ Write per-track DJ script (Pelé voice, used for ElevenLabs in Phase 2)
   └─ Write per-track rationale ("Why this was pitched")
   │
   ▼
4. ENQUEUE → Spotify active device plays. UI shows queue, plays Codex card on tap.
   │
   ▼
5. TELEMETRY LOOP — every skip / scrub / approve / replay / save logged. Feeds future PRESS PLAY.
```

**Caching** — radio blocks are saved as JSON to localStorage on generation. Replay is free. Re-generation only on user request or when knobs change > threshold.

---

## Data Sources

| Source | What we use it for | Phase |
|---|---|---|
| **Spotify Web API** | Playback control, search, audio features, recommendations, top tracks/artists, recently played | 1 |
| **Local JSON canon** | top-100-albums, top-100-songs, birth-year-1984 | 1 |
| **Genius** | Lyrics + annotations | 1 (Codex MVP) |
| **XRAY.fm** | Trusted-curator tracklists (Beaches show + others) — scrape via Cloudflare Worker | 1 (subset) → 2 (full) |
| **Discogs** | Production / engineering credits, vinyl lookups | 2 |
| **MusicBrainz / Last.fm / Wikipedia** | Artist bios, scene context | 2 |
| **ElevenLabs** | Pelé voice synthesis for Radio | 2 |
| **Weather API (Open-Meteo)** | Knob context (free, no key) | 1 |
| **IG screenshots / pasted text** | Inbox → OCR via Tesseract.js → song candidates | 2 |
| **User telemetry** | Every interaction logged | 1 |

---

## Storage Layer

| Tier | What | Where (Phase 1) | Where (Phase 2) |
|---|---|---|---|
| **Canon** | top-100, birth-year, etc. | JSON in repo | JSON in repo (sheets-synced) |
| **Codex entries** | Per-song enrichments | localStorage (key: `codex:{spotify_id}`) | Cloudflare D1 |
| **Telemetry** | Plays, skips, knob configs, approvals | localStorage (rolling 90 days) | Cloudflare D1 |
| **Radio blocks** | Generated queues + DJ scripts | localStorage | Cloudflare R2 (replay anywhere) |
| **OAuth tokens** | Spotify access + refresh | localStorage (encrypted with WebCrypto) | Cloudflare KV (server-side refresh) |
| **IG Inbox** | Pending discoveries | — | Cloudflare D1 |

---

## Phase 1 — This Session

A single self-contained `zubissou-sounds.html` in repo root, deployable to Cloudflare Pages today. Phase 1 surfaces:

1. **The Console** — visible in DAY mode by default. All 7 knobs interactive (controlled JS state). Intent bar text input. PLAY button. DAY/NIGHT toggle (animated transition).
2. **OAuth PKCE flow** — "Connect Spotify" → opens auth → token in localStorage. Auto-refresh on expiry.
3. **Now Playing widget** — once connected, shows album art, track, artist, progress, audio-feature radar.
4. **Recent / Top** — last 50 plays, top tracks (4-week / 6-month / all-time), top artists, top genres.
5. **The Vinyl Wall** — 95 covers from `top-100-albums.json`, fuzzy-searchable (Fuse.js), tap → opens Spotify in new tab or enqueues.
6. **Cross-reference layer** — which canon albums streamed in last 30 days, which haven't been touched.
7. **Listening heatmap** — day-of-week × hour-of-day from Spotify recently-played (with caveat: only last 50 tracks; long-tail builds over time via local telemetry log).
8. **The Codex (MVP)** — tap any song → drawer slides up with: artist, album, year, genre, country (from canon if present), spotify_url, Zubair's `why_i_love_it` note. Genius lyrics fetch behind a button. *Full enrichment in Phase 2.*
9. **PLAY button mock** — generates a radio block from canon-only (no LLM in Phase 1). Acts as scaffolding for Phase 2 Model.

**Out of Phase 1:** LLM curation, ElevenLabs DJ voice, XRAY scraping, IG Inbox, Workshop save-to-Spotify, AI cover art, full Codex enrichment.

---

## Phase 2 — Next

- LLM curation pipeline (D-architecture). Workers AI or direct Anthropic API call.
- XRAY.fm scraper as Cloudflare Worker; ingests episode tracklists nightly.
- ElevenLabs Pelé voice synthesis.
- Workshop full flow: name → AI proposal → preview → approve → save to Spotify (with AI cover art via DALL-E/Imagen).
- IG Inbox.
- Codex full integrations (Genius annotations, Discogs credits, MusicBrainz bios).
- Cloudflare D1 migration for persistence.

---

## Cross-Dash Integration (Master Dash)

When a sprint starts in Master Dash, it can hit:
```
sounds.zubissou.com/?intent=focus&energy=high&density=sparse&duration=90
```
Page loads, applies knob presets, dims to NIGHT mode, presses PLAY, hides chrome. Returns to Master Dash on sprint end.

---

## Tech Stack

- **Hosting**: Cloudflare Pages
- **Access**: Cloudflare Access + Passkey (FaceID privacy)
- **Frontend**: Vanilla HTML/CSS/JS, single file for Phase 1. Tailwind via CDN.
- **Libraries**: Fuse.js (fuzzy search), Chart.js (radar + heatmap), Web Audio API (VU meter animation), CSS @property + custom properties (knob rotations + tube glow)
- **Auth**: Spotify OAuth PKCE (no client secret needed, fully browser-side)
- **APIs**: Spotify, Genius (Phase 1); Discogs, MusicBrainz, ElevenLabs (Phase 2)
- **Workers (Phase 2)**: XRAY scraper, IG OCR proxy, sheets-to-JSON sync

---

## Risks / Open Items

1. **US/UK canon bias** (73%). EXPLORE knob will lean on Spotify recs + XRAY for non-Western surfacing. May need to seed Codex with curated non-Western canon expansions.
2. **Heatmap data depth** — Spotify only returns last 50 recent plays (~30 days). Long-tail heatmap requires local telemetry log built from session-to-session appends.
3. **OAuth scope creep** — Spotify scopes needed: `user-read-private`, `user-read-email`, `user-read-currently-playing`, `user-read-playback-state`, `user-modify-playback-state`, `user-read-recently-played`, `user-top-read`, `playlist-read-private`, `playlist-modify-private`, `playlist-modify-public`, `user-library-read`, `user-library-modify`.
4. **ElevenLabs cost** — per-character pricing for Pelé voice. Cache DJ scripts; only synthesize once per script.
5. **Aesthetic discipline** — temptation to add "one more knob." Discipline = 7 on the front, fine-tuning in a drawer.

---

## XRAY shows → Spotify playlists (`scripts/build_playlists.py`)

One-time bulk job: turns each scraped XRAY show into a private Spotify playlist (name = show title as-is, description = show bio normalized to plain text, tracks in found/episode order, deduped per show). Stdlib-only Python; auth via Authorization-Code + PKCE through the registered `http://127.0.0.1:8080/zubissou-sounds.html` redirect. Token cached in `scripts/.spotify_token.json` (gitignore it — holds a refresh token).

**Why a script, not a dashboard button:** it can both search and create playlists under your account *and* write the result DB into the repo, which browser code can't do.

**Match waterfall** (XRAY tracks are text, no IDs): `track+artist+album` → exact version; same song, alternate version (live↔studio); fuzzy artist+track above threshold; else miss. Title scorer tolerates Spotify suffixes (`- Remastered`, `- Alternate Take`, `- Live`). Multi-artist slashes use the primary artist as anchor.

**State DBs** (in `assets/data/xray/`):
- `matched.json` — `norm(artist|track)` → `{uri, via, matched_*, release_date}`. Cache; re-runs skip solved tracks.
- `misses.json` — per-show "not on Spotify yet" records with full metadata + empty `knobs{}` fields for the later enrichment pass. `--retry-misses` re-attempts only these.

**Run:**
```
python3 scripts/build_playlists.py --show the-darkest-hour --dry-run   # match-rate test, creates nothing
python3 scripts/build_playlists.py --show the-darkest-hour             # build one
python3 scripts/build_playlists.py --all                               # all shows w/ tracks
python3 scripts/build_playlists.py --retry-misses                      # re-try misses only
```

**Roadmap after playlists:** (2) store every track — matched + missed — as knob-ready records; (3) enrichment pipeline fills knob coordinates from Spotify artist-genres + MusicBrainz/Discogs (ERA/GENRE/PLACE/FAMILIAR achievable; MOOD/ENERGY/DENSITY/HEAD-BODY need an LLM/3rd-party tagging pass since Spotify `/audio-features` is deprecated); (4) wire the enriched pool into the 7 knobs; (5) existing Phase 2 (LLM curation/RAG, DJ Zigby voice, Workshop).
