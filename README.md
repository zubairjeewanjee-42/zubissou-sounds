# Zubissou Sounds · The Listening Station

> A private listening room for the always-on era.
> Seven knobs. A canon of one hundred records. The inverse of a feed.

**Live:** [zubissou-sounds.pages.dev](https://zubissou-sounds.pages.dev/)
**Built by:** [Zubair Jeewanjee](https://github.com/zubairjeewanjee-42)

---

## What it is

A personal music dashboard built as the structural opposite of an algorithmic feed.
Where streaming services chase the next click, this room asks one quieter question:
*what kind of moment is this?*

The console is a literal metaphor — a vintage hi-fi mixing desk drawn in HTML.
Seven knobs (mood, energy, familiarity, era, density, head-vs-body, place) score against
a hand-picked canon of one hundred records, then hit Spotify Web API for playback.
A curator layer — *Aquarium Drunkard*, *Derrick Gee*, twelve XRAY.fm shows — folds
trusted human taste back into the system. No engagement loop. No feed.

Designed as a personal capstone. Single HTML file, ~8,300 lines, no backend.

---

## The room, in pieces

| Surface | What it does |
|---|---|
| **The Console** | Seven-knob taste model + intent bar. Knobs stack. Untouched knobs are open to interpretation. |
| **The Codex** | A drawer that opens on any album — release date, country, lyrics, AD context, your notes. |
| **The Vinyl Wall** | The canon, as spines. Fuzzy search across artist, album, year, genre, country. |
| **Taste Profile** | Spotify last-50 tracks plotted as a radar — the shape of an ear. |
| **Taste Map** | The canon plotted by feel — mood × energy, sized by density. |
| **Across Time** | The canon walked through the decades, genre keeps the colors honest. |
| **World of the Canon** | A geography of listening — the records and the rooms they were cut in. |
| **My Fingerprint** | The artists that recur across every curator I trust. |
| **Listening Heatmap** | When the room is loudest, day-of-week × hour-of-day. |
| **Currently Spinning** | Aquarium Drunkard's daily rotation, as cards. |
| **Trusted Curators** | XRAY.fm shows, Derrick Gee playlists — sets I lean on. |
| **The Manual** | A field guide. |

---

## Stack

- **Vanilla JS** · zero framework. The constraint is the design.
- **Chart.js** for the analytics (radar, scatter, stacked area, heatmap).
- **Fuse.js** for fuzzy search across the canon.
- **Spotify Web API** + **Web Playback SDK** via PKCE OAuth.
- **Last.fm** for global playcount + listener signal.
- **Static JSON** for the canon, curators, AD posts.
- **Cloudflare Pages** for the wire. Git-connected.

---

## Aesthetic

- Palette: Wes Anderson, *The Life Aquatic*.
- Geometry: Tokyo kissa listening-bar — restraint, weight, warm wood.
- Hardware: vintage Marantz / Sansui console.
- Type: Big Shoulders for nameplates, Lora italic for copy, IBM Plex Mono for telemetry.
- Two states: **DAY** (gallery-white room, focus mode) and **NIGHT** (kissa lounge, amber lamps, tubes glowing). Same furniture, different lighting.

---

## Heads quoted

The room leans on real humans. Their taste is folded into the data layer.

- **Aquarium Drunkard** — six hundred posts, fuzzy-matched into the Codex.
- **Derrick Gee** — six sets, three hundred tracks (Spotify curator).
- **XRAY.fm** — Steven Cantor (*Beats & Pieces*), *Hot Fudge Sunday*, *On The Corner*, *Get Outta Town*, more.

---

## Local development

```bash
# Serve the file (must be on http://127.0.0.1:8080 for the Spotify redirect URI to match)
cd ~/Projects/personal/zubissou-sounds
python3 -m http.server 8080
# → open http://127.0.0.1:8080/zubissou-sounds.html
```

Data enrichment scripts live in `scripts/`. The Spotify app is registered in
[developer.spotify.com](https://developer.spotify.com/dashboard) under a
personal account; PKCE OAuth means no client secret in the page.

---

## Status

Phase 1 shipped. Phase 2 in progress:
AI DJ (ElevenLabs voice between tracks), AI Curator chat in the Codex,
Genius lyrics enrichment, Discogs credits enrichment, more curators (NTS, KEXP, Bandcamp Daily).

---

*Music means something here. Treat the station like a hi-fi you respect:
take time to dial in, listen on good speakers, sit with one album before moving to the next.*

— **Z.**
