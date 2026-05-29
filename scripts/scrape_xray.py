#!/usr/bin/env python3
"""
Zubissou Sounds — XRAY.fm scraper

Iterates a list of XRAY.fm shows, walks pagination to gather broadcasts,
fetches each broadcast page, parses the tracklist, and writes one JSON
file per show to ../assets/data/xray/{slug}.json.

Usage:
    python3 scrape_xray.py                  # scrape default config
    python3 scrape_xray.py --slug=the-darkest-hour --max-episodes=999
    python3 scrape_xray.py --refresh        # ignore existing data

This is a one-off ingestion script. For a nightly refresh, port the same
logic to a Cloudflare Worker on a Cron Trigger.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from datetime import datetime

# -- CONFIG ---------------------------------------------------------------
BASE = "https://xray.fm"
USER_AGENT = "ZubissouSounds/1.0 (+personal music dashboard)"
THROTTLE_S = 0.30  # polite delay between requests (used in serial mode)
PARALLEL_WORKERS = 6   # concurrent fetchers for episodes

# Show config: slug → (max_episodes_to_pull, tags)
# Default caps are conservative to fit one-show-per-bash-call. The user can
# re-run with --max-episodes=999 (or edit the cap) later — the scraper resumes
# from checkpoint and only fetches NEW episodes.
SHOWS = {
    "the-darkest-hour":         (60, ["mix", "jazz", "broad"]),  # FAVORITE — bump later
    "in-the-wilderness":        (40, ["mix"]),
    "80lb-cardstock":           (40, ["mix"]),
    "beautiful-music":          (40, ["cross-genre"]),
    "optic-echo-presents":      (40, ["mix"]),
    "get-outta-town":           (40, ["world"]),
    "hot-fudge-sunday":         (40, ["mix"]),
    "searchingforthesound":     (40, ["world"]),
    "intuitive-navigation":     (40, ["mix"]),
    "on-the-corner":            (40, ["jazz"]),
    "pacific-pulsations":       (40, ["mix"]),
    "playing-by-sense-of-smell":(40, ["mix"]),
}
SKIP = {"inside-the-wizards-hat"}  # no tracklists per user

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "data", "xray")

# -- HTTP -----------------------------------------------------------------
def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

# -- PARSERS --------------------------------------------------------------
class ShowPageParser(HTMLParser):
    """Extract broadcast links + meta from a show page."""
    def __init__(self):
        super().__init__()
        self.broadcasts = []            # [(url, broadcast_id)]
        self.show_meta = {}             # title, image, description, tags
        self.in_h1 = False
        self._h1_text = []
        self.h1_texts = []              # collect ALL h1s (first is "Shows" breadcrumb)
        self._in_title = False
        self._title_text = []
        self.page_title = None
        self.og_title = None
        self.og_description = None
        self.max_page = 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            href = a.get("href", "")
            m = re.match(r"^/broadcasts/(\d+)$", href)
            if m:
                bid = m.group(1)
                url = BASE + href
                if (url, bid) not in self.broadcasts:
                    self.broadcasts.append((url, bid))
            m = re.search(r"/programs/[^/]+/page:(\d+)", href)
            if m:
                pg = int(m.group(1))
                if pg > self.max_page: self.max_page = pg
        elif tag == "h1":
            self.in_h1 = True
            self._h1_text = []
        elif tag == "title":
            self._in_title = True
            self._title_text = []
        elif tag == "meta":
            prop = a.get("property", "") or a.get("name", "")
            content = a.get("content", "")
            if prop == "og:title": self.og_title = content
            elif prop == "og:description": self.og_description = content
        elif tag == "img":
            src = a.get("src", "")
            if "cdn.xray.fm/image" in src and "image" not in self.show_meta:
                self.show_meta["image"] = src

    def handle_endtag(self, tag):
        if tag == "h1" and self.in_h1:
            txt = "".join(self._h1_text).strip()
            if txt: self.h1_texts.append(txt)
            self.in_h1 = False
        elif tag == "title" and self._in_title:
            self.page_title = "".join(self._title_text).strip()
            self._in_title = False

    def handle_data(self, data):
        if self.in_h1: self._h1_text.append(data)
        if self._in_title: self._title_text.append(data)

    @property
    def captured_title(self):
        # Best title: og:title (strip " /// XRAY.fm"), then second h1 (skip "Shows"), then page title
        if self.og_title:
            t = self.og_title.replace("&amp;", "&").strip()
            t = re.sub(r"\s*/+\s*XRAY\.fm\s*$", "", t).strip()
            if t: return t
        if self.page_title:
            t = self.page_title.replace("&amp;", "&").strip()
            t = re.sub(r"\s*/+\s*XRAY\.fm\s*$", "", t).strip()
            if t: return t
        for h in self.h1_texts:
            if h.lower() not in ("shows", ""): return h
        return None

    @property
    def description(self):
        return self.og_description


class BroadcastParser(HTMLParser):
    """
    Extract tracklist + meta from a broadcast page.
    XRAY broadcast pages use <li class="creek-track"> with sub-<span>s:
      creek-track-time, creek-track-title, creek-track-artist,
      creek-track-album, creek-track-label
    """
    SPAN_FIELDS = {
        "creek-track-time": "time",
        "creek-track-title": "track",
        "creek-track-artist": "artist",
        "creek-track-album": "album",
        "creek-track-label": "label",
    }

    def __init__(self):
        super().__init__()
        self.title = None
        self.air_time = None
        self.audio_url = None
        self.tracks = []
        self.image = None
        self._in_h1 = False
        self._h1_text = []
        self._in_li_track = False
        self._cur_track = None       # {time,track,artist,album,label}
        self._cur_field = None       # which span we're currently inside
        self._cur_field_text = []    # accumulator for current span

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "h1":
            self._in_h1 = True
            self._h1_text = []
        elif tag == "img":
            src = a.get("src", "")
            if "cdn.xray.fm/image" in src and not self.image:
                self.image = src
        elif tag == "a":
            href = a.get("href", "")
            if href.endswith(".mp3"):
                self.audio_url = href
        elif tag == "li" and "creek-track" in cls:
            self._in_li_track = True
            self._cur_track = {"time": None, "track": None, "artist": None, "album": None, "label": None}
        elif tag == "span" and self._in_li_track and cls in self.SPAN_FIELDS:
            self._cur_field = self.SPAN_FIELDS[cls]
            self._cur_field_text = []

    def handle_endtag(self, tag):
        if tag == "h1" and self._in_h1:
            txt = "".join(self._h1_text).strip()
            if txt and not self.title:
                self.title = txt
            self._in_h1 = False
        elif tag == "span" and self._cur_field:
            val = "".join(self._cur_field_text).strip()
            # collapse runs of whitespace
            val = re.sub(r"\s+", " ", val)
            if val:
                self._cur_track[self._cur_field] = val
            self._cur_field = None
            self._cur_field_text = []
        elif tag == "li" and self._in_li_track:
            # close out the track
            t = self._cur_track
            if t.get("artist") and t.get("track"):
                self.tracks.append(t)
            self._in_li_track = False
            self._cur_track = None

    def handle_data(self, data):
        if self._in_h1: self._h1_text.append(data)
        if self._cur_field is not None: self._cur_field_text.append(data)


# -- TRACK LINE PARSER ----------------------------------------------------
TIME_RE = re.compile(r"^(\d{1,2}:\d{2}\s*[ap]m)\s+", re.IGNORECASE)
BY_RE = re.compile(r"\s+by\s+", re.IGNORECASE)
ON_RE = re.compile(r"\s+on\s+", re.IGNORECASE)
LABEL_RE = re.compile(r"\s*\(([^()]+)\)\s*$")

def parse_track_line(line):
    """
    Parse one tracklist line:
      "8:02pm Endangered Species feat. Lalah Hathaway  by Esperanza Spalding on Radio Music Society  (Heads Up )"
    -> {'time': '8:02pm', 'track': 'Endangered Species feat. Lalah Hathaway',
        'artist': 'Esperanza Spalding', 'album': 'Radio Music Society', 'label': 'Heads Up'}
    """
    if not line: return None
    # Skip obvious non-track lines
    if len(line) > 350: return None
    if line.lower().startswith(("share", "now playing", "tweet", "play / pause", "volume")):
        return None
    if " by " not in line.lower():
        return None

    time_str = None
    m = TIME_RE.match(line)
    if m:
        time_str = m.group(1).strip()
        line = line[m.end():]

    by_m = BY_RE.search(line)
    if not by_m:
        return None
    track = line[:by_m.start()].strip()
    rest = line[by_m.end():].strip()

    label = None
    lm = LABEL_RE.search(rest)
    if lm:
        label = lm.group(1).strip()
        rest = rest[:lm.start()].strip()

    on_m = ON_RE.search(rest)
    if on_m:
        artist = rest[:on_m.start()].strip()
        album = rest[on_m.end():].strip()
    else:
        artist = rest.strip()
        album = None

    # Skip if obviously garbage
    if not track or not artist:
        return None
    if len(track) > 200 or len(artist) > 200:
        return None

    return {
        "time": time_str,
        "track": track,
        "artist": artist,
        "album": album,
        "label": label,
    }


# -- DATE / META FROM BROADCAST LIST (best-effort) ------------------------
DATE_LIST_RE = re.compile(r"(\d{1,2}:\d{2}[ap]m),?\s+(\d{1,2}-\d{1,2}-\d{4})", re.IGNORECASE)

def extract_broadcasts_with_dates(html):
    """
    Walk the show page HTML and pair each broadcast link with the nearest
    preceding date string. Returns [{url, id, air_date, title}].
    """
    # Find broadcast anchors with dates by scanning windows
    out = []
    # Pattern: date string then anchor block with /broadcasts/{id}
    # We'll use regex on the raw HTML for robustness.
    pattern = re.compile(
        r"(\d{1,2}:\d{2}[ap]m),?\s+(\d{1,2}-\d{1,2}-\d{4}).*?/broadcasts/(\d+).*?>([^<]+)</a>",
        re.IGNORECASE | re.DOTALL
    )
    for m in pattern.finditer(html):
        out.append({
            "id": m.group(3),
            "url": f"{BASE}/broadcasts/{m.group(3)}",
            "air_time": m.group(1),
            "air_date": m.group(2),
            "title": m.group(4).strip(),
        })
    # dedupe
    seen = set()
    uniq = []
    for b in out:
        if b["id"] in seen: continue
        seen.add(b["id"])
        uniq.append(b)
    return uniq


def scrape_show(slug, max_episodes, tags, verbose=True):
    print(f"\n=== {slug} (max {max_episodes}) ===", flush=True)
    # Step 1: walk pagination to gather broadcasts
    all_broadcasts = []
    page = 1
    seen_ids = set()
    while True:
        url = (f"{BASE}/shows/{slug}" if page == 1
               else f"{BASE}/programs/{slug}/page:{page}?url=shows%2F{slug}")
        try:
            html = http_get(url)
        except Exception as e:
            print(f"  ! page {page} fail: {e}", flush=True)
            break
        time.sleep(THROTTLE_S)
        broadcasts = extract_broadcasts_with_dates(html)
        new_b = [b for b in broadcasts if b["id"] not in seen_ids]
        if not new_b:
            break
        for b in new_b:
            seen_ids.add(b["id"])
            all_broadcasts.append(b)
        if verbose:
            print(f"  page {page}: +{len(new_b)} (total {len(all_broadcasts)})", flush=True)
        # capture show meta from page 1
        if page == 1:
            sp = ShowPageParser()
            sp.feed(html)
            show_meta = {
                "slug": slug,
                "title": sp.captured_title or slug.replace("-", " ").title(),
                "description": sp.description,
                "image": sp.show_meta.get("image"),
                "tags": tags,
                "url": f"{BASE}/shows/{slug}",
            }
        # detect end via pagination
        max_pg = ShowPageParser()
        max_pg.feed(html)
        if page >= max_pg.max_page or len(all_broadcasts) >= max_episodes:
            break
        page += 1
        if page > 60:  # hard safety
            break

    all_broadcasts = all_broadcasts[:max_episodes]
    print(f"  → {len(all_broadcasts)} episodes to fetch", flush=True)

    # Step 2: fetch each broadcast IN PARALLEL with CHECKPOINTING.
    #   Skip episodes already present in the existing file (resume support).
    out_path = os.path.join(OUT_DIR, f"{slug}.json")
    os.makedirs(OUT_DIR, exist_ok=True)
    existing_episodes = {}
    if os.path.exists(out_path):
        try:
            old = json.load(open(out_path))
            for ep in old.get("episodes", []):
                existing_episodes[ep["id"]] = ep
            if existing_episodes:
                print(f"  ↻ resuming · {len(existing_episodes)} episodes already cached", flush=True)
        except Exception:
            pass

    to_fetch = [b for b in all_broadcasts if b["id"] not in existing_episodes]
    print(f"  → {len(to_fetch)} new to fetch ({len(existing_episodes)} cached)", flush=True)

    def fetch_and_parse(b):
        try:
            html = http_get(b["url"])
        except Exception as e:
            return ("err", b, str(e))
        bp = BroadcastParser()
        bp.feed(html)
        ep = {
            "id": b["id"],
            "url": b["url"],
            "title": bp.title or b["title"],
            "air_date": b["air_date"],
            "air_time": b["air_time"],
            "image": bp.image,
            "audio_url": bp.audio_url,
            "track_count": len(bp.tracks),
            "tracks": bp.tracks,
        }
        return ("ok", b, ep)

    episodes = list(existing_episodes.values())
    done = 0
    CHECKPOINT_EVERY = 5

    def checkpoint():
        total_tracks = sum(e["track_count"] for e in episodes)
        episodes.sort(key=lambda e: -int(e["id"]))
        out = {
            "schema_version": 1,
            "scraped_at": datetime.utcnow().isoformat() + "Z",
            "show": show_meta,
            "episode_count": len(episodes),
            "track_count_total": total_tracks,
            "episodes": episodes,
        }
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = { ex.submit(fetch_and_parse, b): b for b in to_fetch }
        for fut in as_completed(futures):
            status, b, payload = fut.result()
            done += 1
            if status == "err":
                if verbose: print(f"  ! ep {b['id']} fail: {payload}", flush=True)
                continue
            episodes.append(payload)
            if done % CHECKPOINT_EVERY == 0 or done == len(to_fetch):
                total_tracks = sum(e["track_count"] for e in episodes)
                print(f"  [{done}/{len(to_fetch)}] · {len(episodes)} eps · {total_tracks} tracks · CHKPT", flush=True)
                checkpoint()
    episodes.sort(key=lambda e: -int(e["id"]))

    checkpoint()
    total_tracks = sum(e["track_count"] for e in episodes)
    print(f"  ✓ wrote {out_path}  ({len(episodes)} eps, {total_tracks} tracks)", flush=True)
    return None


# -- INDEX (catalog of all shows + flat track list) -----------------------
def build_index():
    """After scraping, walk OUT_DIR and build a master index for fast loading."""
    flat_tracks = []
    show_list = []
    seen_pairs = set()  # (artist|track) dedupe within index
    for fname in sorted(os.listdir(OUT_DIR)):
        if not fname.endswith(".json") or fname == "index.json": continue
        path = os.path.join(OUT_DIR, fname)
        with open(path) as f: d = json.load(f)
        show = d["show"]
        show_list.append({
            "slug": show["slug"],
            "title": show["title"],
            "image": show.get("image"),
            "tags": show.get("tags", []),
            "url": show["url"],
            "episode_count": d.get("episode_count", 0),
            "track_count_total": d.get("track_count_total", 0),
        })
        for ep in d.get("episodes", []):
            for t in ep.get("tracks", []):
                key = ((t.get("artist") or "").lower().strip(), (t.get("track") or "").lower().strip())
                if not key[0] or not key[1]: continue
                if key in seen_pairs: continue
                seen_pairs.add(key)
                flat_tracks.append({
                    "artist": t["artist"],
                    "track": t["track"],
                    "album": t.get("album"),
                    "label": t.get("label"),
                    "show": show["slug"],
                    "show_title": show["title"],
                    "tags": show.get("tags", []),
                    "ep_id": ep["id"],
                    "ep_date": ep.get("air_date"),
                })
    index = {
        "schema_version": 1,
        "built_at": datetime.utcnow().isoformat() + "Z",
        "shows": show_list,
        "unique_track_count": len(flat_tracks),
        "tracks": flat_tracks,
    }
    out_path = os.path.join(OUT_DIR, "index.json")
    with open(out_path, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"\n✓ wrote {out_path}  ({len(show_list)} shows, {len(flat_tracks)} unique tracks)", flush=True)


# -- MAIN -----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="only this show")
    ap.add_argument("--max-episodes", type=int, default=None)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if file exists")
    ap.add_argument("--index-only", action="store_true", help="just rebuild the master index from existing files")
    args = ap.parse_args()

    if args.index_only:
        build_index()
        return

    shows_to_run = SHOWS
    if args.slug:
        shows_to_run = { args.slug: SHOWS.get(args.slug, (50, [])) }

    for slug, (max_eps, tags) in shows_to_run.items():
        if slug in SKIP:
            print(f"--- SKIP {slug} (no tracklists)", flush=True)
            continue
        out_path = os.path.join(OUT_DIR, f"{slug}.json")
        if os.path.exists(out_path) and not args.refresh:
            print(f"--- SKIP {slug} (exists; use --refresh to redo)", flush=True)
            continue
        eps = args.max_episodes or max_eps
        try:
            scrape_show(slug, eps, tags)
        except KeyboardInterrupt:
            print("interrupted", flush=True)
            break
        except Exception as e:
            print(f"!! {slug} crashed: {e}", flush=True)

    build_index()


if __name__ == "__main__":
    main()
