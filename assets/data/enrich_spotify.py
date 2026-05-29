#!/usr/bin/env python3
"""
enrich_spotify.py — Auto-populate Spotify URLs + cover art + release dates
for every album in top-100-albums.json (and birth-year-1984.json) by hitting
Spotify's catalog search with client_credentials flow.

USAGE (from this directory):
    python3 enrich_spotify.py

WHAT IT DOES:
    - Calls Spotify /api/token with your Client ID + Secret
    - For each album in top-100-albums.json:
        * Searches Spotify catalog
        * Adds spotify_url, spotify_id, cover_url, release_date
        * Fills in year if it was missing
    - Same for birth-year-1984.json
    - Regenerates both .csv files to match

REQUIRES: Python 3 (already on your Mac, no installs needed)
"""

import json, urllib.request, urllib.parse, base64, time, sys, csv, os

CLIENT_ID = "95a0b516240d4e5696cd884865018c1f"
CLIENT_SECRET = "8a39f43bf978450e9efe9cbdc459aca4"

def get_token():
    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["access_token"]


def _spotify_search(token, q, limit=5):
    """Run a Spotify album search. Returns a list of result items."""
    qenc = urllib.parse.quote(q)
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/search?q={qenc}&type=album&limit={limit}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read()).get("albums", {}).get("items", [])
    except Exception:
        return []


def _format_album_result(a):
    return {
        "url": a["external_urls"]["spotify"],
        "id": a["id"],
        "cover_url": a["images"][0]["url"] if a.get("images") else "",
        "release_date": a.get("release_date", ""),
    }


def search_album(token, artist, album):
    """Multi-pass album lookup with fallbacks for self-titled albums + punctuation issues."""
    # Strip trailing punctuation that confuses Spotify's parser
    album_clean = album.rstrip("!?.").strip()
    artist_clean = artist.strip()

    # Pass 1 — strict field-based query (most precise when it works)
    items = _spotify_search(token, f'album:"{album_clean}" artist:"{artist_clean}"', limit=1)
    if items:
        return _format_album_result(items[0])

    # Pass 2 — plain text "artist album" (more forgiving of punctuation + self-titled)
    items = _spotify_search(token, f"{artist_clean} {album_clean}", limit=5)
    # Filter to actual artist matches (so we don't get a cover/tribute album)
    for a in items:
        artists_lower = [x["name"].lower() for x in a.get("artists", [])]
        if any(artist_clean.lower() in name or name in artist_clean.lower() for name in artists_lower):
            return _format_album_result(a)

    # Pass 3 — just the album name, then filter results by artist
    items = _spotify_search(token, album_clean, limit=10)
    for a in items:
        artists_lower = [x["name"].lower() for x in a.get("artists", [])]
        if any(artist_clean.lower() in name or name in artist_clean.lower() for name in artists_lower):
            return _format_album_result(a)

    return None


def fetch_album_by_id(token, spotify_id):
    """Direct album lookup by ID — used to backfill cover art when we have a manually-set URL."""
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/albums/{spotify_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            a = json.loads(r.read())
            return {
                "url": a["external_urls"]["spotify"],
                "id": a["id"],
                "cover_url": a["images"][0]["url"] if a.get("images") else "",
                "release_date": a.get("release_date", ""),
            }
    except Exception:
        return None


def enrich_file(token, json_path, csv_path, csv_columns):
    with open(json_path) as f:
        data = json.load(f)

    print(f"\n→ Enriching {json_path} ({len(data['items'])} items)...")
    hit = miss = skip = backfill = 0
    misses = []
    for i, item in enumerate(data["items"]):
        # Skip generic "(any essentials)" entries
        if "(any essentials)" in item.get("album", ""):
            skip += 1
            continue
        # Backfill: if we have spotify_url/id but no cover, look up by ID (no search needed)
        if item.get("spotify_url") and not item.get("cover_url"):
            sid = item.get("spotify_id")
            if not sid and "/album/" in item["spotify_url"]:
                sid = item["spotify_url"].split("/album/")[-1].split("?")[0]
            if sid:
                res = fetch_album_by_id(token, sid)
                time.sleep(0.06)
                if res:
                    item["cover_url"] = res["cover_url"]
                    item["spotify_id"] = res["id"]
                    if not item.get("release_date"):
                        item["release_date"] = res["release_date"]
                    backfill += 1
                    hit += 1
                    continue
        # Skip if already fully populated
        if item.get("spotify_url") and item.get("cover_url"):
            hit += 1
            continue
        res = search_album(token, item["artist"], item["album"])
        time.sleep(0.06)
        if res:
            item["spotify_url"] = res["url"]
            item["spotify_id"] = res["id"]
            item["cover_url"] = res["cover_url"]
            item["release_date"] = res["release_date"]
            if not item.get("year") and res["release_date"]:
                try:
                    item["year"] = int(res["release_date"][:4])
                except Exception:
                    pass
            hit += 1
        else:
            miss += 1
            misses.append(f"{item['artist']} — {item['album']}")
        if (i + 1) % 20 == 0:
            print(f"   ... {i+1}/{len(data['items'])}")

    # Write JSON back
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    # Regenerate CSV with any new columns (spotify_id, cover_url) tacked on the end
    if data["items"]:
        new_cols = [k for k in data["items"][0].keys() if k not in csv_columns]
        cols = csv_columns + new_cols
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for row in data["items"]:
                w.writerow({k: row.get(k, "") for k in cols})

    print(f"✓ {hit} hit · {miss} no-match · {skip} skipped (generic)")
    if misses:
        print(f"\n  --- {len(misses)} no-match (probably typo or obscure) ---")
        for m in misses[:15]:
            print(f"    · {m}")
        if len(misses) > 15:
            print(f"    ... and {len(misses)-15} more")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    print("→ Requesting Spotify bearer token...")
    try:
        token = get_token()
        print("✓ Token acquired\n")
    except Exception as e:
        print(f"✗ Could not get token: {e}")
        print("  Check that CLIENT_ID and CLIENT_SECRET at the top of this file are correct.")
        sys.exit(1)

    ALBUM_COLS = [
        "rank","artist","album","year","genre","subgenre","country",
        "format_owned","mood","standout_tracks","why_i_love_it",
        "spotify_url","spotify_search_url","discogs_search_url","notes",
    ]
    BY1984_COLS = [
        "rank","release_date","artist","album","genre","subgenre","country",
        "spotify_url","spotify_search_url","discogs_search_url",
        "format_owned","mood","why_i_love_it","notes",
    ]

    enrich_file(token, "top-100-albums.json", "top-100-albums.csv", ALBUM_COLS)
    enrich_file(token, "birth-year-1984.json", "birth-year-1984.csv", BY1984_COLS)

    print("\n→ All done. JSON + CSV files updated in place.")
    print("  spotify_url is now populated for every match.")
    print("  cover_url is now populated → the dashboard can render album art.")
    print("  release_date is filled in for everything Spotify could match.")


if __name__ == "__main__":
    main()
