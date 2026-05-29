#!/usr/bin/env python3
"""
Zubissou Sounds — Spotify user-as-curator scraper.

Given a Spotify username (e.g. derrickgee), pulls every PUBLIC playlist they've
made plus all the tracks inside them. Turns any Spotify-power user into a curator
source for the dashboard (joins XRAY + Aquarium Drunkard).

Uses /users/{id}/playlists and /playlists/{id}/tracks — NO /search calls, so it
sidesteps the dev-mode search quota entirely. Reuses the OAuth + Spotify class
from build_playlists.py.

OUTPUT (in assets/data/curators/{user_id}/):
    profile.json        the user's basic profile + counts
    playlists.json      list of all their public playlists with metadata
    tracks.json         FLAT list of every track across all their playlists,
                        tagged with source_playlist  (this is what My Fingerprint reads)
    all_tracks.json     symlink-equivalent — same as tracks.json under the name
                        the dashboard already expects for curators

USAGE
    python3 scripts/scrape_spotify_curator.py derrickgee
    python3 scripts/scrape_spotify_curator.py derrickgee --limit 20

Add new curators just by running the same command with a different user id.
"""
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_playlists import Spotify, CoolOff

REPO = os.path.dirname(HERE)
CURATORS = os.path.join(REPO, "assets", "data", "curators")


def save(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def fetch_paged(sp, path, key="items"):
    """Walk a paginated Spotify endpoint, return all items."""
    out = []
    while path:
        d = sp._request("GET", path)
        out += (d.get(key) or [])
        nxt = d.get("next")
        path = nxt.replace("https://api.spotify.com/v1", "") if nxt else None
        time.sleep(0.15)
    return out


def _extract_playlist_id(s):
    """Accept a playlist ID, a /playlist/<id>?... URL, or spotify:playlist:<id>."""
    import re
    m = re.search(r"playlist[/:]([a-zA-Z0-9]+)", s)
    return m.group(1) if m else s.strip()


def fetch_via_embed(playlist_id, debug=False):
    """Public Spotify embed page — no auth, no quota. Returns
    (playlist_meta, tracks_list) or (None, None).
    Each track: {spotify_id?, spotify_uri?, track, artist, duration_ms, cover_url, album?}."""
    import urllib.request, urllib.error, re, json
    url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    # Full browser-shaped UA — Spotify sometimes serves different markup to
    # spartan UAs and that's why this can succeed in one env and not another.
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        if debug: print(f"     [debug] fetch failed: {e}")
        return None, None

    if debug:
        print(f"     [debug] {playlist_id}: html={len(html)} chars, "
              f"has __NEXT_DATA__={'__NEXT_DATA__' in html}, "
              f"has spotify:track:={('spotify:track:' in html)} "
              f"({len(re.findall(r'spotify:track:[a-zA-Z0-9]+', html))} uri matches)")

    # 1) PREFERRED: the embed page embeds a React state JSON with full URIs.
    blob = None
    m = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try: blob = json.loads(m.group(1))
        except Exception: blob = None

    tracks, meta = [], {}
    if blob:
        # Embed schema (current 2026): tracks live at
        #   props.pageProps.state.data.entity.trackList[]
        # with fields title / subtitle (artists comma-joined) / uri / duration.
        # Fall back to the older API-style object if some other shape appears.
        def normalize_track(o):
            if not isinstance(o, dict): return None
            uri = o.get("uri")
            if not (isinstance(uri, str) and uri.startswith("spotify:track:")): return None
            # embed style
            if o.get("title"):
                # subtitle uses non-breaking spaces as artist separator; normalize
                sub = (o.get("subtitle") or "").replace(" ", " ").strip()
                # collapse runs of whitespace and trim commas
                import re as _re
                sub = _re.sub(r"\s+", " ", sub).strip(", ")
                return {
                    "spotify_uri": uri,
                    "spotify_id":  uri.split(":")[-1],
                    "track":       o.get("title"),
                    "artist":      sub,
                    "duration_ms": o.get("duration"),
                    "album": None, "album_id": None, "cover_url": None,
                }
            # api-shape fallback
            if o.get("name"):
                arts = o.get("artists") or []
                return {
                    "spotify_uri": uri,
                    "spotify_id":  uri.split(":")[-1],
                    "track":       o.get("name"),
                    "artist":      ", ".join((a.get("name") or "") for a in arts if isinstance(a, dict)),
                    "duration_ms": o.get("duration_ms"),
                    "album":       (o.get("album") or {}).get("name") if isinstance(o.get("album"), dict) else None,
                    "album_id":    (o.get("album") or {}).get("uri","").split(":")[-1] if isinstance(o.get("album"), dict) else None,
                    "cover_url":   ((o.get("album") or {}).get("images") or [{}])[0].get("url") if isinstance(o.get("album"), dict) else None,
                }
            return None

        def walk(o, out):
            if isinstance(o, dict):
                t = normalize_track(o)
                if t: out.append(t)
                for v in o.values(): walk(v, out)
            elif isinstance(o, list):
                for v in o: walk(v, out)
        walk(blob, tracks)
        # dedup by URI preserving order
        seen, uniq = set(), []
        for t in tracks:
            if t["spotify_uri"] in seen: continue
            seen.add(t["spotify_uri"]); uniq.append(t)
        tracks = uniq
        # playlist meta — embed JSON's entity object has name + cover, more reliable than og: tags
        entity = ((blob.get("props") or {}).get("pageProps") or {}).get("state", {}).get("data", {}).get("entity", {}) or {}
        if entity.get("name"):  meta["name"] = entity["name"]
        if entity.get("title") and not meta.get("name"): meta["name"] = entity["title"]
        if entity.get("subtitle"): meta["author"] = entity["subtitle"]
        ca = ((entity.get("coverArt") or {}).get("sources") or [{}])
        if ca and ca[0].get("url"): meta["image"] = ca[0]["url"]
        # fallback to og:
        if not meta.get("name"):
            m2 = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
            if m2: meta["name"] = m2.group(1)
        if not meta.get("image"):
            m3 = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
            if m3: meta["image"] = m3.group(1)
        m4 = re.search(r'<meta\s+property="og:description"\s+content="([^"]+)"', html)
        if m4: meta["description"] = m4.group(1)

    # 2) Fallback: regex over the rendered HTML for track rows. No URIs, just text.
    if not tracks:
        for tm in re.finditer(
            r'data-encore-id="text"[^>]*>\s*(?P<title>[^<]+)</[^>]+>\s*'
            r'<div[^>]*>\s*<a[^>]*data-encore-id="text"[^>]*>\s*(?P<artist>[^<]+)',
            html):
            tracks.append({"track": tm.group("title").strip(),
                           "artist": tm.group("artist").strip()})
        m2 = re.search(r'<title>([^<]+) - playlist by[^<]+</title>', html)
        if m2: meta["name"] = m2.group(1).strip()

    return meta or None, tracks or None


def main():
    ap = argparse.ArgumentParser(description="Scrape a Spotify user's public playlists into a curator source.")
    ap.add_argument("user_id", help="Spotify user id (e.g. derrickgee) — used as the folder name and source label.")
    ap.add_argument("--playlists", nargs="+", default=None,
                    help="explicit list of playlist URLs/IDs (use if /users/{id}/playlists 403s)")
    ap.add_argument("--limit", type=int, default=0, help="cap playlists this run")
    ap.add_argument("--clone-as", default=None,
                    help="after scraping, create a Spotify playlist in MY library named this and add the first scraped playlist's tracks")
    args = ap.parse_args()

    out_dir = os.path.join(CURATORS, args.user_id)
    sp = Spotify()
    print(f"\n  scraping Spotify curator: {args.user_id}")

    # 1) profile — best-effort. Dev-mode apps often 403 here. We just continue.
    try:
        prof = sp._request("GET", f"/users/{args.user_id}")
        save(os.path.join(out_dir, "profile.json"), prof)
        print(f"     ✓ profile: {prof.get('display_name') or args.user_id} · {prof.get('followers',{}).get('total','?')} followers")
    except Exception as e:
        print(f"     · profile not readable ({e}) — continuing without it.")

    # 2) playlists list — try the user endpoint first, fall back to explicit URLs.
    playlists = []
    if args.playlists:
        print(f"     · fetching {len(args.playlists)} playlist(s) by URL …")
        for u in args.playlists:
            pid = _extract_playlist_id(u)
            try:
                p = sp._request("GET", f"/playlists/{pid}?fields=id,name,description,uri,images,tracks(total)")
                if p: playlists.append(p)
            except Exception as e:
                print(f"     ! {pid}: {e}")
    else:
        print(f"     · listing /users/{args.user_id}/playlists …")
        try:
            playlists = fetch_paged(sp, f"/users/{args.user_id}/playlists?limit=50")
            playlists = [p for p in playlists if p]
            print(f"     ✓ found {len(playlists)} public playlists")
        except Exception as e:
            sys.exit(
                f"     ! /users/{{id}}/playlists also 403d ({e}).\n"
                f"     Fix: open Derrick's profile in Spotify, copy each playlist URL,\n"
                f"     then re-run with the URLs:\n"
                f"       python3 scripts/scrape_spotify_curator.py {args.user_id} \\\n"
                f"         --playlists https://open.spotify.com/playlist/XXXX https://open.spotify.com/playlist/YYYY ...")
    if args.limit:
        playlists = playlists[: args.limit]

    # save the metadata-only list immediately so progress survives a crash
    save(os.path.join(out_dir, "playlists.json"),
         [{"id": p["id"], "name": p["name"], "description": p.get("description"),
           "tracks_total": (p.get("tracks") or {}).get("total"),
           "image": (p.get("images") or [{}])[0].get("url"),
           "uri": p["uri"]} for p in playlists])

    # 3) tracks per playlist + flat aggregate. API first; embed if API 403s.
    flat = []
    per_playlist_tracks = {}
    try:
        for i, pl in enumerate(playlists, 1):
            print(f"     · [{i}/{len(playlists)}] {pl['name'][:60]} …", end="", flush=True)
            tracks_extracted = []
            via = "api"
            try:
                items = fetch_paged(sp,
                    f"/playlists/{pl['id']}/tracks?fields=items(track(id,name,uri,duration_ms,artists(id,name),album(id,name,images,release_date))),next&limit=100")
                for it in items:
                    t = (it or {}).get("track") or {}
                    if not t.get("id"): continue
                    tracks_extracted.append({
                        "spotify_id": t["id"],
                        "spotify_uri": t["uri"],
                        "track": t.get("name"),
                        "artist": ", ".join(a.get("name") or "" for a in (t.get("artists") or [])),
                        "artist_ids": [a.get("id") for a in (t.get("artists") or [])],
                        "album": (t.get("album") or {}).get("name"),
                        "album_id": (t.get("album") or {}).get("id"),
                        "release_date": (t.get("album") or {}).get("release_date"),
                        "duration_ms": t.get("duration_ms"),
                        "cover_url": ((t.get("album") or {}).get("images") or [{}])[0].get("url"),
                    })
            except Exception as e:
                # API blocked — fall back to the public embed page
                via = "embed"
                _, embed_tracks = fetch_via_embed(pl["id"])
                if embed_tracks:
                    tracks_extracted = embed_tracks
                else:
                    print(f"  err: {e}"); continue
            # attach source-playlist info to each
            for t in tracks_extracted:
                t["source_playlist"] = pl["id"]
                t["source_playlist_name"] = pl["name"]
            flat.extend(tracks_extracted)
            per_playlist_tracks[pl["id"]] = tracks_extracted
            print(f"  {len(tracks_extracted)} tracks  [{via}]")
            # save flat partial after every playlist so crashes don't lose work
            save(os.path.join(out_dir, "tracks.json"), flat)
            save(os.path.join(out_dir, "all_tracks.json"), flat)   # matches AD/XRAY naming
    except KeyboardInterrupt:
        print("\n  ⏸  stopped — partial saved.")
    except CoolOff as e:
        print(f"\n  ⏸  Spotify rate-limit (Retry-After ~{e.wait/3600:.1f}h). Partial saved.")

    # 4) Optional: clone the first playlist into the user's library as a real Spotify playlist
    if args.clone_as and playlists:
        first = playlists[0]
        tracks = per_playlist_tracks.get(first["id"], [])
        uris = [t["spotify_uri"] for t in tracks if t.get("spotify_uri")]
        if uris:
            desc = f"Cloned from {first.get('name','playlist')} via Zubissou Sounds."
            try:
                pl = sp._request("POST", f"/users/{sp.me['id']}/playlists",
                                 {"name": args.clone_as, "description": desc, "public": False})
                # add 100 at a time
                for j in range(0, len(uris), 100):
                    sp._request("POST", f"/playlists/{pl['id']}/tracks",
                                {"uris": uris[j:j+100]})
                print(f"\n  ✓ cloned “{first.get('name')}” → “{args.clone_as}” in your Spotify library ({len(uris)} tracks)")
            except Exception as e:
                print(f"\n  ! clone failed: {e}")
        else:
            print(f"\n  ! no track URIs available to clone (embed fallback may have failed for URIs)")

    print(f"\n  ── summary ──")
    print(f"  curator:  {args.user_id}")
    print(f"  playlists: {len(playlists)}")
    print(f"  tracks (flat): {len(flat)}")
    print(f"  files in {os.path.relpath(out_dir, REPO)}/")


if __name__ == "__main__":
    main()
