#!/usr/bin/env python3
"""
Zubissou Sounds — XRAY shows → Spotify playlists.

Turns each scraped XRAY show into a private Spotify playlist:
  - playlist name        = show title (as-is)
  - playlist description = show bio (normalized to plain text)
  - tracks added in the order they were found (episode order), deduped per show

The XRAY tracklists are plain text (artist + track + album + label) with no
Spotify IDs, so every track is resolved via the Spotify Search API using a
match waterfall:

    1. exact recording  ->  track + artist + album  (same version)
    2. same song, any version (live<->studio fallback)
    3. fuzzy artist+track best guess above threshold
    4. miss  ->  recorded so it can be retried later

RESUMABLE. Every track that gets *attempted* (hit or miss) is written to a
cache, and the cache is saved every few seconds. If Spotify rate-limits us or
you Ctrl+C, just run the same command again — it skips everything already done.

State files (in assets/data/xray/):
    matched.json   norm(artist|track) -> {uri | null, ...}  (the resume cache)
    misses.json    human-readable "not on Spotify yet" DB, grouped by show,
                   with empty knob fields for the later enrichment pass.

Auth: Spotify Authorization-Code + PKCE (no client secret). A tiny local server
catches the redirect on the already-registered URI
    http://127.0.0.1:8080/zubissou-sounds.html
Token cached in scripts/.spotify_token.json so you only log in once.

Stdlib only — nothing to pip install.

USAGE
    python3 scripts/build_playlists.py --show the-darkest-hour --dry-run
    python3 scripts/build_playlists.py --show the-darkest-hour
    python3 scripts/build_playlists.py --all
    python3 scripts/build_playlists.py --retry-misses
"""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, HTTPServer

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
CLIENT_ID = "95a0b516240d4e5696cd884865018c1f"
REDIRECT_URI = "http://127.0.0.1:8080/zubissou-sounds.html"
REDIRECT_PORT = 8080
SCOPES = ("playlist-modify-private playlist-modify-public playlist-read-private "
          "playlist-read-collaborative user-read-private user-read-email "
          "user-library-read user-library-modify")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
XRAY_DIR = os.path.join(REPO, "assets", "data", "xray")
TOKEN_FILE = os.path.join(HERE, ".spotify_token.json")
MATCHED_FILE = os.path.join(XRAY_DIR, "matched.json")
MISSES_FILE = os.path.join(XRAY_DIR, "misses.json")

PLAYLIST_DESC_SUFFIX = " · auto-built by Zubissou Sounds from XRAY.fm"

# Acceptance thresholds for the match scorer
EXACT_TITLE = 0.86
EXACT_ARTIST = 0.60
LOOSE_TITLE = 0.72
LOOSE_ARTIST = 0.70

# Pacing / rate-limit safety
TRACK_PAUSE = 0.12          # seconds between tracks (be polite to the API)
SAVE_EVERY = 20             # save the cache every N newly-attempted tracks
MAX_WAIT = 900              # if Spotify asks us to wait longer than this (15 min),
                            # save and exit cleanly instead of hanging


class CoolOff(Exception):
    """Spotify handed us a long Retry-After; bail out and let the user resume."""
    def __init__(self, wait):
        self.wait = wait
        super().__init__(f"cool-off {wait}s")


# --------------------------------------------------------------------------- #
# String helpers
# --------------------------------------------------------------------------- #
def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize(s):
    s = strip_accents((s or "").lower())
    s = re.sub(r"\bfeat\.?\b.*", "", s)
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def primary_artist(artist):
    a = (artist or "").split("/")[0]
    a = re.sub(r"\bfeat\.?\b.*", "", a, flags=re.I)
    return a.strip()


def clean_title_for_query(track):
    raw = (track or "").strip().strip("'\"")
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", raw)
    t = re.sub(r"\bfeat\.?\b.*", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip().strip("'\"")
    return t or raw


def sim(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def title_sim(q, c):
    nq, nc = normalize(q), normalize(c)
    if not nq or not nc:
        return 0.0
    base = SequenceMatcher(None, nq, nc).ratio()
    core_q = normalize(re.split(r"\s-\s", q)[0])
    core_c = normalize(re.split(r"\s-\s", c)[0])
    core = SequenceMatcher(None, core_q, core_c).ratio()
    qt, ct = set(nq.split()), set(nc.split())
    contain = len(qt & ct) / len(qt) if qt else 0.0
    return max(base, core, contain)


def looks_live(s):
    return bool(re.search(r"\b(live|en vivo|concert|session)\b", (s or ""), re.I))


def plain_text(s):
    s = strip_accents(unicodedata.normalize("NFKC", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def track_key(artist, track):
    return normalize(primary_artist(artist)) + "|" + normalize(track)


# --------------------------------------------------------------------------- #
# JSON state load/save
# --------------------------------------------------------------------------- #
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def empty_knob_fields():
    return {"year": None, "genre": None, "country": None, "mood": None,
            "energy": None, "density": None, "head_body": None,
            "familiar": None, "place": None}


def write_misses_db(matched):
    """Rebuild the human-readable misses.json (grouped by show) from the cache."""
    grouped = {}
    for rec in matched.values():
        if rec.get("uri"):
            continue
        slug = rec.get("show", "?")
        grouped.setdefault(slug, []).append({
            "artist": rec.get("artist"), "track": rec.get("track"),
            "album": rec.get("album"), "label": rec.get("label"),
            "show": slug, "show_title": rec.get("show_title"),
            "ep_id": rec.get("ep_id"), "ep_date": rec.get("ep_date"),
            "reason": rec.get("reason"), "knobs": rec.get("knobs", empty_knob_fields()),
        })
    save_json(MISSES_FILE, grouped)


def persist(matched):
    save_json(MATCHED_FILE, matched)
    write_misses_db(matched)


# --------------------------------------------------------------------------- #
# OAuth (Authorization Code + PKCE)
# --------------------------------------------------------------------------- #
class _CodeCatcher(BaseHTTPRequestHandler):
    code = None
    state = None

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CodeCatcher.code = (params.get("code") or [None])[0]
        _CodeCatcher.state = (params.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:sans-serif;background:#11100e;"
            b"color:#e8d9b5;display:flex;height:100vh;align-items:center;"
            b"justify-content:center'><div style='text-align:center'>"
            b"<h2>Zubissou Sounds connected.</h2>"
            b"<p>Close this tab and return to your terminal.</p>"
            b"</div></body></html>")

    def log_message(self, *a):
        pass


def _http_post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def _save_token(tok):
    tok["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
    save_json(TOKEN_FILE, tok)
    return tok


def _interactive_auth():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT_URI,
        "scope": SCOPES, "code_challenge_method": "S256",
        "code_challenge": challenge, "state": state})

    print("\n  Opening Spotify authorization in your browser…")
    print("  If it doesn't open, paste this URL manually:\n")
    print("   ", auth_url, "\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CodeCatcher)
    print(f"  Waiting for the redirect on 127.0.0.1:{REDIRECT_PORT} …")
    while _CodeCatcher.code is None:
        server.handle_request()
    server.server_close()
    if _CodeCatcher.state != state:
        sys.exit("  ! OAuth state mismatch — aborting for safety.")

    tok = _http_post_form("https://accounts.spotify.com/api/token", {
        "grant_type": "authorization_code", "code": _CodeCatcher.code,
        "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID, "code_verifier": verifier})
    print("  ✓ Authorized.\n")
    return _save_token(tok)


def _refresh(tok):
    new = _http_post_form("https://accounts.spotify.com/api/token", {
        "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
        "client_id": CLIENT_ID})
    new.setdefault("refresh_token", tok["refresh_token"])
    return _save_token(new)


def get_token():
    tok = load_json(TOKEN_FILE, None)
    if not tok:
        return _interactive_auth()
    if time.time() >= tok.get("expires_at", 0):
        try:
            return _refresh(tok)
        except Exception:
            return _interactive_auth()
    return tok


# --------------------------------------------------------------------------- #
# Spotify API
# --------------------------------------------------------------------------- #
class Spotify:
    def __init__(self):
        self.tok = get_token()
        self.me = self._get("/me")
        self.search_calls = 0

    def _auth_header(self):
        return {"Authorization": "Bearer " + self.tok["access_token"]}

    def _request(self, method, path, body=None, _retry=True):
        url = "https://api.spotify.com/v1" + path
        headers = self._auth_header()
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "2")) + 1
                if wait > MAX_WAIT:
                    raise CoolOff(wait)
                print(f"    · rate limited, waiting {wait}s")
                time.sleep(wait)
                return self._request(method, path, body, _retry)
            if e.code == 401 and _retry:
                self.tok = _refresh(self.tok)
                return self._request(method, path, body, _retry=False)
            raise

    def _get(self, path):
        return self._request("GET", path)

    def _search(self, q, limit=6):
        self.search_calls += 1
        path = "/search?" + urllib.parse.urlencode({"q": q, "type": "track", "limit": limit})
        return (self._request("GET", path).get("tracks") or {}).get("items") or []

    def search_track(self, artist, track, album=None):
        # Two queries max (keeps API volume down): album-assisted, then artist-only.
        a, t = primary_artist(artist), clean_title_for_query(track)
        if album:
            items = self._search(f'track:{t} artist:{a} album:{album}')
            if items:
                return items
        return self._search(f'track:{t} artist:{a}')

    def find_playlist_by_name(self, name):
        path = "/me/playlists?limit=50"
        while path:
            page = self._request("GET", path)
            for pl in page.get("items", []):
                if pl and pl.get("name") == name and pl.get("owner", {}).get("id") == self.me["id"]:
                    return pl
            nxt = page.get("next")
            path = nxt.replace("https://api.spotify.com/v1", "") if nxt else None
        return None

    def create_playlist(self, name, description):
        return self._request("POST", f"/users/{self.me['id']}/playlists",
                             {"name": name, "description": description, "public": False})

    def set_playlist_tracks(self, playlist_id, uris):
        first, rest = uris[:100], uris[100:]
        self._request("PUT", f"/playlists/{playlist_id}/tracks", {"uris": first})
        for i in range(0, len(rest), 100):
            self._request("POST", f"/playlists/{playlist_id}/tracks", {"uris": rest[i:i + 100]})

    def update_description(self, playlist_id, description):
        self._request("PUT", f"/playlists/{playlist_id}", {"description": description})


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def score_candidate(artist, track, album, cand):
    cand_artists = " ".join(a["name"] for a in cand.get("artists", []))
    t_sim = title_sim(track, cand.get("name", ""))
    a_sim = max(sim(primary_artist(artist), cand_artists), sim(artist, cand_artists))
    album_match = bool(album) and sim(album, (cand.get("album") or {}).get("name", "")) > 0.8
    version_match = looks_live(track) == looks_live(cand.get("name", ""))
    return t_sim, a_sim, album_match, version_match


def best_match(artist, track, album, items):
    ranked = []
    for c in items:
        t_sim, a_sim, album_match, version_match = score_candidate(artist, track, album, c)
        score = 0.6 * t_sim + 0.4 * a_sim + (0.15 if album_match else 0) + (0.05 if version_match else 0)
        ranked.append((score, t_sim, a_sim, album_match, c))
    if not ranked:
        return None, "no_results", None
    ranked.sort(key=lambda x: x[0], reverse=True)
    score, t_sim, a_sim, album_match, c = ranked[0]
    if t_sim >= EXACT_TITLE and a_sim >= EXACT_ARTIST:
        return c["uri"], ("exact" if album_match else "same_song_alt_version"), c
    if t_sim >= LOOSE_TITLE and a_sim >= LOOSE_ARTIST:
        return c["uri"], "fuzzy", c
    return None, f"low_conf(t={t_sim:.2f},a={a_sim:.2f})", None


# --------------------------------------------------------------------------- #
# Show processing
# --------------------------------------------------------------------------- #
def gather_show_tracks(show_json):
    seen, ordered = set(), []
    for ep in show_json.get("episodes", []):
        for t in ep.get("tracks", []):
            k = track_key(t.get("artist", ""), t.get("track", ""))
            if not k.strip("|") or k in seen:
                continue
            seen.add(k)
            rec = dict(t)
            rec["_ep_id"] = ep.get("id")
            rec["_ep_date"] = ep.get("air_date")
            ordered.append(rec)
    return ordered


def attempt_track(sp, slug, title, t, matched):
    """Search + score one track, writing the result (hit or miss) into the cache."""
    key = track_key(t.get("artist", ""), t.get("track", ""))
    items = sp.search_track(t.get("artist", ""), t.get("track", ""), t.get("album"))
    uri, via, cand = best_match(t.get("artist", ""), t.get("track", ""), t.get("album"), items)
    if uri:
        matched[key] = {
            "uri": uri, "via": via,
            "artist": t.get("artist"), "track": t.get("track"),
            "matched_name": cand.get("name"),
            "matched_artist": ", ".join(a["name"] for a in cand.get("artists", [])),
            "matched_album": (cand.get("album") or {}).get("name"),
            "release_date": (cand.get("album") or {}).get("release_date"),
        }
    else:
        matched[key] = {
            "uri": None, "reason": via,
            "artist": t.get("artist"), "track": t.get("track"),
            "album": t.get("album"), "label": t.get("label"),
            "show": slug, "show_title": title,
            "ep_id": t.get("_ep_id"), "ep_date": t.get("_ep_date"),
            "knobs": empty_knob_fields(),
        }
    return key


def process_show(sp, slug, matched, dry_run=False):
    path = os.path.join(XRAY_DIR, slug + ".json")
    show_json = load_json(path, None)
    if not show_json:
        print(f"  ! {slug}: file not found, skipping")
        return None
    show = show_json.get("show", {})
    title = show.get("title", slug)
    bio = plain_text(show.get("description", ""))
    desc = (bio + PLAYLIST_DESC_SUFFIX).strip()[:300]

    tracks = gather_show_tracks(show_json)
    if not tracks:
        print(f"  · {title}: 0 tracks, skipping")
        return None

    print(f"\n  ── {title}  ({len(tracks)} unique tracks) ──")
    attempted_now = 0
    for i, t in enumerate(tracks, 1):
        key = track_key(t.get("artist", ""), t.get("track", ""))
        if key in matched:               # already tried (hit or miss) — resume skips it
            continue
        attempt_track(sp, slug, title, t, matched)
        attempted_now += 1
        if attempted_now % SAVE_EVERY == 0:
            persist(matched)
            done = sum(1 for x in tracks if track_key(x.get("artist",""), x.get("track","")) in matched)
            hits = sum(1 for x in tracks
                       if matched.get(track_key(x.get("artist",""), x.get("track","")), {}).get("uri"))
            print(f"     {done}/{len(tracks)} done … {hits} matched")
        time.sleep(TRACK_PAUSE)

    persist(matched)

    # Build the playlist from the cache, in track order
    uris, found, missed = [], 0, 0
    for t in tracks:
        rec = matched.get(track_key(t.get("artist", ""), t.get("track", "")))
        if rec and rec.get("uri"):
            uris.append(rec["uri"]); found += 1
        else:
            missed += 1
    hit = 100 * found // max(1, found + missed)
    print(f"     → {found} matched / {missed} missed  ({hit}% hit rate)")

    if dry_run:
        print(f"     [dry-run] would build “{title}” with {len(uris)} tracks (nothing created)")
    elif not uris:
        print(f"     ! nothing matched for “{title}”, no playlist created")
    else:
        existing = sp.find_playlist_by_name(title)
        if existing:
            sp.set_playlist_tracks(existing["id"], uris)
            sp.update_description(existing["id"], desc)
            print(f"     ✓ updated playlist “{title}” ({len(uris)} tracks)")
        else:
            pl = sp.create_playlist(title, desc)
            sp.set_playlist_tracks(pl["id"], uris)
            print(f"     ✓ created playlist “{title}” ({len(uris)} tracks)")
    return {"title": title, "found": found, "missed": missed}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def all_show_slugs():
    idx = load_json(os.path.join(XRAY_DIR, "index.json"), {})
    return [s["slug"] for s in idx.get("shows", []) if s.get("track_count_total", 0) > 0]


def main():
    ap = argparse.ArgumentParser(description="Build Spotify playlists from XRAY shows.")
    ap.add_argument("--show", help="single show slug (e.g. the-darkest-hour)")
    ap.add_argument("--all", action="store_true", help="build every show with tracks")
    ap.add_argument("--dry-run", action="store_true", help="match only; create nothing")
    ap.add_argument("--retry-misses", action="store_true",
                    help="forget previous misses and re-attempt them")
    args = ap.parse_args()

    if not (args.show or args.all or args.retry_misses):
        ap.error("pick one of --show <slug>, --all, or --retry-misses")

    matched = load_json(MATCHED_FILE, {})

    # retry-misses = drop the null (miss) entries so they get searched again
    if args.retry_misses:
        miss_shows = sorted({v.get("show") for v in matched.values()
                             if not v.get("uri") and v.get("show")})
        before = len(matched)
        matched = {k: v for k, v in matched.items() if v.get("uri")}
        print(f"  retry-misses: cleared {before - len(matched)} misses to re-attempt")
        slugs = miss_shows or all_show_slugs()
    elif args.all:
        slugs = all_show_slugs()
    else:
        slugs = [args.show]

    sp = Spotify()
    print(f"  Logged in as: {sp.me.get('display_name') or sp.me.get('id')}")

    summary = []
    try:
        for slug in slugs:
            res = process_show(sp, slug, matched, dry_run=args.dry_run)
            if res:
                summary.append(res)
            persist(matched)
    except CoolOff as e:
        persist(matched)
        hrs = e.wait / 3600
        print(f"\n  ⏸  Spotify is rate-limiting hard (asked us to wait ~{hrs:.1f}h).")
        print("     Progress is SAVED. Re-run the same command later — it resumes")
        print("     and skips everything already done. Cache:",
              os.path.relpath(MATCHED_FILE, REPO))
        return
    except KeyboardInterrupt:
        persist(matched)
        print("\n  ⏸  Stopped. Progress saved — re-run to resume.")
        return

    print("\n  ============ SUMMARY ============")
    tot_f = tot_m = 0
    for r in summary:
        tot_f += r["found"]; tot_m += r["missed"]
        print(f"   {r['title'][:30]:32} {r['found']:5} matched  {r['missed']:5} missed")
    rate = 100 * tot_f // max(1, tot_f + tot_m)
    print(f"   {'TOTAL':32} {tot_f:5} matched  {tot_m:5} missed   ({rate}% hit)")
    print(f"   search API calls this run: {sp.search_calls}")
    print(f"\n   resume cache → {os.path.relpath(MATCHED_FILE, REPO)}")
    print(f"   misses DB    → {os.path.relpath(MISSES_FILE, REPO)}")
    if args.dry_run:
        print("   (dry run — no playlists were created or modified)")


if __name__ == "__main__":
    main()
