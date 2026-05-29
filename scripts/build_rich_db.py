#!/usr/bin/env python3
"""
Zubissou Sounds — Rich Data DB builder.

Turns the three source lists into ONE unified rich-record schema that every
knob / preset / search feature can read:

    source                         -> output
    top-100-albums.json            -> rich/albums.json
    top-100-songs.json             -> rich/songs.json
    birth-year-1984.json (albums)  -> folded into rich/albums.json (source=birthyear)
    xray/index.json  (tracks)      -> rich/catalog.json   (the expanded volume)

Each rich record carries the seven knob coordinates plus the descriptive fields
the dashboard needs. What can be derived locally is filled now:
    - year                  (from source)
    - knobs.era             (snapped to the nearest seminal-era anchor)
    - region / knobs.place  (mapped from country)
    - genre, subgenres
    - knobs.familiarity     (= canon rank; lower = more familiar; null for catalog)
The rest (mood / energy / density / headbody / bpm / instrumentation) start as
null and get filled by the later enrichment pass (Spotify artist-genres,
MusicBrainz, Discogs, or a manual/LLM tagging pass).

IDEMPOTENT: re-running merges. Any knob value or field you've already populated
is preserved; only missing/derivable fields are (re)filled. So you can hand-tag
moods and never lose them on the next build.

Stdlib only. Run:
    python3 scripts/build_rich_db.py
"""

import json
import os
import re
import unicodedata
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "assets", "data")
RICH = os.path.join(DATA, "rich")

# --------------------------------------------------------------------------- #
# Seminal-era anchors — the ERA knob snaps to these. Reaches before 1950 and
# stops dead on landmark years in music history.
# --------------------------------------------------------------------------- #
ERA_ANCHORS = [
    ("pre-1950", 1948), ("1955", 1955), ("1959", 1959), ("1965", 1965),
    ("1967", 1967), ("1969", 1969), ("1971", 1971), ("1973", 1973),
    ("1977", 1977), ("1980", 1980), ("1985", 1985), ("1991", 1991),
    ("1995", 1995), ("2000", 2000), ("2007", 2007), ("2013", 2013),
    ("2020", 2020), ("today", datetime.now().year),
]


def era_anchor(year):
    """Return (label, anchor_year) of the nearest seminal era anchor."""
    if not year:
        return (None, None)
    best = min(ERA_ANCHORS, key=lambda a: abs(a[1] - int(year)))
    return best


# --------------------------------------------------------------------------- #
# Country -> region (regions match the PLACES list in the dashboard)
# --------------------------------------------------------------------------- #
REGION_RULES = [
    (("usa", "united states", "america"), "USA"),
    (("canada",), "USA"),
    (("uk", "england", "britain", "scotland", "wales", "ireland"), "UK"),
    (("france",), "France"),
    (("germany",), "Germany"),
    (("italy",), "Italy"),
    (("sweden", "norway", "denmark", "finland", "iceland", "scandinav"), "Scandinavia"),
    (("brazil",), "Brazil"),
    (("argentina", "uruguay"), "Argentina"),
    (("cuba",), "Cuba"),
    (("mexico",), "Mexico"),
    (("jamaica",), "Jamaica"),
    (("mali", "sahel"), "Mali / Sahel"),
    (("nigeria", "ghana", "senegal", "west africa"), "West Africa"),
    (("south africa",), "South Africa"),
    (("ethiopia",), "Ethiopia"),
    (("japan",), "Japan"),
    (("korea",), "Korea"),
    (("india", "pakistan", "bangladesh", "south asia"), "India / South Asia"),
    (("thailand", "indonesia", "vietnam", "cambodia", "philippines", "se asia"), "SE Asia"),
    (("turkey", "egypt", "morocco", "lebanon", "iran", "mena"), "MENA / Turkey"),
    (("russia", "poland", "czech", "hungary", "romania", "ukraine", "eastern europe"), "Eastern Europe"),
    (("australia", "new zealand", "oceania"), "Oceania"),
]


def country_to_region(country):
    if not country:
        return None
    first = country.split("/")[0].strip().lower()   # 'USA/Germany' -> 'usa'
    for needles, region in REGION_RULES:
        if any(n in first for n in needles):
            return region
    return None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def norm(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower())
                if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def load_list(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []
    if isinstance(d, list):
        return d
    for v in d.values():
        if isinstance(v, list):
            return v
    return []


def split_subgenres(s):
    return [x.strip() for x in re.split(r"[;,]", s or "") if x.strip()]


def empty_knobs():
    return {
        "mood": None,         # melancholy 0 .. euphoric 100
        "energy": None,       # ambient 0 .. driving 100
        "density": None,      # sparse 0 .. wall-of-sound 100
        "headbody": None,     # cerebral 0 .. groove 100
        "era": None,          # nearest anchor year (derived from year)
        "place": None,        # region string (derived from country)
        "familiarity": None,  # canon rank; lower = more familiar; null for catalog
    }


def base_record(rec_id, rtype, source):
    return {
        "id": rec_id, "type": rtype, "source": source,
        "artist": None, "title": None, "album": None,
        "year": None, "release_date": None,
        "genre": None, "subgenres": [], "country": None, "region": None,
        "instrumentation": [], "tags": [],
        "knobs": empty_knobs(),
        "bpm": None,
        "spotify_id": None, "spotify_url": None, "cover_url": None,
        "standout_tracks": None, "why_i_love_it": None, "notes": None,
        "enrichment": {"status": "stub", "sources": [], "last_enriched": None},
    }


def fill_derivable(r):
    """(Re)derive the fields we can compute locally without touching the record's
    manually-set / enriched knob values."""
    if r.get("year"):
        label, anchor = era_anchor(r["year"])
        r["knobs"]["era"] = anchor
        r["_era_label"] = label
    if r.get("country"):
        region = country_to_region(r["country"])
        r["region"] = region
        if r["knobs"].get("place") is None:
            r["knobs"]["place"] = region
    return r


def merge(existing, fresh):
    """Preserve any non-null/ non-empty value the existing record already has,
    so hand-tagged knobs and enrichment survive a rebuild."""
    if not existing:
        return fresh
    out = dict(fresh)
    for k, v in existing.items():
        if k == "knobs":
            continue
        if v not in (None, [], "", {}):
            out[k] = v
    # knobs: keep existing non-null knob values
    ek = existing.get("knobs", {})
    for k, v in ek.items():
        if v is not None:
            out["knobs"][k] = v
    # enrichment provenance: keep the richer one
    if existing.get("enrichment", {}).get("status") in ("partial", "complete"):
        out["enrichment"] = existing["enrichment"]
    return out


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def key_of(rtype, artist, title):
    return f"{rtype}:{norm(artist)}|{norm(title)}"


def build_album(src, source="canon"):
    title = src.get("album") or ""
    r = base_record(src.get("spotify_id") or key_of("album", src.get("artist"), title),
                    "album", source)
    r.update({
        "artist": src.get("artist"), "title": title, "album": title,
        "year": src.get("year") or None,
        "release_date": src.get("release_date") or None,
        "genre": src.get("genre") or None,
        "subgenres": split_subgenres(src.get("subgenre")),
        "country": src.get("country") or None,
        "spotify_id": src.get("spotify_id") or None,
        "spotify_url": src.get("spotify_url") or None,
        "cover_url": src.get("cover_url") or None,
        "standout_tracks": src.get("standout_tracks") or None,
        "why_i_love_it": src.get("why_i_love_it") or None,
        "notes": src.get("notes") or None,
    })
    if src.get("rank"):
        r["knobs"]["familiarity"] = src["rank"]
    if src.get("mood"):
        r["tags"].append(src["mood"])
    return fill_derivable(r)


def build_song(src):
    title = src.get("track") or ""
    r = base_record(src.get("spotify_id") or key_of("song", src.get("artist"), title),
                    "song", "canon")
    r.update({
        "artist": src.get("artist"), "title": title, "album": src.get("album") or None,
        "year": src.get("year") or None,
        "genre": src.get("genre") or None,
        "spotify_url": src.get("spotify_url") or None,
        "why_i_love_it": src.get("why_i_love_it") or None,
        "notes": src.get("notes") or None,
    })
    if src.get("rank"):
        r["knobs"]["familiarity"] = src["rank"]
    if src.get("mood"):
        r["tags"].append(src["mood"])
    if src.get("bpm_est"):
        try:
            r["bpm"] = int(src["bpm_est"])
        except (ValueError, TypeError):
            pass
    return fill_derivable(r)


def build_catalog_track(src):
    title = src.get("track") or ""
    r = base_record(key_of("song", src.get("artist"), title), "song", "xray")
    r.update({
        "artist": src.get("artist"), "title": title, "album": src.get("album") or None,
        "notes": src.get("label") or None,
        "tags": list(src.get("tags") or []),
    })
    r["xray"] = {"show": src.get("show"), "show_title": src.get("show_title"),
                 "ep_id": src.get("ep_id"), "ep_date": src.get("ep_date")}
    return fill_derivable(r)


def rebuild(out_path, fresh_records):
    existing = {r["id"]: r for r in load_list(out_path)}
    merged = []
    seen = set()
    for fr in fresh_records:
        if fr["id"] in seen:        # dedup within this build
            continue
        seen.add(fr["id"])
        merged.append(merge(existing.get(fr["id"]), fr))
    # carry over any existing records that no longer appear in source (don't lose work)
    for rid, er in existing.items():
        if rid not in seen:
            merged.append(er)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)
    return merged


# --------------------------------------------------------------------------- #
def main():
    os.makedirs(RICH, exist_ok=True)

    albums = [build_album(a) for a in load_list(os.path.join(DATA, "top-100-albums.json"))]
    by1984 = [build_album(a, source="birthyear")
              for a in load_list(os.path.join(DATA, "birth-year-1984.json"))]
    songs = [build_song(s) for s in load_list(os.path.join(DATA, "top-100-songs.json"))]

    idx = {}
    p = os.path.join(DATA, "xray", "index.json")
    try:
        idx = json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        idx = {}
    catalog = [build_catalog_track(t) for t in idx.get("tracks", [])]

    a_out = rebuild(os.path.join(RICH, "albums.json"), albums + by1984)
    s_out = rebuild(os.path.join(RICH, "songs.json"), songs)
    c_out = rebuild(os.path.join(RICH, "catalog.json"), catalog)

    def coverage(recs, field):
        return sum(1 for r in recs if r.get(field) or r["knobs"].get(field))

    print(f"  rich/albums.json   {len(a_out):5} records")
    print(f"     era filled      {sum(1 for r in a_out if r['knobs']['era']):5}")
    print(f"     region filled   {sum(1 for r in a_out if r['region']):5}")
    print(f"     genre filled    {sum(1 for r in a_out if r['genre']):5}")
    print(f"     mood TODO        {sum(1 for r in a_out if r['knobs']['mood'] is None):5} (enrichment)")
    print(f"  rich/songs.json    {len(s_out):5} records")
    print(f"  rich/catalog.json  {len(c_out):5} records (expanded XRAY volume)")
    print(f"     era filled      {sum(1 for r in c_out if r['knobs']['era']):5}")
    print("\n  Derivable fields filled. mood/energy/density/headbody await enrichment.")


if __name__ == "__main__":
    main()
