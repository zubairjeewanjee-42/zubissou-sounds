# Morning Update · 2026-05-29

Cooked while you slept. Build is clean — 8,258 lines, 0 duplicate IDs,
0 orphan JS refs, 78 top-level functions, JS syntax verified.

Open the dashboard fresh to see it all:
`http://127.0.0.1:8080/zubissou-sounds.html`

---

## What's new (visible)

### 1. Yorke preset names — live
All 12 of the original presets renamed to the abstract Yorke vibe you locked in:

| Old | New |
|---|---|
| Rainy Sunday Morning | **Pyramid Hours** |
| Hot Sahara Drive | **Tassili** |
| Cooking Late Night | **Cozinha Lenta** |
| Deep Focus Sprint | **Threshold** |
| Evening Jazz Bar | **Smoke Pillar** |
| Late Night Romance | **Drawn Blinds** |
| On The Lake | **Floating Boards** |
| Piano Pilgrimage | **Hand Glyphs** |
| The Classical Hour | **Long Strings** |
| Candlelit Dinner | **Wax Hours** |
| Sunday Reset | **Recovery Days** |
| Surprise Me · Today | **Stray Hour** |

Plus **3 new "Zubair" personal-brand presets**:
- **Zubair Sleeps** (ambient, drone, very low energy)
- **Zubair Works** (Sam Wilkes territory — ambient jazz/electronic flow)
- **Open Water** (yacht week — breezy indie, tropical pop)

The Manual line that referenced "Rainy Sunday, Sahara Drive, Cooking Late"
now reads "Pyramid Hours, Tassili, Wax Hours, Hand Glyphs and more."

### 2. RECORDS / SETS toggle — live
A small toggle pill above the action row: `[ RECORDS | SETS ]`.

- **RECORDS** (default) — existing behavior. Knobs surface album channels.
- **SETS** — new. Knobs now also surface a **"Matching Sets"** chip row
  showing the top 5 presets whose knob coordinates are closest to where
  you're dialed in. The closest match glows amber. Click any chip to dial
  it in (animates the knobs to the preset's values, sets the intent text,
  cues the selection).

Persists across reloads via localStorage. Mode change is logged to telemetry.

### 3. Currently Spinning — AD shelf
A new section "Currently Spinning" below the page, between Heatmap and
Trusted Curators. Renders the 6 AD carousel albums as cards with:
- Cover, artist, album in italic Lora
- "AD" nameplate ribbon top-right
- Click → opens the album in the Codex drawer
- Section auto-hides if `assets/data/curators/aquariumdrunkard/carousel.json`
  isn't present yet

### 4. Derrick Gee shelf — live with all 6 playlists
Same card pattern but with a teal "DG" ribbon. Shows:
- Gentle Hammer (20 tracks)
- 6/8 Soul (23 tracks)
- HALL/ODO II (70 tracks)
- Yacht Club ⛵️ (42 tracks)
- Derrick Gee FM - Archive (100 tracks)
- Derrick Sleeps ☁ (46 tracks)

Click any card → plays the original Spotify playlist via your active device.

### 5. Codex now reads from Aquarium Drunkard
When you open any album in the Codex drawer:
- If it's an AD carousel pick, the AD blurb shows inline.
- Otherwise, it does a fuzzy lookup against `posts.json` (all 615 AD posts)
  by artist+album. If matched, the AD body text excerpt + author + a
  "▸ Full piece on AD" link appear in a new **From Aquarium Drunkard**
  section above the Phase 2 placeholder.
- Falls back gracefully — section hides if no match.

This means the moment Justin Gage wrote about Fela Kuti's Detroit album,
that paragraph appears in your Codex when you open Fela.

### 6. My Fingerprint includes Derrick
Now reads `derrickgee/all_tracks.json` alongside XRAY + AD. Artists who
cross-spin in canon + AD + Derrick (Bowie, Sakamoto probably) will glow
brightest amber. Meta line stays concise.

### 7. Status pill text glow
CANON / WEATHER / RADIO text now glows in matching color (mustard / teal
/ orange) when their LED is lit — same readability treatment SPOTIFY has
when connected. Uses CSS `:has()`. Falls back gracefully on older browsers.

### 8. Vampire Weekend + Spirit of Eden in canon
- **Rank 96**: Vampire Weekend (self-titled, 2008)
- **Rank 97**: Talk Talk · Spirit of Eden (1988, foundational post-rock)

Both have search_url and discogs_search_url; spotify_id is blank — open
them in the Vinyl Wall and use `+ PROMOTE TO CANON` (or paste the album
URL into row 96/97 of `top-100-albums.json`) to fill in the Spotify ID.

### 9. Curator → preset affinity map
A new `CURATOR_PRESET_AFFINITY` data structure maps Derrick's 6 playlists
to relevant presets:
- Gentle Hammer → Hand Glyphs + Long Strings
- 6/8 Soul → Drawn Blinds + Wax Hours
- Yacht Club → Open Water + Floating Boards
- Derrick Sleeps → Zubair Sleeps + Recovery Days
- HALL/ODO II + FM Archive → Stray Hour + Smoke Pillar

`getCuratorTracksForPreset(presetId)` returns the relevant Derrick tracks.
Not yet wired into the play pipeline — foundation laid for when we want
SETS mode to actually play curator tracks instead of canon.

---

## Polish + smoothness

- **Modal entrance animation** — soft fade + scale-in (220ms cubic-bezier).
- **Smooth scroll** across the whole page.
- **Reduced-motion respect** — anyone with that preference set gets
  ~zero animation. Accessibility win.
- **Modal close button** has hover scale + active press feedback.
- **Sets chip** has hover lift + active press states (per the standing
  feedback-on-every-interactive rule).

---

## Page audit results

Walked the whole HTML/JS systematically. Findings:

- ✅ **0 duplicate IDs** (would cause `getElementById` collisions)
- ✅ **0 orphan JS handlers** — `pele-line` was being referenced in JS
  but had no element (got removed when Pelé came off-stage). I restored
  it as a clean `.console-message` element with proper styling — italic
  Lora, centered, fades when empty. The "Cued · ..." / "Channel built · ..."
  / "Shuffled the dials" messages now show again.
- ✅ **JS syntax clean** end-to-end.
- ✅ **78 top-level functions** all reachable and bound.
- ✅ **15 page sections** all rendering.

---

## What I deliberately did NOT do (and why)

- **Did not run any Spotify write scripts.** Per the memory you had me
  lock in last night: the app is Dev Mode permanently, writes 403,
  never bring up `clone_playlist.py` / `build_playlists.py` /
  `build_ad_playlists.py` again.
- **Did not call any paid APIs** (Anthropic or otherwise). Zero credits
  burned overnight.
- **Did not merge LLM-tagged catalog tracks into the playable pool.**
  Catalog tracks have no Spotify URIs (they came from text scrapes), so
  merging them as canon members would put unplayable items in the pool.
  Cleaner to wire them as "discovery" suggestions later, where clicking
  one fires a single Spotify search for that track (under quota).
- **Did not modify catalog.json.** Your overnight enrich_lastfm run was
  writing to it — touching it from here would have raced. The file may
  be corrupt mid-batch (I saw a JSON parse error at line 353,535) but
  the dashboard doesn't read it yet, so it doesn't break anything.
  Re-run `enrich_lastfm.py --source catalog` cleanly to rewrite it.

---

## Roadmap — clear queue for whenever you want to keep building

### Immediately doable, no Spotify writes
1. **Genius lyrics enrichment** — parallel to `enrich_lastfm.py`. Lyrics
   feed Codex depth + DJ context. Free API, token-based.
2. **Discogs credits enrichment** — producers, players, label. Free API.
   Codex depth.
3. **Wire LLM-tagged catalog as discovery suggestions** in SETS mode —
   when a preset is matched, also show 5 catalog tracks that fit the
   filter, click → 1 search call, play track.
4. **Cover art formula + generation** for the presets (DALL-E / Stable
   Diffusion). Needs your judgment on style.
5. **More curators** — NTS Radio shows, Bandcamp Daily, KEXP — same
   embed-scrape pattern that worked for Derrick.

### Needs your input
1. Approve the Derrick → preset affinity mapping (currently my
   judgment — easy to adjust the data structure).
2. Decide if the SETS chip click should also auto-PLAY, or just dial
   the knobs + cue (current behavior).
3. Lyrics depth — Genius API key (free) when ready.

### Bigger architecture pieces
1. **AI DJ (ElevenLabs)** — the marquee. Voice setup, narration insertion
   point, hook to read AD context md when tracks play.
2. **The Workshop** — concept-first AI-copilot playlist builder.
3. **AI Curator chat** in the Codex drawer — RAG over the AD knowledge
   base.

---

## Files touched tonight

- `zubissou-sounds.html` — Yorke names, new presets, RECORDS/SETS toggle
  + Sets panel, AD shelf section, Derrick shelf section, console-message
  restoration, Codex AD enrichment, status pill glow, modal polish,
  smooth scroll, reduced-motion, curator affinity map.
- `assets/data/top-100-albums.json` — Vampire Weekend (96) + Talk Talk
  Spirit of Eden (97).

Nothing else touched. Catalog tagger and Last.fm enrichment may have
been writing while I worked but I stayed away from those files.

Sleep well. Wake up and see it.
