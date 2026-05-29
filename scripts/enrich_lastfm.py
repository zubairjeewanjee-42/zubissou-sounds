#!/usr/bin/env python3
"""
Zubissou Sounds — Last.fm enrichment.

For every track in the rich DB, hit Last.fm's track.getInfo to pull:
    - global playcount + listeners  (drives the EXPLORE knob at scale)
    - duration (ms)                  (used for playlist length budgeting)
    - top user tags                  (extra genre signal for the intent matcher)
    - album it appears on, if known
    - the "wiki summary" first line  (short blurb for the Codex)

Free. No paid tier. Last.fm rate limit is generous (~5 req/sec); we sleep
0.25s between calls anyway. Resumable — records with `lastfm.fetched_at`
already set are skipped.

SETUP (one-time, free):
    1. Go to https://www.last.fm/api/account/create
    2. Pick any app name (e.g. "Zubissou Sounds personal").
    3. Copy the "API key" (32-char hex).
    4. export LASTFM_API_KEY='your_key_here'

USAGE:
    python3 scripts/enrich_lastfm.py --source catalog --limit 100   # smoke-test
    python3 scripts/enrich_lastfm.py --source catalog               # full run
    python3 scripts/enrich_lastfm.py --source albums                # canon
    python3 scripts/enrich_lastfm.py --source all                   # everything

Stdlib only. Resumable + incremental save.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RICH = os.path.join(REPO, "assets", "data", "rich")

API = "https://ws.audioscrobbler.com/2.0/"
UA  = "ZubissouSounds/1.0 (+personal listening dashboard)"
PAUSE = 0.25
SAVE_EVERY = 25


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, ValueError): return d
def save(p, d):
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def lfm_get(method, params, key):
    q = dict(params); q.update({"method": method, "api_key": key, "format": "json"})
    url = f"{API}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(8); return None
        return None
    except urllib.error.URLError:
        time.sleep(2); return None


def needs_lastfm(rec):
    return not (rec.get("lastfm") or {}).get("fetched_at")


def get_artist_track(rec):
    """Each source has slightly different shape. Normalize."""
    return ((rec.get("artist") or "").strip(),
            (rec.get("track") or rec.get("title") or rec.get("album") or "").strip())


def enrich_one(rec, key):
    artist, track = get_artist_track(rec)
    if not artist or not track: return False
    data = lfm_get("track.getInfo", {"artist": artist, "track": track,
                                      "autocorrect": "1"}, key)
    if not data or "track" not in data:
        rec.setdefault("lastfm", {})["fetched_at"] = datetime.utcnow().isoformat()+"Z"
        rec["lastfm"]["found"] = False
        return True   # attempted, mark so we don't keep re-trying
    t = data["track"]
    lf = {"fetched_at": datetime.utcnow().isoformat()+"Z", "found": True}
    try: lf["playcount"] = int(t.get("playcount") or 0)
    except (TypeError, ValueError): pass
    try: lf["listeners"] = int(t.get("listeners") or 0)
    except (TypeError, ValueError): pass
    try: lf["duration_ms"] = int(t.get("duration") or 0)
    except (TypeError, ValueError): pass
    if (t.get("album") or {}).get("title"):
        lf["album_title"] = t["album"]["title"]
        if t["album"].get("mbid"): lf["album_mbid"] = t["album"]["mbid"]
    tags = ((t.get("toptags") or {}).get("tag") or [])
    if tags: lf["tags"] = [x["name"] for x in tags[:6]]
    wiki = (t.get("wiki") or {}).get("summary") or ""
    if wiki:
        lf["summary"] = wiki.split("<a href=")[0].strip()[:600]
    rec["lastfm"] = lf
    # also fold useful signals into the rich schema so the dashboard can read directly
    if lf.get("duration_ms") and not rec.get("duration_ms"):
        rec["duration_ms"] = lf["duration_ms"]
    if lf.get("listeners"):
        # crude "familiarity" boost: tracks with millions of listeners are "canon-world"
        rec.setdefault("knobs", {}).setdefault("global_listeners", lf["listeners"])
    if lf.get("tags") and not rec.get("tags"):
        rec["tags"] = lf["tags"]
    prov = rec.setdefault("enrichment", {"status": "stub", "sources": [], "last_enriched": None})
    if "lastfm" not in (prov.get("sources") or []):
        prov.setdefault("sources", []).append("lastfm")
    prov["last_enriched"] = lf["fetched_at"]
    return True


def run(path, key, limit):
    if not os.path.exists(path):
        print(f"  ! {path} not found, skip"); return
    recs = load(path, [])
    todo = [r for r in recs if needs_lastfm(r)]
    print(f"\n  {os.path.basename(path)}  ·  need lookup: {len(todo)}/{len(recs)}")
    if not todo: return
    done = 0; hits = 0
    for r in todo:
        if limit and done >= limit: break
        try:
            if enrich_one(r, key) and (r.get("lastfm") or {}).get("found"):
                hits += 1
        except KeyboardInterrupt:
            print("\n  ⏸  stopped — saving."); break
        except Exception as e:
            print(f"     · error: {e}")
        done += 1
        if done % SAVE_EVERY == 0:
            save(path, recs)
            print(f"     {done} attempted · {hits} hits  (saved)")
        time.sleep(PAUSE)
    save(path, recs)
    print(f"     → done: {done} attempted · {hits} hits this run.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["albums", "songs", "catalog", "ad_picks", "all"], required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    key = os.environ.get("LASTFM_API_KEY")
    if not key:
        # fallback: read from scripts/.lastfm_key.txt (one line, gitignored)
        kfile = os.path.join(HERE, ".lastfm_key.txt")
        if os.path.exists(kfile):
            key = open(kfile).read().strip()
    if not key:
        sys.exit("  ! no API key. Set LASTFM_API_KEY or save it to scripts/.lastfm_key.txt")
    sources = ["albums", "songs", "catalog", "ad_picks"] if args.source == "all" else [args.source]
    for s in sources:
        run(os.path.join(RICH, f"{s}.json"), key, args.limit)
    print("\n  rich files updated with last.fm fields under `lastfm` and rolled-up fields where appropriate.")


if __name__ == "__main__":
    main()
