#!/usr/bin/env python3
"""
Create Spotify playlists from the Aquarium Drunkard playlist defs
(`assets/data/curators/aquariumdrunkard/playlists/*.json` produced by
process_ad_data.py).

Two kinds of playlists:

  ALBUM kind — by_tag, by_decade, by_type, by_mixtape (with album_ids)
      Each def already carries `spotify_album_ids`. We just expand each album
      to its tracks and add them. NO Spotify search needed → safe to run even
      while the search rate-limit is cooling off.

  MIXTAPE kind — by_mixtape (with `tracks` text only)
      Each def carries a parsed tracklist [{artist, track}]. We resolve each
      via Spotify search using the matcher logic from build_playlists.py.
      Needs the search rate-limit to be cleared.

Reuses the Spotify auth + helpers from build_playlists.py — same one-time
PKCE login via 127.0.0.1:8080.

USAGE
    # see what would be created (no API calls)
    python3 scripts/build_ad_playlists.py --kind albums --dry-run

    # create just the by-tag playlists (no search needed — safe today)
    python3 scripts/build_ad_playlists.py --kind albums --filter by-tag

    # do everything (mixtapes too, needs search rate-limit cleared)
    python3 scripts/build_ad_playlists.py --kind all

Flags:
    --kind albums | mixtapes | all       (default: albums — safe today)
    --filter SUBSTR    only playlists whose slug contains SUBSTR
    --limit N          cap how many playlists this run
    --dry-run          print plan, create nothing
    --prefix STR       prefix every Spotify playlist name (default "AD · ")

Idempotent: a playlist with the exact same name in your library is updated
(tracks replaced) instead of duplicated.
"""

import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_playlists import (Spotify, CoolOff, best_match, primary_artist,
                             clean_title_for_query, track_key)

REPO = os.path.dirname(HERE)
PL_DIR    = os.path.join(REPO, "assets", "data", "curators", "aquariumdrunkard", "playlists")
PL_INDEX  = os.path.join(PL_DIR, "index.json")
MATCHED_FILE = os.path.join(REPO, "assets", "data", "xray", "matched.json")  # shared cache


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, ValueError): return d
def save(p, d):
    tmp = p + ".tmp"; json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def load_playlists():
    if not os.path.isdir(PL_DIR):
        sys.exit(f"  ! no playlist defs found in {PL_DIR} — run process_ad_data.py first")
    files = sorted(f for f in os.listdir(PL_DIR) if f.endswith(".json") and f != "index.json")
    return [load(os.path.join(PL_DIR, f), {}) for f in files]


def pick_kind(pl, kind):
    k = pl.get("kind")
    if kind == "all": return True
    if kind == "albums":  return k in ("by_tag", "by_decade", "by_type") or (k == "by_mixtape" and pl.get("spotify_album_ids"))
    if kind == "mixtapes": return k == "by_mixtape" and pl.get("tracks")
    return False


def expand_albums_to_uris(sp, album_ids):
    """For each album id, fetch its tracks and gather URIs. No search calls."""
    uris = []
    for aid in album_ids:
        try:
            data = sp._request("GET", f"/albums/{aid}/tracks?limit=50")
        except Exception as e:
            print(f"     · album {aid} fetch failed: {e}"); continue
        for t in (data.get("items") or []):
            if t.get("uri"): uris.append(t["uri"])
        time.sleep(0.08)   # gentle pacing
    return uris


def resolve_text_tracks(sp, tracks, matched, matched_path):
    """Search each text track via the matcher. Updates and flushes the shared
    matched cache every 20 hits so a crash never wipes progress."""
    import re as _re
    uris, miss, n = [], 0, 0
    for t in tracks:
        key = track_key(t["artist"], t["track"])
        cached = matched.get(key)
        if cached and cached.get("uri"):
            uris.append(cached["uri"]); continue
        if cached:           # known miss
            miss += 1; continue
        items = sp.search_track(t["artist"], t["track"])
        uri, via, cand = best_match(t["artist"], t["track"], None, items)
        if uri:
            uris.append(uri)
            matched[key] = {"uri": uri, "via": via,
                            "query_artist": t["artist"], "query_track": t["track"],
                            "matched_name": cand.get("name"),
                            "matched_artist": ", ".join(a["name"] for a in cand.get("artists", [])),
                            "matched_album": (cand.get("album") or {}).get("name")}
        else:
            matched[key] = {"uri": None, "reason": via,
                            "artist": t["artist"], "track": t["track"]}
            miss += 1
        n += 1
        if n % 20 == 0: save(matched_path, matched)   # flush mid-playlist
        time.sleep(0.25)        # gentler pacing — fewer 429s
    save(matched_path, matched)
    return uris, miss


def _clean_text(s):
    """Strip control chars + collapse whitespace — Spotify 400s on weird descriptions."""
    import re as _re, unicodedata as _ud
    s = _ud.normalize("NFKC", s or "")
    s = "".join(c for c in s if c == "\n" or _ud.category(c)[0] != "C")
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def upsert_playlist(sp, name, description, uris):
    name = _clean_text(name)[:100]
    description = _clean_text(description)[:300]
    existing = sp.find_playlist_by_name(name)
    if existing:
        sp.set_playlist_tracks(existing["id"], uris)
        try: sp.update_description(existing["id"], description)
        except Exception: pass   # description update is best-effort
        return existing["id"], "updated"
    pl = sp.create_playlist(name, description)
    sp.set_playlist_tracks(pl["id"], uris)
    return pl["id"], "created"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["albums", "mixtapes", "all"], default="albums")
    ap.add_argument("--filter", default=None, help="only playlists whose slug contains this substring")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--prefix", default="AD · ", help="prefix for the Spotify playlist name")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip playlists already in your library (faster resume)")
    args = ap.parse_args()

    defs = load_playlists()
    picked = [p for p in defs if pick_kind(p, args.kind) and (not args.filter or args.filter in (p.get("slug") or ""))]
    if not picked:
        sys.exit("  ! nothing matched the kind/filter — try --filter '' or a different --kind")

    print(f"\n  AD → Spotify playlists")
    print(f"  candidates: {len(picked)} (kind={args.kind}" + (f", filter={args.filter}" if args.filter else "") + ")")
    if args.limit: picked = picked[:args.limit]
    for p in picked:
        print(f"     · [{p.get('kind','?'):11}] {p.get('name','?'):46}  ({len(p.get('spotify_album_ids') or p.get('tracks') or [])} items)")
    if args.dry_run:
        print("  [dry-run] no playlists created.")
        return

    sp = Spotify()
    print(f"  logged in as {sp.me.get('display_name') or sp.me.get('id')}\n")
    matched = load(MATCHED_FILE, {}) if args.kind in ("mixtapes", "all") else {}

    try:
        for p in picked:
            name = (args.prefix or "") + (p.get("name") or "AD playlist")
            desc = (p.get("description") or "Aquarium Drunkard curation.").strip() + " · auto-built by Zubissou Sounds."
            if args.skip_existing:
                try:
                    if sp.find_playlist_by_name(name):
                        print(f"     · already exists, skipping: {name}"); continue
                except Exception: pass
            try:
                if p.get("spotify_album_ids"):
                    uris = expand_albums_to_uris(sp, p["spotify_album_ids"])
                    kind_tag = "album-pl"
                elif p.get("tracks"):
                    uris, missed = resolve_text_tracks(sp, p["tracks"], matched, MATCHED_FILE)
                    kind_tag = f"mixtape ({missed} missed)"
                else:
                    print(f"     · {name}: no items, skipping"); continue
                if not uris:
                    print(f"     · {name}: 0 uris resolved, skipping"); continue
                pid, status = upsert_playlist(sp, name, desc, uris)
                print(f"     ✓ {status}  [{kind_tag}]  “{name}” · {len(uris)} tracks")
            except CoolOff:
                raise   # propagate up
            except Exception as e:
                print(f"     ! {name}: {type(e).__name__}: {str(e)[:160]} — skipping, continuing")
                save(MATCHED_FILE, matched)
                continue
    except CoolOff as e:
        save(MATCHED_FILE, matched)
        print(f"\n  ⏸  Spotify is rate-limiting (Retry-After ~{e.wait/3600:.1f}h). Resume later — cache saved.")
    except KeyboardInterrupt:
        save(MATCHED_FILE, matched)
        print("\n  ⏸  stopped — progress saved.")


if __name__ == "__main__":
    main()
