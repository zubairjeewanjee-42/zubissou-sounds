#!/usr/bin/env python3
"""
Zubissou Sounds — LLM feel-tagger for the rich catalog.

Calls the Claude API to estimate the four "feel" knob values
(mood / energy / density / headbody, 0-100) for every record that doesn't have
them yet. Lights up the MOOD/ENERGY/DENSITY/HEAD·BODY knobs across the *whole*
catalog (8k+ tracks), not just the 115 canon albums.

Reads + writes the rich files in place:
    assets/data/rich/albums.json     (115 canon — most already tagged by ear)
    assets/data/rich/songs.json
    assets/data/rich/catalog.json    (6,745 XRAY tracks)
    assets/data/rich/ad_picks.json   (AD carousel)

Resumable + incremental save. Re-runnable — skips records already tagged.

Setup (one time):
    export ANTHROPIC_API_KEY='your_key_here'

Usage:
    python3 scripts/llm_tag_catalog.py --source albums  --dry-run    # estimate cost
    python3 scripts/llm_tag_catalog.py --source albums  --limit 100  # tag the first 100
    python3 scripts/llm_tag_catalog.py --source catalog               # full run

Costs: ~$0.005 per batch of 30 tracks with Sonnet, ~$0.0015 with Haiku.
Full XRAY catalog (~6,745 tracks) ≈ 225 batches ≈ $1.15 on Sonnet, $0.35 on Haiku.

Stdlib only.
"""
import argparse, json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RICH = os.path.join(REPO, "assets", "data", "rich")

API = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"
BATCH = 30
PAUSE = 0.4
COST_PER_BATCH = {"claude-sonnet-4-6": 0.005, "claude-haiku-4-5-20251001": 0.0015,
                  "claude-opus-4-6": 0.025}

PROMPT = """You are a deep-listening music critic with knowledge of every era, genre, and scene. For each track below, estimate four "feel" values on 0-100 scales — give your best estimate even if the specific track is obscure (lean on the artist's typical sound + album/genre context).

- mood: 0 desolate/melancholy ............. 100 euphoric
- energy: 0 silent/ambient ................. 100 driving/frantic
- density: 0 sparse ........................ 100 wall-of-sound
- headbody: 0 cerebral ..................... 100 groove/body

Respond with ONLY a JSON array of objects {{"id": ..., "mood": ..., "energy": ..., "density": ..., "headbody": ...}}. No commentary, no markdown fences.

Tracks:
{lines}"""


# --------------------------------------------------------------------------- #
def needs_feel(rec):
    k = rec.get("knobs") or {}
    return any(k.get(x) is None for x in ("mood", "energy", "density", "headbody"))


def line_for(rec, idx):
    artist = rec.get("artist") or "?"
    title  = rec.get("title") or rec.get("album") or "?"
    album  = rec.get("album") or ""
    extra  = f" ({album})" if album and album != title else ""
    return f'{idx+1}. id="r{idx}" {artist} - {title}{extra}'


def call_api(records, key, model):
    lines = "\n".join(line_for(r, i) for i, r in enumerate(records))
    body = {
        "model": model,
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": PROMPT.format(lines=lines)}],
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode())
    text = (data.get("content") or [{}])[0].get("text", "")
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("no JSON array in response: " + text[:200])
    return json.loads(m.group(0))


def apply_tags(records, results):
    by_id = {r.get("id"): r for r in results if isinstance(r, dict)}
    updated = 0
    for i, rec in enumerate(records):
        tags = by_id.get(f"r{i}")
        if not tags: continue
        kn = rec.setdefault("knobs", {})
        try:
            kn["mood"]     = max(0, min(100, int(tags.get("mood",     50))))
            kn["energy"]   = max(0, min(100, int(tags.get("energy",   50))))
            kn["density"]  = max(0, min(100, int(tags.get("density",  50))))
            kn["headbody"] = max(0, min(100, int(tags.get("headbody", 50))))
        except (TypeError, ValueError):
            continue
        prov = rec.setdefault("enrichment", {"status": "stub", "sources": [], "last_enriched": None})
        if "llm-claude" not in (prov.get("sources") or []):
            prov.setdefault("sources", []).append("llm-claude")
        prov["last_enriched"] = datetime.utcnow().isoformat() + "Z"
        prov["status"] = "complete"
        updated += 1
    return updated


def main():
    ap = argparse.ArgumentParser(description="LLM-tag mood/energy/density/headbody.")
    ap.add_argument("--source", choices=["albums", "songs", "catalog", "ad_picks"], required=True)
    ap.add_argument("--limit", type=int, default=0, help="cap records this run (0 = all)")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="any Anthropic model string (default: " + DEFAULT_MODEL + ")")
    ap.add_argument("--dry-run", action="store_true", help="just print cost estimate")
    args = ap.parse_args()

    path = os.path.join(RICH, f"{args.source}.json")
    if not os.path.exists(path):
        sys.exit(f"  ! {path} not found — run build_rich_db.py first.")

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key and not args.dry_run:
        sys.exit("  ! set ANTHROPIC_API_KEY (export ANTHROPIC_API_KEY='...').")

    recs = json.load(open(path, encoding="utf-8"))
    todo = [r for r in recs if needs_feel(r)]
    n_batches = (len(todo) + BATCH - 1) // BATCH
    cap = args.limit if args.limit else len(todo)
    cap_batches = (min(cap, len(todo)) + BATCH - 1) // BATCH
    cost = cap_batches * COST_PER_BATCH.get(args.model, COST_PER_BATCH[DEFAULT_MODEL])

    print(f"  source:    {args.source}.json")
    print(f"  total:     {len(recs)} records")
    print(f"  need feel: {len(todo)}")
    print(f"  model:     {args.model}")
    print(f"  this run:  {min(cap, len(todo))} records · {cap_batches} batches · ~${cost:.3f}")
    if args.dry_run: return

    done = 0
    for start in range(0, len(todo), BATCH):
        if done >= cap: break
        batch = todo[start:start + BATCH]
        try:
            results = call_api(batch, key, args.model)
        except urllib.error.HTTPError as e:
            print(f"  ! HTTP {e.code} — {e.read().decode()[:200]}"); time.sleep(5); continue
        except Exception as e:
            print(f"  ! batch error: {e}"); time.sleep(3); continue
        n = apply_tags(batch, results)
        done += len(batch)
        # save in place after every batch so a crash never loses progress
        json.dump(recs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"     ✓ batch {start//BATCH + 1}/{cap_batches} · +{n} tagged  (total: {done})")
        time.sleep(PAUSE)

    full = sum(1 for r in recs if not needs_feel(r))
    print(f"\n  done. {full}/{len(recs)} records now have all four feel knobs.")
    print(f"  re-run anytime — already-tagged records are skipped.")


if __name__ == "__main__":
    main()
