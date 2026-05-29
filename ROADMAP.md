# Roadmap

The Phase-1 product is a personal listening room built on a hand-curated canon.
The Phase-2 pivot is the same surface, opened to any Spotify user, scoring against
**their own library** instead of a private canon.

---

## Phase 2 — multi-tenant: "Run the console over your library"

### The pitch

> Anyone who signs in with Spotify gets the same seven-knob console — but the records
> being scored are *their* saved albums, *their* top tracks, *their* recent listening.
> No curator layer. No editorial taste. Just the user's own library, made queryable by
> mood, energy, era, density, head↔body, place.

This is the "Maps for music" version of the dashboard: the user doesn't tell us where
they want to go, they tell us what kind of moment they're in.

### Architecture changes

The current single-tenant flow is:

```
static JSON canon  →  in-memory CANON  →  knob scoring  →  Spotify Playback API
```

The multi-tenant flow becomes:

```
user OAuth  →  /me/albums + /me/top/* + /me/player/recently-played
            →  in-memory user-canon
            →  enrich each track with audio features (mood/energy/etc.)
            →  knob scoring
            →  Spotify Playback API
```

Three real engineering pieces to build:

#### 1. User-library sync

- Fetch `/me/albums?limit=50` paged (Spotify caps at 50/req); typical user library
  is 100–2,000 albums.
- Cache the library client-side in IndexedDB (localStorage is ~5 MB; library payloads
  can exceed that).
- Re-sync on a TTL (24 h) or explicit user refresh.
- Background pull `/me/top/artists` and `/me/top/tracks` (short_term, medium_term,
  long_term) to populate the FAM↔EXP axis.

#### 2. Audio-features enrichment

The single-tenant version uses hand-tagged `_feel` values
(`mood`, `energy`, `density`, `headbody`) on each canon entry. For arbitrary user
libraries, those values come from Spotify's `/audio-features` endpoint:

```
mood       ← valence (0..1, mapped to 0..100)
energy     ← energy
density    ← derived from instrumentalness + speechiness + loudness
headbody   ← danceability
era        ← release_date.year
place      ← market field on the artist (less reliable; fallback to genre tags)
```

Spotify deprecated `/audio-features` for *new* apps in November 2024. Existing apps
still have access. Phase 2 requires either:

- **Continued grandfathered access** for the existing app (which is gated to 25
  Dev-Mode allowlisted users), or
- **Migration to user-provided audio-feature alternatives** — possible via Last.fm
  tags or a third-party feature provider, with a degraded but functional model.

#### 3. Extended Quota Mode

Multi-tenant requires escaping Spotify's Development Mode 25-user ceiling. As of
May 2025, Extended Quota is gated to apps with **250K+ MAU at submission**. Paths:

- **Wait-list / invite model** — operate at the 25-user cap, hand-allowlist users
  one at a time. Limits growth but works.
- **Apply for Extended Quota** — requires demonstrated traction, a product page,
  business email, screencasts, and a review process measured in weeks.
- **BYO-app model** — let advanced users register their own Spotify app and paste
  the client ID. Pushes auth burden to the user but unblocks unlimited adoption.

### Data model deltas

| Phase 1 | Phase 2 |
|---|---|
| `top-100-albums.json` (static) | User library, IndexedDB cached |
| Hand-tagged `_feel` per album | Spotify audio features per track |
| `CURATOR_PRESET_AFFINITY` (curator-to-preset) | Removed; SETS pulls one track per album from user library |
| Canon-derived radar genres | User top-artists genres |
| Server-less | Still server-less (auth flow runs in browser) |

### What we keep

- The seven-knob model itself — the scoring math is canon-agnostic.
- The console UI — every surface (knobs, intent bar, RECORDS/SETS toggle, mode lamp,
  DIALED preset pill) works unchanged.
- The mobile-first responsive system.
- The day/night theme metaphor.
- The visual analytics layer — the radar/scatter/stacked-area/bar/heatmap charts all
  re-source from user data without structural changes.

### What we drop

- The curator layer (AD, Derrick Gee, XRAY.fm) — that's the *author's* taste, not
  applicable to other users.
- The Codex Aquarium Drunkard enrichment — same reason.
- The "Currently Spinning" and "The Circle" sections.
- The 1984 birth-year shelf.

### Privacy model

- All user library data lives client-side. No server stores it.
- The only network calls are user-initiated reads against Spotify's own API.
- Tokens are scoped narrowly (no `playlist-modify` unless the user opts into save).
- Optional analytics — anonymous, aggregated, opt-in only.

### Open questions

- **Naming.** "Zubissou Listening" doesn't carry over to a multi-tenant product. The
  product name needs to land somewhere that says *"music console, by you, for the
  moment you're in"* — candidates TBD.
- **Pricing model.** Free tier vs. paid tier (BYO Spotify app required for free)?
- **Mobile app.** Native wrapper (Capacitor / Tauri) vs. PWA install?
- **Social layer.** Do users see each other's dials? Probably not in v1 — the room
  is private by default.

---

## Phase 1.5 — incremental wins before the pivot

- **Genius lyrics enrichment** (free API, token-based) — lyrics into the Codex,
  feeds intent-bar fuzzy matching against lyric content.
- **Discogs credits enrichment** (free API) — producers, players, label into the
  Codex; opens "produced by" / "session with" navigation.
- **AI DJ via ElevenLabs** — voice-synthesized track transitions; reads AD context
  + Codex notes between songs. ~5K characters/track.
- **Genre radar layered with Spotify** — the canon radar polygon stays; an outer
  polygon shows the user's actual Spotify top-genres for comparison.
- **More curators** — NTS Radio shows, Bandcamp Daily, KEXP — same embed-scrape
  pattern that worked for the existing curator set.

---

*Phase 1 ships first. Phase 2 is the bet.*
