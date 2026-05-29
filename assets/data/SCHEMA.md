# Zubissou Sounds — Music Data Schema

Single source of truth for the personal music canon (top 100 albums + top 100 songs) and curated research catalogs (e.g., birth-year-1984).

Data lives twice:
- **CSV** — for editing in Google Sheets. Import → Replace current sheet.
- **JSON** — for the Zubissou Sounds dashboard to fetch at load.

When you edit the Google Sheet, re-export as CSV → drop into `assets/data/` → re-run the JSON generator (TBD: small build script or Cloudflare Worker).

---

## Files

| File | Purpose | Records |
|---|---|---|
| `top-100-albums.csv` / `.json` | Zubair's personal canon — albums you'd save in a fire | 95 (room for 5 more) |
| `top-100-songs.csv` / `.json` | Personal canon — songs (template + 5 starter rows) | 5 (fill in 95 more) |
| `birth-year-1984.csv` / `.json` | Research catalog of best albums released in your birth year | 20 |

---

## Album schema

```
rank                 — integer, 1..N
artist               — string
album                — string
year                 — integer (or empty if unknown)
genre                — primary genre, single value (e.g., "Jazz")
subgenre             — semicolon-separated secondary tags (e.g., "Spiritual; Fusion")
country              — origin country (e.g., "USA", "UK", "Brazil")
format_owned         — vinyl / CD / cassette / digital / streaming / (multiple allowed)
mood                 — single mood tag (e.g., "contemplative", "energetic", "wistful")
standout_tracks      — semicolon-separated track titles you'd point a friend to
why_i_love_it        — 1-3 sentence personal note
spotify_url          — full https://open.spotify.com/album/... URL
spotify_search_url   — pre-built search URL (click → land on Spotify search to find/paste URL)
discogs_search_url   — pre-built Discogs search URL (for vinyl lookups)
notes                — anything else (e.g., "Pick a specific record")
```

## Song schema

```
rank                 — integer, 1..N
artist               — string
track                — string
album                — string (the album this song comes from)
year                 — integer (release year)
genre                — primary genre
mood                 — mood tag
bpm_est              — estimated BPM (Spotify API will fill this auto)
why_i_love_it        — 1-3 sentence personal note
spotify_url          — full https://open.spotify.com/track/... URL
spotify_search_url   — pre-built search URL
notes                — anything else
```

## Birth-year catalog schema

Same as albums, plus `release_date` (YYYY-MM-DD) since this list is date-specific.

---

## How the Zubissou Sounds dashboard uses this

**On page load:**
1. Fetch all three JSON files.
2. Build a unified search index (Fuse.js) across artists + albums + tracks.
3. Cross-reference with live Spotify API:
   - "Of my top 100 albums, which have I streamed in the last 30 days?"
   - "Which top albums haven't I added to a playlist yet?"
4. Vinyl lookup: `format_owned` contains "vinyl" → highlight in collection view.
5. Mood-based playlist generator: filter songs by `mood` tag → auto-create Spotify playlist.

---

## Editing rules (consistency)

When updating the Google Sheets:
- **Genre** uses primary value only in `genre` column; tags go in `subgenre`.
- **Mood** is a SINGLE word. Pick from: `contemplative`, `energetic`, `melancholic`, `joyful`, `intense`, `warm`, `wistful`, `grief`, `longing`, `dancing`, `groove`, `ambient`, `urgent`, `peaceful`. Add more to the list as you go.
- **Spotify URL** — paste only the canonical `https://open.spotify.com/album/{id}` form. Drop `?si=...` tracking params before saving.
- **Format owned** — use: `vinyl`, `CD`, `cassette`, `digital`, `streaming-only`. Multiple separated by `; `.
- **Years** — 4-digit integers only. Leave blank if you don't know it.

---

## Rich DB (`assets/data/rich/`, built by `scripts/build_rich_db.py`)

The source CSV/JSON above stays the editable "spreadsheet" layer. `build_rich_db.py`
compiles it (plus the XRAY catalog) into one **unified rich-record schema** that every
knob, preset, and search reads:

```
rich/albums.json    canon top-100 albums + birth-year-1984  (source: canon | birthyear)
rich/songs.json     canon top-100 songs                      (source: canon)
rich/catalog.json   the expanded volume — all unique XRAY tracks (source: xray)
```

Each record:
```
id, type(album|song), source
artist, title, album, year, release_date
genre, subgenres[], country, region          # region mapped from country
instrumentation[], tags[]
knobs: {                                       # the 7 console dials, 0–100 (or derived)
  mood, energy, density, headbody,             #   null until the enrichment pass fills them
  era,          # nearest seminal-year anchor, derived from year
  place,        # region string, derived from country
  familiarity   # = canon rank (lower = more familiar); null for catalog
}
bpm, spotify_id, spotify_url, cover_url, standout_tracks, why_i_love_it, notes
enrichment: { status(stub|partial|complete), sources[], last_enriched }
```

**Derived now (local, no API):** `year`, `knobs.era` (snapped to seminal anchors),
`region` + `knobs.place`, `genre`, `subgenres`, `knobs.familiarity`.
**Curated by ear** (`scripts/apply_feel_tags.py`): `knobs.mood / energy / density /
headbody` for all 115 canon albums — these power the feel knobs. Edit values there
and re-run; it only touches those four fields. (XRAY catalog tracks are NOT feel-tagged
yet — too many to hand-do; they need an LLM tagging pass.)
**Still awaiting:** `bpm`, `instrumentation`, and feel tags for the expanded catalog.

**ERA anchors** (ERA knob snaps to these, reaches pre-1950): pre-1950, 1955, 1959,
1965, 1967, 1969, 1971, 1973, 1977, 1980, 1985, 1991, 1995, 2000, 2007, 2013, 2020, today.
Keep `ERA_ANCHORS` in `build_rich_db.py` and `zubissou-sounds.html` in sync.

`build_rich_db.py` is **idempotent**: re-running preserves any knob value or field you've
hand-tagged; it only (re)fills derivable/missing fields. Run: `python3 scripts/build_rich_db.py`.

---

## TODO (future)

- [ ] Auto-fill `spotify_url` for top-100-albums via Spotify Web API (search-then-match)
- [ ] Auto-fill `bpm_est` for top-100-songs via `/audio-features` endpoint
- [ ] Build sheet-sync script: Google Sheets ↔ JSON (one-way pull, runs nightly)
- [ ] Add `last_played` timestamp updated from Spotify recently-played
- [ ] Add `play_count_this_week` updated from Spotify analytics
- [ ] Add `cover_url` column populated from Spotify API
- [ ] Add Discogs API integration for vinyl value tracking
