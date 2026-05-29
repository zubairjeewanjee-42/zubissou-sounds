#!/usr/bin/env python3
"""
Turn the raw Aquarium Drunkard scrape into two structured assets:

  1. assets/data/rich/ad_picks.json
     Knob-ready album records (same schema as rich/albums.json), one per AD
     review/feature that has a Spotify album URL. These join the canon's
     selection pool so the dashboard's knobs steer AD picks alongside your
     top-100.

  2. assets/data/curators/aquariumdrunkard/playlists/
     index.json + one file per defined playlist. Sliced four ways so you
     never end up with one massive 600-album dump:

         by_tag      one playlist per popular tag (Afrobeat, post-punk,
                     ambient, jazz…) with at least N albums
         by_decade   one per decade we can date (60s, 70s, 80s, 90s, 2000s…)
         by_type     review-shelf · interview-subjects · lagniappe-covers
         by_mixtape  each AD mixtape post as its own playlist (the parsed
                     tracklist; track URIs to be filled by the matcher later)

Run AFTER the scrape finishes:
    python3 scripts/process_ad_data.py

Re-run any time — it rebuilds from posts.json (your scrape source of truth).
Stdlib only.
"""

import json, os, re
from collections import Counter, defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
AD_DIR = os.path.join(REPO, "assets", "data", "curators", "aquariumdrunkard")
POSTS_FILE    = os.path.join(AD_DIR, "posts.json")
CAROUSEL_FILE = os.path.join(AD_DIR, "carousel.json")
PICKS_FILE    = os.path.join(REPO, "assets", "data", "rich", "ad_picks.json")
TRACKS_FILE   = os.path.join(AD_DIR, "all_tracks.json")
PL_DIR        = os.path.join(AD_DIR, "playlists")
PL_INDEX      = os.path.join(PL_DIR, "index.json")

MIN_TAG_PLAYLIST = 4         # only emit a tag playlist if at least N albums share it
YEAR_IN_TEXT_RE  = re.compile(r"\b(19[3-9]\d|20[0-2]\d)\b")

# tracklist parsers — try strict numbered, then loose "Artist – Track" lines
NUMBERED_RE = re.compile(r"^\s*\d{1,3}[.\)]\s+([^\n]+?)\s+[–—\-]\s+([^\n]+)\s*$", re.M)
BULLET_RE   = re.compile(r"^\s*[•·\-\*]\s+([^\n]+?)\s+[–—\-]\s+([^\n]+)\s*$", re.M)
LOOSE_RE    = re.compile(r"^\s*([^\n]+?)\s+[–—]\s+([^\n]+?)\s*$", re.M)   # en/em-dash only, less ambiguous

def _valid_pair(artist, track):
    a, t = artist.strip(), track.strip()
    if not (2 <= len(a) <= 80 and 2 <= len(t) <= 140): return False
    if a.count(".") > 2 or t.count(".") > 2: return False         # avoid sentences
    if a.count(",") > 3 or t.count(",") > 3: return False
    if not re.search(r"[A-Za-z]", a) or not re.search(r"[A-Za-z]", t): return False
    return True

def parse_mixtape_tracklist(body):
    """Return [{artist, track, raw}] from a mixtape body. Tries strict numbered
    first, then bullet, then loose 'Artist – Track' lines with validation."""
    for label, pat in (("numbered", NUMBERED_RE), ("bullet", BULLET_RE), ("loose", LOOSE_RE)):
        tracks = []
        for m in pat.finditer(body):
            a, t = m.group(1).strip(), m.group(2).strip()
            if not _valid_pair(a, t): continue
            tracks.append({"artist": a, "track": t, "raw": f"{a} – {t}"})
        # require a minimum so we don't false-positive on a few dashed sentences
        if len(tracks) >= 5:
            # de-dupe identical lines
            seen, out = set(), []
            for tr in tracks:
                k = (tr["artist"].lower(), tr["track"].lower())
                if k in seen: continue
                seen.add(k); out.append(tr)
            return out
    return []


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, ValueError): return d

def save(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------- #
def guess_year(post):
    """Hunt for a release year — title first, then first paragraph of body."""
    for src in (post.get("album") or "", post.get("title") or "", (post.get("body_text") or "")[:600]):
        m = YEAR_IN_TEXT_RE.search(src)
        if m: return int(m.group(1))
    return None


def empty_knobs():
    return {"mood": None, "energy": None, "density": None, "headbody": None,
            "era": None, "place": None, "familiarity": None}


def to_rich_record(post):
    """Convert one AD review post into a knob-ready album record."""
    spot_albums = post["links"].get("spotify_album") or []
    if not spot_albums: return None
    sid = spot_albums[0].split("/")[-1].split("?")[0]
    year = guess_year(post)
    tag_names = [t["name"] for t in (post.get("tags") or [])]
    return {
        "id": sid,
        "type": "album",
        "source": "aquariumdrunkard",
        "artist": post.get("artist"),
        "title": post.get("album") or post.get("title"),
        "album": post.get("album") or post.get("title"),
        "year": year,
        "release_date": None,
        "genre": tag_names[0] if tag_names else None,
        "subgenres": tag_names[1:6],
        "country": None, "region": None,
        "instrumentation": [],
        "tags": tag_names,
        "knobs": {**empty_knobs(),
                  "era": year if year else None},   # era anchor handled at consumer side
        "bpm": None,
        "spotify_id": sid,
        "spotify_url": spot_albums[0],
        "cover_url": post.get("cover_url"),
        "standout_tracks": None,
        "why_i_love_it": None,
        "ad_blurb": (post.get("body_text") or "")[:600].strip(),
        "ad_url": post["url"],
        "ad_author": post.get("author"),
        "ad_date": post.get("date"),
        "notes": None,
        "enrichment": {"status": "partial", "sources": ["aquariumdrunkard"],
                       "last_enriched": datetime.utcnow().isoformat() + "Z"},
    }


# --------------------------------------------------------------------------- #
def carousel_to_rich(c):
    sid = c["spotify_id"]
    return {
        "id": sid, "type": "album", "source": "aquariumdrunkard-carousel",
        "artist": c.get("artist"), "title": c.get("album"), "album": c.get("album"),
        "year": None, "release_date": None,
        "genre": None, "subgenres": [], "country": None, "region": None,
        "instrumentation": [], "tags": [],
        "knobs": {**empty_knobs()},
        "bpm": None,
        "spotify_id": sid, "spotify_url": c.get("spotify_album"),
        "cover_url": c.get("cover_url"),
        "standout_tracks": None, "why_i_love_it": None,
        "ad_blurb": (c.get("blurb") or "").strip()[:600],
        "ad_url": None, "ad_author": None, "ad_date": None,
        "notes": None,
        "enrichment": {"status": "partial", "sources": ["aquariumdrunkard-carousel"],
                       "last_enriched": datetime.utcnow().isoformat() + "Z"},
    }


def build_picks(posts, carousel):
    picks = []
    for p in posts.values():
        r = to_rich_record(p)
        if r: picks.append(r)
    for c in carousel:
        picks.append(carousel_to_rich(c))
    # dedup on spotify_id
    seen, uniq = set(), []
    for r in picks:
        if not r.get("spotify_id") or r["spotify_id"] in seen: continue
        seen.add(r["spotify_id"]); uniq.append(r)
    return uniq


def build_playlists(posts, picks):
    """Slice the corpus into coherent themed playlists."""
    out = {}

    # 0) "Currently Spinning" — the homepage carousel snapshot. Small but ALWAYS
    #    has Spotify album IDs, so it's the one playlist we can create on
    #    Spotify with zero search/matching today.
    carousel_picks = [p for p in picks if p.get("source") == "aquariumdrunkard-carousel"]
    if carousel_picks:
        out["currently-spinning"] = {
            "slug": "currently-spinning", "kind": "by_type",
            "name": "AD · Currently Spinning",
            "description": f"AD's current homepage carousel — {len(carousel_picks)} albums on rotation.",
            "spotify_album_ids": [c["spotify_id"] for c in carousel_picks],
            "sources": [c.get("ad_url") or "" for c in carousel_picks],
        }

    # 1) by_tag — one playlist per tag with >= MIN_TAG_PLAYLIST picks
    tag_buckets = defaultdict(list)
    for p in picks:
        for t in p["tags"]: tag_buckets[t].append(p)
    for tag, items in tag_buckets.items():
        if len(items) < MIN_TAG_PLAYLIST: continue
        slug = "by-tag-" + re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")
        out[slug] = {
            "slug": slug, "kind": "by_tag",
            "name": f"AD · {tag}",
            "description": f"{len(items)} albums tagged “{tag}” across Aquarium Drunkard reviews.",
            "spotify_album_ids": [x["spotify_id"] for x in items],
            "sources": [x["ad_url"] for x in items],
        }

    # 2) by_decade
    dec_buckets = defaultdict(list)
    for p in picks:
        if p.get("year"):
            dec_buckets[(p["year"] // 10) * 10].append(p)
    for d, items in dec_buckets.items():
        if len(items) < 3: continue
        slug = f"by-decade-{d}s"
        out[slug] = {
            "slug": slug, "kind": "by_decade",
            "name": f"AD · the {d}s",
            "description": f"{len(items)} AD picks from {d}–{d+9}.",
            "spotify_album_ids": [x["spotify_id"] for x in items],
            "sources": [x["ad_url"] for x in items],
        }

    # 3) by_type — review shelf, interview subjects (their albums if reviewed), lagniappe covers
    reviews = [p for p in posts.values() if p.get("post_type") == "review"]
    if reviews:
        out["by-type-review-shelf"] = {
            "slug": "by-type-review-shelf", "kind": "by_type",
            "name": "AD · Review Shelf",
            "description": f"Every AD album review we scraped — {len(reviews)} picks.",
            "spotify_album_ids": [(p["links"]["spotify_album"][0]).split("/")[-1].split("?")[0] for p in reviews if p["links"].get("spotify_album")],
            "sources": [p["url"] for p in reviews],
        }
    lagn = [p for p in posts.values() if p.get("post_type") == "lagniappe"]
    if lagn:
        out["by-type-lagniappe-sessions"] = {
            "slug": "by-type-lagniappe-sessions", "kind": "by_type",
            "name": "AD · Lagniappe Sessions",
            "description": f"AD's Lagniappe Sessions index — {len(lagn)} cover-song sessions.",
            "session_post_urls": [p["url"] for p in lagn],
            "sources": [p["url"] for p in lagn],
        }

    # 4) by_mixtape — each AD mixtape becomes a playlist of TRACKS.
    #    Try numbered → unnumbered. Validate so we don't false-positive on prose.
    for p in posts.values():
        if "mixtape" not in ((p.get("sources") or []) + [p.get("source")]): continue
        body = p.get("body_text") or ""
        tracks = parse_mixtape_tracklist(body)
        if not tracks: continue
        slug = "by-mixtape-" + p["slug"]
        out[slug] = {
            "slug": slug, "kind": "by_mixtape",
            "name": f"AD Mixtape · {p['title']}",
            "description": (p.get("description") or (p.get("body_text") or "")[:240]).strip(),
            "needs_matching": True,
            "track_count": len(tracks),
            "tracks": tracks,
            "sources": [p["url"]],
        }

    return out


# --------------------------------------------------------------------------- #
def main():
    posts = load(POSTS_FILE, {})
    carousel = load(CAROUSEL_FILE, [])
    if not posts and not carousel:
        print(f"  ! no scrape data yet — run scrape_aquariumdrunkard.py first")
        return
    print(f"  posts loaded: {len(posts)} · carousel cards: {len(carousel)}")

    picks = build_picks(posts, carousel)
    print(f"  knob-ready album picks: {len(picks)} (with Spotify ID)")
    save(PICKS_FILE, picks)

    playlists = build_playlists(posts, picks)

    # Flat tracks file — every parsed AD mixtape track tagged with its source mixtape
    # so the dashboard's My Fingerprint chart can merge AD + XRAY in one pass.
    all_tracks = []
    for slug, pl in playlists.items():
        if pl.get("kind") != "by_mixtape": continue
        for t in pl.get("tracks", []):
            all_tracks.append({
                "artist": t["artist"], "track": t["track"],
                "mixtape": slug, "title": pl["name"],
            })
    save(TRACKS_FILE, all_tracks)
    print(f"  ad tracks (flat) → {len(all_tracks)} across {sum(1 for p in playlists.values() if p.get('kind')=='by_mixtape')} mixtapes")

    save(PL_INDEX, {
        "built_at": datetime.utcnow().isoformat() + "Z",
        "playlist_count": len(playlists),
        "by_kind": dict(Counter(p["kind"] for p in playlists.values())),
        "slugs": sorted(playlists.keys()),
    })
    os.makedirs(PL_DIR, exist_ok=True)
    for slug, pl in playlists.items():
        save(os.path.join(PL_DIR, slug + ".json"), pl)

    # nice summary
    print(f"\n  ── summary ──")
    print(f"  picks → assets/data/rich/ad_picks.json  ({len(picks)} albums)")
    print(f"  playlists → assets/data/curators/aquariumdrunkard/playlists/  ({len(playlists)} files)")
    print(f"  by kind: {dict(Counter(p['kind'] for p in playlists.values()))}")
    top_tags = Counter()
    for p in picks:
        for t in p["tags"]: top_tags[t] += 1
    print(f"\n  top tags across picks:")
    for t, n in top_tags.most_common(15):
        print(f"     {n:3} · {t}")


if __name__ == "__main__":
    main()
