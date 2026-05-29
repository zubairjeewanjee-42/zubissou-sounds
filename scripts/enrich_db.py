#!/usr/bin/env python3
"""
Zubissou Sounds — Rich DB enrichment (MusicBrainz pass).

Fills the *derivable-from-metadata* knob fields that we can't get locally:
    year (if missing) -> knobs.era
    country           -> region -> knobs.place
    genre             -> genre / subgenres

Source: MusicBrainz Web Service (https://musicbrainz.org/ws/2/). Free, no login.
Hard rule: <= 1 request/second + a descriptive User-Agent (their TOS). The script
sleeps 1.1s between calls and is fully resumable.

What it does NOT do: mood / energy / density / head-body. Those are subjective
"feel" axes with no metadata source (Spotify killed /audio-features). They need a
separate tagging pass — a manual round or an LLM listening/inference pass — which
is the next sub-project.

Reuses region/era logic from build_rich_db.py so everything stays consistent.

RESUMABLE: skips records already enriched; saves every few lookups; --limit caps
calls per run so you can chip away. Re-running continues where it stopped.

USAGE
    python3 scripts/enrich_db.py --source albums              # 115 albums (~4 min)
    python3 scripts/enrich_db.py --source songs
    python3 scripts/enrich_db.py --source catalog --limit 300 # expanded vol, in chunks
    python3 scripts/enrich_db.py --source albums --dry-run    # show what it WOULD fetch
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_rich_db import country_to_region, era_anchor   # reuse the shared logic

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RICH = os.path.join(REPO, "assets", "data", "rich")

MB = "https://musicbrainz.org/ws/2"
UA = "ZubissouSounds/1.0 ( personal dashboard; contact: gooneglobal@gmail.com )"
PAUSE = 1.1          # >= 1s per MusicBrainz TOS
SAVE_EVERY = 10


import re


def clean_q(s):
    """Plain query terms — strip punctuation that breaks MusicBrainz's Lucene
    parser (quotes, ?, :, parens, etc.). A bare multi-term query is the
    canonical MB usage and won't 400."""
    s = re.sub(r"[^\w\s&]", " ", (s or ""), flags=re.U)
    return re.sub(r"\s+", " ", s).strip()


def mb_get(path, params):
    """Return (http_code, data|None). 503 = back off and retry."""
    params = dict(params); params["fmt"] = "json"
    url = f"{MB}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return 200, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 503:                      # MB asks us to back off
                time.sleep(2 + attempt * 2); continue
            return e.code, None
        except urllib.error.URLError:
            time.sleep(2); continue
    return 0, None


def lookup_release_group(artist, title):
    """Return {year, country, genre, subgenres[]} or {} for an album."""
    q = f"{clean_q(artist)} {clean_q(title)}".strip()
    if not q:
        return {}
    code, data = mb_get("release-group", {"query": q, "limit": 3})
    time.sleep(PAUSE)
    rgs = (data or {}).get("release-groups") or []
    if not rgs:
        return {}
    rg = rgs[0]
    out = {}
    frd = rg.get("first-release-date") or ""
    if len(frd) >= 4 and frd[:4].isdigit():
        out["year"] = int(frd[:4])
    tags = sorted(rg.get("tags") or [], key=lambda t: -t.get("count", 0))
    if tags:
        out["genre"] = tags[0]["name"].title()
        out["subgenres"] = [t["name"].title() for t in tags[1:4]]
    # country = the lead artist's area
    ac = (rg.get("artist-credit") or [{}])[0].get("artist") or {}
    area = ac.get("area") or {}
    if area.get("name"):
        out["country"] = area["name"]
    elif ac.get("id"):
        _, art = mb_get(f"artist/{ac['id']}", {"inc": "area"})
        time.sleep(PAUSE)
        if art and (art.get("area") or {}).get("name"):
            out["country"] = art["area"]["name"]
    return out


def lookup_recording(artist, title):
    """Return {year, country, genre} for a track via its recording."""
    q = f"{clean_q(artist)} {clean_q(title)}".strip()
    if not q:
        return {}
    code, data = mb_get("recording", {"query": q, "limit": 3})
    time.sleep(PAUSE)
    recs = (data or {}).get("recordings") or []
    if not recs:
        return {}
    rec = recs[0]
    out = {}
    frd = rec.get("first-release-date") or ""
    if len(frd) >= 4 and frd[:4].isdigit():
        out["year"] = int(frd[:4])
    tags = sorted(rec.get("tags") or [], key=lambda t: -t.get("count", 0))
    if tags:
        out["genre"] = tags[0]["name"].title()
    ac = (rec.get("artist-credit") or [{}])[0].get("artist") or {}
    if (ac.get("area") or {}).get("name"):
        out["country"] = ac["area"]["name"]
    return out


def needs_enrichment(r):
    return not (r.get("year") and r.get("country") and r.get("genre"))


def apply_fields(r, fields):
    changed = False
    if fields.get("year") and not r.get("year"):
        r["year"] = fields["year"]
        label, anchor = era_anchor(fields["year"])
        r["knobs"]["era"] = anchor; r["_era_label"] = label
        changed = True
    if fields.get("country") and not r.get("country"):
        r["country"] = fields["country"]
        region = country_to_region(fields["country"])
        r["region"] = region
        if r["knobs"].get("place") is None:
            r["knobs"]["place"] = region
        changed = True
    if fields.get("genre") and not r.get("genre"):
        r["genre"] = fields["genre"]
        if fields.get("subgenres") and not r.get("subgenres"):
            r["subgenres"] = fields["subgenres"]
        changed = True
    if changed:
        prov = r.setdefault("enrichment", {"status": "stub", "sources": [], "last_enriched": None})
        if "musicbrainz" not in prov["sources"]:
            prov["sources"].append("musicbrainz")
        prov["status"] = "complete" if (r.get("year") and r.get("country") and r.get("genre")) else "partial"
        prov["last_enriched"] = datetime.utcnow().isoformat() + "Z"
    return changed


def run(source, limit, dry):
    path = os.path.join(RICH, f"{source}.json")
    if not os.path.exists(path):
        sys.exit(f"  ! {path} not found — run build_rich_db.py first.")
    recs = json.load(open(path, encoding="utf-8"))
    todo = [r for r in recs if needs_enrichment(r)]
    print(f"  {source}: {len(recs)} records, {len(todo)} need enrichment"
          + (f" (capping at {limit} this run)" if limit else ""))
    if dry:
        for r in todo[:limit or 20]:
            print(f"     would look up: {r.get('artist')} — {r.get('title')}")
        return

    done = 0
    for r in todo:
        if limit and done >= limit:
            print(f"     hit --limit {limit}; re-run to continue."); break
        try:
            if r["type"] == "album":
                fields = lookup_release_group(r.get("artist") or "", r.get("title") or "")
            else:
                fields = lookup_recording(r.get("artist") or "", r.get("title") or "")
        except KeyboardInterrupt:
            print("\n     stopped — progress saved."); break
        except Exception as e:
            print(f"     · error on {r.get('artist')} — {r.get('title')}: {e}"); fields = {}
        if apply_fields(r, fields):
            print(f"     ✓ {r.get('artist')} — {r.get('title')}  "
                  f"[{r.get('year')}, {r.get('region')}, {r.get('genre')}]")
        done += 1
        if done % SAVE_EVERY == 0:
            json.dump(recs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"     … saved ({done} processed)")

    json.dump(recs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    filled = sum(1 for r in recs if not needs_enrichment(r))
    print(f"\n  done. {filled}/{len(recs)} fully enriched. file: assets/data/rich/{source}.json")
    print("  (mood / energy / density / head-body still need a feel-tagging pass.)")


def main():
    ap = argparse.ArgumentParser(description="Enrich the rich DB from MusicBrainz.")
    ap.add_argument("--source", choices=["albums", "songs", "catalog"], required=True)
    ap.add_argument("--limit", type=int, default=0, help="max lookups this run (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.source, args.limit, args.dry_run)


if __name__ == "__main__":
    main()
