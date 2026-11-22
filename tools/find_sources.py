#!/usr/bin/env python3
"""Daily source hunter for mango2952/iptv-api fork.

Searches GitHub for recently-updated IPTV playlist repos, extracts playlist
URLs their READMEs publish, verifies each URL really returns a playlist
(#EXTM3U / #EXTINF>=20, or txt genre format), and appends up to MAX_NEW new
ones to config/subscribe.txt (before the [WHITELIST] section).
Rules are mechanical on purpose: no IPv6-only lists, no demos, no dupes.
"""
import os, re, sys, json, urllib.request, urllib.parse, datetime

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
SUBSCRIBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "subscribe.txt")
MAX_NEW = 5
QUERIES = ["iptv m3u", "iptv playlist m3u", "直播源 m3u", "IPTV直播源", "iptv m3u8 playlist"]
URL_RE = re.compile(r'https?://[^\s\)\]\}"\'<>|]+')
BAD = ("example", "demo", "localhost", "您的", "your-", "username", "placeholder")

def http_get(url, timeout=20, limit=200000, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "source-hunter/1.0",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN and "api.github.com" in url else {}),
        **({"Accept": "application/vnd.github.raw+json"} if raw else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(limit).decode("utf-8", "ignore")

def api(path):
    s, t = http_get("https://api.github.com" + path)
    return json.loads(t)

def verify_playlist(url):
    try:
        s, head = http_get(url, timeout=15, limit=65536)
    except Exception as e:
        return False, f"fetch fail {e.__class__.__name__}"
    if "#EXTM3U" in head and head.count("#EXTINF") >= 20:
        return True, f"m3u ok, EXTINF={head.count('#EXTINF')}"
    if "#genre#" in head and ",http" in head:
        return True, "txt genre ok"
    return False, "not a playlist"

def main():
    dry = "--dry-run" in sys.argv
    with open(SUBSCRIBE, encoding="utf-8") as f:
        sub = f.read()
    have = set(re.findall(r'https?://\S+', sub))
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    repos = []
    for q in QUERIES:
        try:
            r = api("/search/repositories?q=" + urllib.parse.quote(f"{q} pushed:>{since}") + "&sort=updated&per_page=15")
        except Exception as e:
            print("search fail:", q, e); continue
        for it in r.get("items", []):
            fn = it["full_name"]
            if fn not in repos and fn.lower() != "mango2952/iptv-api":
                repos.append(fn)
    print(f"candidate repos: {len(repos)}")
    added = []
    added_names = set()
    for fn in repos:
        if len(added) >= MAX_NEW: break
        try:
            s, readme = http_get(f"https://api.github.com/repos/{fn}/readme", raw=True)
        except Exception:
            continue
        cands = []
        for u in URL_RE.findall(readme):
            u = u.rstrip('.,;`~_')
            low = u.lower()
            if not any(k in low for k in (".m3u", ".m3u8")): continue
            if "ipv6" in low or any(b in low for b in BAD): continue
            pr = urllib.parse.urlparse(u)
            if not pr.path.lower().endswith((".m3u", ".m3u8", ".txt")): continue
            if any(k in pr.query.lower() for k in ("token", "key=", "auth", "sign")): continue
            if "logo" in low or u in have or u in cands: continue
            cands.append(u)
        for u in cands:
            if len(added) >= MAX_NEW: break
            base = urllib.parse.urlparse(u).path.rsplit("/", 1)[-1]
            if base in added_names:
                print("skip", fn, u, "- same file already added via another mirror"); continue
            ok, why = verify_playlist(u)
            print(("ADD " if ok else "skip"), fn, u, "-", why)
            if ok:
                added.append(u); have.add(u); added_names.add(base)
    if added and not dry:
        marker = "\n[WHITELIST]"
        block = "".join(u + "\n" for u in added)
        if marker in sub:
            sub = sub.replace(marker, "\n" + block.rstrip("\n") + marker, 1)
        else:
            sub = sub.rstrip("\n") + "\n" + block
        with open(SUBSCRIBE, "w", encoding="utf-8") as f:
            f.write(sub)
    print(f"new sources: {len(added)}")
    for u in added: print("  +", u)
    # signal for the workflow step
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"added={len(added)}\n")

if __name__ == "__main__":
    main()
