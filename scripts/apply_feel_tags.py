#!/usr/bin/env python3
"""
Apply curated FEEL tags (mood / energy / density / head-body) to rich/albums.json.

These are hand-judged 0–100 values — Claude's ear, album by album — for the four
knob axes that have no metadata source:
    mood      0 desolate/melancholy ............. 100 euphoric
    energy    0 silent/ambient ................... 100 driving/frantic
    density   0 sparse ............................ 100 wall-of-sound
    headbody  0 cerebral .......................... 100 groove/body

Keyed by (source, rank) so it matches records exactly regardless of title text.
Edit any value here and re-run; it's the source of truth for feel. Re-running
only sets these four knobs (everything else untouched).

    python3 scripts/apply_feel_tags.py
"""
import json, os

RICH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "assets", "data", "rich", "albums.json")

# (mood, energy, density, headbody)
CANON = {
 1:(62,50,48,58),  2:(62,50,48,58),  3:(45,48,55,45),  4:(60,42,62,40),  5:(68,55,60,52),
 6:(30,40,55,35),  7:(62,48,45,50),  8:(50,38,40,45),  9:(38,55,62,55),  10:(28,22,35,25),
 11:(40,70,65,42), 12:(40,15,25,20), 13:(48,50,55,72), 14:(32,38,55,38), 15:(65,72,72,80),
 16:(68,55,55,70), 17:(58,42,40,55), 18:(60,48,50,60), 19:(55,40,45,50), 20:(45,12,22,18),
 21:(42,12,20,18), 22:(30,12,30,18), 23:(48,55,50,68), 24:(66,55,58,52), 25:(60,48,50,58),
 26:(35,40,38,45), 27:(55,55,55,60), 28:(45,80,82,55), 29:(60,52,55,55), 30:(56,52,62,48),
 31:(55,68,68,62), 32:(52,45,48,62), 33:(50,55,52,65), 34:(45,50,95,40), 35:(48,58,55,50),
 36:(42,42,58,40), 37:(28,35,45,45), 38:(55,74,58,62), 39:(33,40,52,38), 40:(38,52,58,42),
 41:(65,80,60,84), 42:(55,55,50,65), 43:(48,55,50,68), 44:(65,50,45,62), 45:(48,52,45,52),
 46:(55,62,52,72), 47:(45,55,55,72), 48:(45,52,52,70), 49:(58,48,62,42), 50:(68,72,65,82),
 51:(55,64,66,50), 52:(55,55,55,65), 53:(52,50,55,68), 54:(66,52,50,70), 55:(40,10,30,15),
 56:(32,45,55,50), 57:(42,38,40,45), 58:(70,68,48,76), 59:(45,84,80,55), 60:(68,70,58,90),
 61:(40,40,25,50), 62:(48,40,30,48), 63:(60,70,66,86), 64:(60,76,66,68), 65:(20,45,50,40),
 66:(55,42,42,62), 67:(58,48,50,58), 68:(42,32,45,48), 69:(55,58,55,72), 70:(62,72,68,82),
 71:(70,58,55,62), 72:(50,30,30,40), 73:(45,70,66,55), 74:(52,44,55,60), 75:(48,45,50,62),
 76:(55,55,50,60), 77:(35,58,62,55), 78:(58,18,24,30), 79:(55,70,42,62), 80:(45,58,52,50),
 81:(58,52,50,72), 82:(68,48,45,58), 83:(50,48,48,62), 84:(34,60,76,55), 85:(50,40,55,24),
 86:(40,82,86,40), 87:(52,62,72,34), 88:(55,26,40,24), 89:(45,16,22,22), 90:(48,35,40,30),
 91:(45,32,38,48), 92:(55,62,60,86), 93:(62,58,58,80), 94:(55,44,52,72), 95:(55,54,54,76),
}
BIRTH = {
 1:(48,55,45,52),  2:(55,66,50,82),  3:(60,70,55,66),  4:(66,72,64,82),  5:(70,74,58,84),
 6:(50,42,72,30),  7:(42,12,28,18),  8:(52,80,46,62),  9:(55,68,48,58),  10:(30,60,58,45),
 11:(48,38,46,42), 12:(32,42,50,35), 13:(55,42,46,56), 14:(55,62,60,62), 15:(58,48,45,50),
 16:(38,38,56,30), 17:(50,56,50,60), 18:(45,42,48,40), 19:(42,30,40,38), 20:(34,30,46,30),
}


def main():
    recs = json.load(open(RICH, encoding="utf-8"))
    n = 0
    for r in recs:
        rank = r["knobs"].get("familiarity")
        table = CANON if r.get("source") == "canon" else (BIRTH if r.get("source") == "birthyear" else None)
        if not table or rank not in table:
            continue
        mood, energy, density, headbody = table[rank]
        r["knobs"]["mood"] = mood
        r["knobs"]["energy"] = energy
        r["knobs"]["density"] = density
        r["knobs"]["headbody"] = headbody
        prov = r.setdefault("enrichment", {"status": "stub", "sources": [], "last_enriched": None})
        if "curated-feel" not in prov["sources"]:
            prov["sources"].append("curated-feel")
        n += 1
    json.dump(recs, open(RICH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  applied feel tags to {n} albums → assets/data/rich/albums.json")
    # quick coverage
    full = sum(1 for r in recs if all(r["knobs"].get(k) is not None
               for k in ("mood", "energy", "density", "headbody")))
    print(f"  {full}/{len(recs)} albums now have all four feel knobs")


if __name__ == "__main__":
    main()
