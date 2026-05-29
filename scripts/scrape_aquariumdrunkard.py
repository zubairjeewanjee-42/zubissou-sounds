#!/usr/bin/env python3
"""
Zubissou Sounds — Aquarium Drunkard scraper (knowledge-base edition).

Captures every public AD post we walk and stores a *rich* record per post:
the full body text, all tags, every streaming link (Spotify / Apple / Tidal /
Bandcamp / SoundCloud / Mixcloud / YouTube / archive.org), author + dates,
cover image, gating flag. The intent is a personal listening knowledge base
that powers (a) the AI DJ voice (ElevenLabs) with real curator context to read
or paraphrase, (b) the user's own learning, and (c) the knobs — albums with
Spotify IDs are real, playable picks that can join the canon's selection pool.

Outputs (in assets/data/curators/aquariumdrunkard/):
    posts.json     primary store — every scraped post keyed by URL
    reviews.json   derived view — posts that resolve to a Spotify album
    mixtapes.json  derived view — posts discovered under /category/mixtapes/
    context/<slug>.md
                   per-post markdown — ready to drop into LLM context, hand to
                   the DJ for narration, or just read.
    index.json     {scraped_at, post_count, review_count, mixtape_count, …}

Modes (mix and match; default = --all):
    --front       /
    --mixtapes    /category/mixtapes/
    --interviews  /category/the-ad-interview/
    --lagniappe   /category/lagniappe-sessions/
    --podcast     /category/podcast/
    --all         all five above

Polite (1.2s between requests, identified User-Agent). Resumable — skips posts
already in posts.json unless --refresh is passed. Stdlib only.

NOTE: AD body text is © Aquarium Drunkard. This script is for personal use as
a private knowledge base on your own machine — don't republish their writing.
"""

import argparse, json, os, re, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime
from html import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT  = os.path.join(REPO, "assets", "data", "curators", "aquariumdrunkard")
POSTS_FILE    = os.path.join(OUT, "posts.json")
REVIEWS_FILE  = os.path.join(OUT, "reviews.json")
MIXTAPES_FILE = os.path.join(OUT, "mixtapes.json")
CAROUSEL_FILE = os.path.join(OUT, "carousel.json")
INDEX_FILE    = os.path.join(OUT, "index.json")
CONTEXT_DIR   = os.path.join(OUT, "context")

BASE = "https://aquariumdrunkard.com"
UA = "ZubissouSounds/1.0 (+personal listening knowledge base; contact: gooneglobal@gmail.com)"
PAUSE = 1.2
COOKIE_HEADER = ""    # set from --cookies-file at startup; sent on every request

# Category sections to walk
SOURCES = {
    "front":      ("/",                            "frontfeed"),
    "mixtapes":   ("/category/mixtapes/",          "mixtape"),
    "interviews": ("/category/the-ad-interview/",  "interview"),
    "lagniappe":  ("/category/lagniappe-sessions/", "lagniappe"),
    "podcast":    ("/category/podcast/",           "podcast"),
}


# --------------------------------------------------------------------------- #
def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, ValueError): return d
def save(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"; json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)

def fetch(url, retries=3):
    headers = {"User-Agent": UA, "Accept": "text/html"}
    if COOKIE_HEADER: headers["Cookie"] = COOKIE_HEADER
    req = urllib.request.Request(url, headers=headers)
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503): time.sleep(4 + i * 3); continue
            return None
        except urllib.error.URLError:
            time.sleep(3); continue
    return None


def strip_tags(s):
    # block-level tags become newlines first so line-based regexes still work
    s = re.sub(r"</(p|li|div|br|h[1-6])\s*>|<br\s*/?>", "\n", s or "", flags=re.I)
    return unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def text_block(s):
    """Strip tags but preserve paragraph breaks for readable body output."""
    s = re.sub(r"</(p|li|div|h[1-6])\s*>", "\n\n", s or "", flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
POST_RE = re.compile(r'href="(https://aquariumdrunkard\.com/(\d{4})/(\d{2})/(\d{2})/([a-z0-9-]+)/?)"')

def discover_posts(list_path, pages, source_label):
    url0 = BASE + list_path
    urls = []; seen = set()
    for n in range(1, pages + 1):
        u = url0 if n == 1 else f"{url0.rstrip('/')}/page/{n}/"
        html = fetch(u)
        if not html: break
        found = 0
        for m in POST_RE.finditer(html):
            url, y, mo, d, slug = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            if url in seen: continue
            seen.add(url); urls.append({"url": url, "date": f"{y}-{mo}-{d}", "slug": slug, "source": source_label})
            found += 1
        print(f"     [{source_label}] page {n}: +{found}")
        if found == 0: break
        time.sleep(PAUSE)
    return urls


# --------------------------------------------------------------------------- #
# Post parsing — extracts the rich record
# --------------------------------------------------------------------------- #
H1_RE       = re.compile(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', re.S)
OG_TTL_RE   = re.compile(r'<meta\s+property="og:title"\s+content="([^"]+)"')
OG_IMG_RE   = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')
META_PUB    = re.compile(r'<meta\s+property="article:published_time"\s+content="([^"]+)"')
META_MOD    = re.compile(r'<meta\s+property="article:modified_time"\s+content="([^"]+)"')
META_AUTHOR = re.compile(r'<meta\s+name="author"\s+content="([^"]+)"')
META_DESC   = re.compile(r'<meta\s+name="description"\s+content="([^"]+)"')

# article body — AD uses <div class="entry-content"> in their WP theme
BODY_RE = re.compile(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>\s*(?:<footer|<div[^>]*class="[^"]*(?:post-meta|cat-links|further-exploration)[^"]*"|<aside|<nav)', re.S | re.I)
# fallback: between H1 and first sidebar/footer marker
FALLBACK_BODY = re.compile(r'<h1[^>]*entry-title[^"]*"[^>]*>.*?</h1>(.*?)(?:<aside|<footer|<nav|<div[^>]*sidebar|<section[^>]*related|<h2[^>]*>Further Exploration)', re.S | re.I)

CATEGORY_LINK_RE = re.compile(r'<a[^>]+href="https://aquariumdrunkard\.com/category/([a-z0-9-]+)/?"[^>]*>([^<]+)</a>', re.I)

LINK_PATTERNS = [
    ("spotify_album",   re.compile(r'https://open\.spotify\.com/album/[a-zA-Z0-9]+')),
    ("spotify_track",   re.compile(r'https://open\.spotify\.com/track/[a-zA-Z0-9]+')),
    ("spotify_artist",  re.compile(r'https://open\.spotify\.com/artist/[a-zA-Z0-9]+')),
    ("spotify_playlist",re.compile(r'https://open\.spotify\.com/playlist/[a-zA-Z0-9]+')),
    ("apple_music",     re.compile(r'https://music\.apple\.com/[^\s"\'<>]+')),
    ("tidal",           re.compile(r'https://tidal\.com/[^\s"\'<>]+')),
    ("bandcamp",        re.compile(r'https://[a-z0-9-]+\.bandcamp\.com/[^\s"\'<>]*|https://bandcamp\.com/[^\s"\'<>]+')),
    ("soundcloud",      re.compile(r'https://soundcloud\.com/[^\s"\'<>]+')),
    ("mixcloud",        re.compile(r'https://(?:www\.)?mixcloud\.com/[^\s"\'<>]+')),
    ("youtube",         re.compile(r'https://(?:www\.)?(?:youtube\.com/watch\?v=[^\s"\'<>]+|youtu\.be/[^\s"\'<>]+)')),
    ("archive_org",     re.compile(r'https://archive\.org/[^\s"\'<>]+')),
]

# Categories that appear in every page's nav/footer — exclude from "tags"
NAV_CATEGORIES = {"the-ad-interview", "lagniappe-sessions", "podcast",
                  "the-aquarium-drunkard-picture-show"}

PAYWALL_MARKERS = ("become a member", "rcp_login_form", "to continue reading")
def is_gated(html):
    s = html.lower()
    return any(m in s for m in PAYWALL_MARKERS)


def parse_artist_album(title):
    """AD uses 'Artist :: Album' (sometimes with a trailing :: and no album)."""
    t = re.sub(r"\s+", " ", title or "").strip()
    # strip trailing :: / dangling separators
    t = re.sub(r"\s*::\s*$", "", t)
    if " :: " in t:
        a, _, al = t.partition(" :: ")
        a, al = a.strip(), al.strip()
        return (a or None), (al or a or None)
    return None, t


def extract_body(html):
    m = BODY_RE.search(html)
    if m: return m.group(1)
    m = FALLBACK_BODY.search(html)
    if m: return m.group(1)
    return ""


def extract_links(html):
    out = {kind: [] for kind, _ in LINK_PATTERNS}
    for kind, pat in LINK_PATTERNS:
        seen = set()
        for m in pat.finditer(html):
            u = m.group(0)
            if u in seen: continue
            seen.add(u); out[kind].append(u)
    return out


def extract_tags(html):
    seen = set(); tags = []
    for m in CATEGORY_LINK_RE.finditer(html):
        slug, name = m.group(1), strip_tags(m.group(2))
        if slug in NAV_CATEGORIES: continue
        if slug in seen: continue
        seen.add(slug); tags.append({"slug": slug, "name": name})
    return tags


def post_type_of(record):
    if record["links"].get("spotify_album"):     return "review"
    if record.get("source") == "mixtape":         return "mixtape"
    if record.get("source") == "interview":       return "interview"
    if record.get("source") == "lagniappe":       return "lagniappe"
    if record.get("source") == "podcast":         return "podcast"
    return "feature"


def scrape_post(stub):
    html = fetch(stub["url"])
    if not html: return None
    h1 = H1_RE.search(html); og = OG_TTL_RE.search(html)
    title = strip_tags(h1.group(1)) if h1 else (strip_tags(og.group(1)) if og else stub["slug"])
    artist, album = parse_artist_album(title)
    img = OG_IMG_RE.search(html); cover = img.group(1) if img else None
    pub = META_PUB.search(html); mod = META_MOD.search(html)
    auth = META_AUTHOR.search(html); desc = META_DESC.search(html)
    body_html = extract_body(html)
    body = text_block(body_html)
    gated = is_gated(html)
    rec = {
        "url": stub["url"], "slug": stub["slug"], "date": stub["date"],
        "source": stub.get("source", "frontfeed"),
        "title": title, "artist": artist, "album": album,
        "author": auth.group(1) if auth else None,
        "published_time": pub.group(1) if pub else None,
        "modified_time":  mod.group(1) if mod else None,
        "description": strip_tags(desc.group(1)) if desc else None,
        "cover_url": cover,
        "tags": extract_tags(html),
        "links": extract_links(html),
        "body_text": body if not gated else (body.split("Only the good shit")[0].strip() if "Only the good shit" in body else body[:1000].strip()),
        "gated": gated,
    }
    rec["post_type"] = post_type_of(rec)
    return rec


# --------------------------------------------------------------------------- #
# Context markdown — per-post, LLM-ready
# --------------------------------------------------------------------------- #
def write_context_md(rec):
    os.makedirs(CONTEXT_DIR, exist_ok=True)
    parts = []
    parts.append(f"# {rec['title']}\n")
    bits = []
    if rec.get("artist") and rec.get("album"): bits.append(f"**{rec['artist']} — {rec['album']}**")
    bits.append(f"_{rec.get('date','')}_")
    if rec.get("author"): bits.append(f"by {rec['author']}")
    if rec.get("post_type"): bits.append(f"`{rec['post_type']}`")
    parts.append(" · ".join(bits))
    if rec.get("tags"):
        parts.append("**Tags:** " + ", ".join(t["name"] for t in rec["tags"]))
    parts.append(f"\n[source]({rec['url']})")
    # links
    L = rec["links"]
    link_lines = []
    if L.get("spotify_album"):    link_lines.append("Spotify album: " + L["spotify_album"][0])
    if L.get("spotify_playlist"): link_lines.append("Spotify playlist: " + L["spotify_playlist"][0])
    if L.get("apple_music"):      link_lines.append("Apple Music: " + L["apple_music"][0])
    if L.get("tidal"):            link_lines.append("Tidal: " + L["tidal"][0])
    if L.get("bandcamp"):         link_lines.append("Bandcamp: " + L["bandcamp"][0])
    if L.get("soundcloud"):       link_lines.append("SoundCloud: " + L["soundcloud"][0])
    if L.get("mixcloud"):         link_lines.append("Mixcloud: " + L["mixcloud"][0])
    if L.get("youtube"):          link_lines.append("YouTube: " + L["youtube"][0])
    if L.get("archive_org"):      link_lines.append("Archive.org: " + L["archive_org"][0])
    if link_lines:
        parts.append("\n## Links\n" + "\n".join("- " + x for x in link_lines))
    if rec.get("gated"):
        parts.append("\n> _AD members-only — body text is truncated to the public excerpt._")
    parts.append("\n## Body\n\n" + (rec.get("body_text") or "_(no body extracted)_"))
    open(os.path.join(CONTEXT_DIR, rec["slug"] + ".md"), "w", encoding="utf-8").write("\n".join(parts))


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def run(sources, pages, refresh=False):
    posts = load(POSTS_FILE, {})
    # discover stubs from each chosen source
    stubs = []
    print(f"\n  Discovering posts …")
    for s in sources:
        path, label = SOURCES[s]
        stubs += discover_posts(path, pages, label)
    # dedup
    seen = set(); uniq = []
    for s in stubs:
        if s["url"] in seen: continue
        seen.add(s["url"]); uniq.append(s)
    todo = uniq if refresh else [s for s in uniq if s["url"] not in posts]
    print(f"  {len(uniq)} unique stubs · {len(todo)} need scraping (existing: {len(posts)})")

    added = 0
    for i, st in enumerate(todo, 1):
        rec = scrape_post(st)
        if rec:
            # merge source labels if we discover the same post in multiple sections
            prev = posts.get(rec["url"])
            if prev and prev.get("source") and rec["source"] not in (prev.get("sources") or [prev["source"]]):
                rec["sources"] = sorted(set((prev.get("sources") or [prev["source"]]) + [rec["source"]]))
            posts[rec["url"]] = rec
            write_context_md(rec)
            added += 1
            tag = "🔒 gated" if rec["gated"] else rec["post_type"]
            preview = (rec.get("artist") or "") + (" — " + rec["album"] if rec.get("album") else "")
            print(f"     ✓ [{tag:9}] {(preview or rec['title'])[:70]}")
        if i % 8 == 0:
            save(POSTS_FILE, posts)
        time.sleep(PAUSE)
    save(POSTS_FILE, posts)

    # derived views
    reviews  = [p for p in posts.values() if p.get("post_type") == "review"]
    mixtapes = {p["slug"]: p for p in posts.values() if "mixtape" in ((p.get("sources") or []) + [p.get("source")])}
    save(REVIEWS_FILE, reviews)
    save(MIXTAPES_FILE, mixtapes)
    idx = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "source": "https://aquariumdrunkard.com",
        "post_count": len(posts),
        "review_count": len(reviews),
        "mixtape_count": len(mixtapes),
        "gated_count": sum(1 for p in posts.values() if p.get("gated")),
        "by_type": {t: sum(1 for p in posts.values() if p.get("post_type") == t)
                    for t in ("review", "mixtape", "interview", "lagniappe", "podcast", "feature")},
    }
    save(INDEX_FILE, idx)

    print(f"\n  ── summary ──")
    print(f"  posts:    {len(posts)}  (+{added} this run)")
    print(f"  reviews:  {len(reviews)} (with direct Spotify album links — ready to play)")
    print(f"  mixtapes: {len(mixtapes)} (paywalled tracklists, public metadata)")
    print(f"  gated:    {idx['gated_count']}")
    print(f"  by type:  {idx['by_type']}")
    print(f"\n  files in {os.path.relpath(OUT, REPO)}/")
    print(f"  per-post markdown ready for LLM context in {os.path.relpath(CONTEXT_DIR, REPO)}/")


def scrape_carousel():
    """Scrape the homepage's 'On The Turntable' carousel — the only place AD
    embeds Spotify album URLs alongside artist/album/cover. Returns a list of
    {artist, album, spotify_album, spotify_id, apple_url, tidal_url, cover_url, blurb}."""
    html = fetch(BASE + "/")
    if not html: return []
    # Each carousel card looks roughly like:
    #   <h3>Artist :: Album</h3>
    #   <p>blurb…</p>
    #   <a href="https://open.spotify.com/album/ID">Spotify</a> <a href="apple…">…</a>
    # We slice the doc on each Spotify album link, then look backwards for the title.
    cards = []
    # Find every Spotify album URL in the document (homepage shows the carousel ones first)
    for m in re.finditer(r'href="(https://open\.spotify\.com/album/([a-zA-Z0-9]+))"', html):
        spot_url, sid = m.group(1), m.group(2)
        # Look BACK ~2000 chars for the nearest h3 title — that's the album/artist line
        window = html[max(0, m.start() - 2400):m.start()]
        h3 = re.findall(r'<h3[^>]*>(.*?)</h3>', window, re.S)
        title = strip_tags(h3[-1]) if h3 else None
        artist, album = parse_artist_album(title) if title else (None, None)
        # nearest <img alt= ...> within the window for the cover
        cov_match = re.search(r'<img[^>]+src="(https://aquariumdrunkard\.com/[^"]+\.(?:jpg|jpeg|png|webp))"', window[::-1])
        # the regex on reversed html is ugly; do forward scan instead
        cover = None
        for im in re.finditer(r'<img[^>]+src="(https://aquariumdrunkard\.com/[^"]+\.(?:jpg|jpeg|png|webp))"', window):
            cover = im.group(1)
        # blurb = the longest <p> in the window
        blurb = ""
        for pm in re.finditer(r'<p[^>]*>(.*?)</p>', window, re.S):
            txt = strip_tags(pm.group(1))
            if len(txt) > len(blurb): blurb = txt
        # nearest apple/tidal links AFTER the spotify one (they cluster together)
        nxt = html[m.start():m.start() + 1500]
        apple = re.search(r'https://music\.apple\.com/[^\s"\'<>]+', nxt)
        tidal = re.search(r'https://tidal\.com/[^\s"\'<>]+', nxt)
        cards.append({
            "spotify_id": sid, "spotify_album": spot_url,
            "artist": artist, "album": album, "title": title,
            "apple_url": apple.group(0) if apple else None,
            "tidal_url": tidal.group(0) if tidal else None,
            "cover_url": cover, "blurb": (blurb or "")[:400],
            "scraped_at": datetime.utcnow().isoformat() + "Z",
        })
    # de-dupe by spotify_id, preserve homepage order
    seen, out = set(), []
    for c in cards:
        if c["spotify_id"] in seen: continue
        seen.add(c["spotify_id"]); out.append(c)
    save(CAROUSEL_FILE, out)
    print(f"  carousel → {len(out)} current Spotify-linked picks  ({CAROUSEL_FILE})")
    for c in out:
        print(f"     · {c['artist']} — {c['album']}  [{c['spotify_id']}]")
    return out


def main():
    global COOKIE_HEADER
    ap = argparse.ArgumentParser(description="Scrape Aquarium Drunkard into a knowledge base.")
    for k in SOURCES: ap.add_argument(f"--{k}", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pages", type=int, default=3, help="pages of listings to walk per source (default 3)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-scrape posts already saved (gets richer fields after a schema upgrade)")
    ap.add_argument("--cookies-file", default=None,
                    help="path to a text file containing your AD session Cookie header (one line)")
    ap.add_argument("--carousel", action="store_true",
                    help="scrape the homepage 'On The Turntable' carousel for current Spotify-linked picks")
    args = ap.parse_args()
    if args.cookies_file:
        try:
            COOKIE_HEADER = open(args.cookies_file, encoding="utf-8").read().strip()
            # quick auth sanity check against a known gated post
            print("  Verifying AD login cookie …")
            sample = fetch(BASE + "/2025/01/21/lamentations-twenty-two-songs-about-john-coltrane/")
            if sample and is_gated(sample):
                print("  ⚠ cookie loaded BUT the page is still gated — cookie may be wrong/expired.")
                print("    Re-copy the Cookie header while logged in and try again.")
            elif sample:
                print("  ✓ cookie works — paywall lifted.")
            else:
                print("  ⚠ couldn't fetch a sample page to verify auth.")
        except FileNotFoundError:
            ap.error(f"cookies file not found: {args.cookies_file}")
    chosen = list(SOURCES.keys()) if args.all else [k for k in SOURCES if getattr(args, k)]
    if args.carousel:
        scrape_carousel()
    if not chosen and not args.carousel:
        ap.error("pick one or more of: " + ", ".join("--" + k for k in SOURCES) + ", --all, or --carousel")
    if chosen:
        run(chosen, args.pages, args.refresh)


if __name__ == "__main__":
    main()
