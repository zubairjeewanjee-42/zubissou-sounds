#!/usr/bin/env python3
"""
Zubissou Sounds — Clone any public Spotify playlist into your library.

Reads the source playlist via the public Spotify EMBED page (no auth, no quota,
no dev-mode 403s). Writes to your library via the normal Spotify Web API (POST
to /me/playlists + /playlists/{id}/tracks — these work because the new playlist
is yours).

USAGE
    python3 scripts/clone_playlist.py <playlist_url> [--name "My Name"] [--public]

    # Default — uses the original playlist name with a “(cloned)” suffix
    python3 scripts/clone_playlist.py https://open.spotify.com/playlist/37i9dQZF1EIUQ4MIeBpMjC

    # Custom name
    python3 scripts/clone_playlist.py <url> --name "Zubair Works"

    # Make it public (default is private)
    python3 scripts/clone_playlist.py <url> --public

Reuses the OAuth from build_playlists.py — same one-time PKCE login.
"""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_playlists import Spotify
from scrape_spotify_curator import _extract_playlist_id, fetch_via_embed


def main():
    ap = argparse.ArgumentParser(description="Clone a public Spotify playlist into your library.")
    ap.add_argument("url", help="Spotify playlist URL or ID")
    ap.add_argument("--name", default=None, help="override the cloned playlist's name")
    ap.add_argument("--public", action="store_true", help="make the clone public (default: private)")
    ap.add_argument("-v", "--verbose", action="store_true", help="print embed diagnostics if extraction fails")
    args = ap.parse_args()

    pid = _extract_playlist_id(args.url)
    print(f"\n  source playlist: {pid}")

    print(f"  reading tracks via public embed (no API quota) …")
    meta, tracks = fetch_via_embed(pid, debug=args.verbose)
    if not tracks:
        sys.exit("  ! couldn't extract tracks from the embed. Is the URL right? Is the playlist public?")
    print(f"  ✓ got {len(tracks)} tracks")
    if meta and meta.get("name"):
        print(f"    source name: {meta['name']}")

    src_name = (meta or {}).get("name") or "Playlist"
    name = args.name or f"{src_name} (cloned)"
    desc = (meta or {}).get("description") or ""
    desc = (desc + " · cloned by Zubissou Sounds").strip()[:300]

    uris = [t.get("spotify_uri") for t in tracks if t.get("spotify_uri")]
    if not uris:
        sys.exit("  ! none of the extracted tracks had spotify URIs. The embed JSON may have changed shape.")
    print(f"  · {len(uris)} of {len(tracks)} tracks resolved to URIs")

    sp = Spotify()
    print(f"  logged in as {sp.me.get('display_name') or sp.me.get('id')}")

    print(f"  creating playlist “{name}” …")
    pl = sp._request("POST", f"/users/{sp.me['id']}/playlists",
                     {"name": name, "description": desc, "public": bool(args.public)})
    print(f"  ✓ created · {pl.get('external_urls',{}).get('spotify', '(no url)')}")

    # add tracks in chunks of 100
    for i in range(0, len(uris), 100):
        chunk = uris[i:i+100]
        sp._request("POST", f"/playlists/{pl['id']}/tracks", {"uris": chunk})
        print(f"     · added {min(i+100, len(uris))}/{len(uris)}")

    print(f"\n  ✓ cloned · open Spotify and look for: {name}")
    print(f"    you can also drop those track URIs into your knob pool — they're now in your library so")
    print(f"    individual tracks can be picked by the dashboard's filter engine for other playlists.")


if __name__ == "__main__":
    main()
