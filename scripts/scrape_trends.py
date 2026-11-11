"""
Aggregate TikTok / Instagram creator trend reporting from free sources.

Goal: surface "right now this video format is going viral" content that a
content agency can act on — POV formats, challenges, transitions, viral
audios, video patterns. NOT general news.

Sources:
  - Google News RSS — targeted queries scoped to last 7 days
  - Reddit creator subs — top of the week, filtered for trend keywords
  - tokchart "fastest growing sounds" — already covered in the Sounds tab
    so no need to repeat here.

Output: data/trends.json
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "trends.json"

UA = "Mozilla/5.0 (compatible; trending-audio-tracker/1.0)"

# Each section combines several Google News queries.
NEWS_SECTIONS = [
    {
        "key": "tiktok_formats",
        "label": "Formatos de vídeo em alta no TikTok",
        "queries": [
            "trend tiktok viral",
            "trend do tiktok",
            "desafio viral tiktok",
        ],
    },
    {
        "key": "reels_formats",
        "label": "Formatos de Reels em alta",
        "queries": [
            "trend reels instagram",
            "reels viral instagram",
            "trend instagram 2026",
        ],
    },
    {
        "key": "viral_sounds",
        "label": "Músicas e áudios virais",
        "queries": [
            "música viral tiktok",
            "áudio viral tiktok",
            "hit do tiktok",
        ],
    },
]

# Creator-focused subreddits, keyword-filtered down to trend posts.
CREATOR_SUBS = [
    "SocialMediaMarketing",
    "InfluencerMarketing",
    "InstagramMarketing",
    "Instagram",
    "TikTok",
    "NewTubers",
    "ContentCreators",
]
TREND_KEYWORDS = (
    "trend", "viral", "format", "challenge", "pov", "reel ", "reels",
    "sound", "audio", "transition", "hack", "blow up", "blew up",
    "going viral", "what's working", "why is everyone",
)


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_json(url: str, timeout: int = 30):
    return json.loads(fetch(url, timeout))


# ---------- Google News RSS ----------
def google_news(query: str) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query + " when:7d")
        + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )
    xml = fetch(url)
    items: list[dict] = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        block = m.group(1)
        title = _xml(block, "title")
        link = _xml(block, "link")
        source = _xml(block, "source")
        pub = _xml(block, "pubDate")
        desc = _xml(block, "description")
        thumb = ""
        # Source links inside description sometimes carry img tags
        img = re.search(r'<img[^>]+src="([^"]+)"', desc)
        if img:
            thumb = img.group(1)

        # Strip "- Publisher" suffix Google News appends
        cleaned_title = re.sub(r"\s*-\s*[^-]{2,40}$", "", title).strip()

        items.append(
            {
                "title": cleaned_title,
                "subtitle": "",
                "url": link,
                "source": source,
                "thumbnail": thumb,
                "meta": _short_when(pub),
                "_pub": pub,
            }
        )
    return items


def _xml(s: str, tag: str) -> str:
    m = re.search(rf"<{tag}(?:\s[^>]*)?>(.*?)</{tag}>", s, re.S)
    if not m:
        return ""
    raw = m.group(1).strip()
    cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", raw, re.S)
    return unescape(cdata.group(1) if cdata else raw).strip()


def _short_when(rfc822: str) -> str:
    if not rfc822:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(rfc822)
        delta = datetime.now(timezone.utc) - dt
        h = int(delta.total_seconds() // 3600)
        if h < 1:
            return "just now"
        if h < 24:
            return f"{h}h ago"
        return f"{h // 24}d ago"
    except Exception:
        return ""


DENY_PATTERNS = (
    "car insurance",
    "credit card",
    "trade-offs",
    "best free ai tool",
    "best ai tools",
    "essential breakdown",
    "honest assessment",
    "auto insurance",
    "weighing the",
    "today's landscape",
    "complete guide",
)


def news_section(label: str, queries: list[str]) -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[dict] = []
    for q in queries:
        try:
            for it in google_news(q):
                if it["url"] in seen_urls:
                    continue
                tkey = it["title"].lower()[:80]
                if tkey in seen_titles:
                    continue
                if any(d in it["title"].lower() for d in DENY_PATTERNS):
                    continue
                seen_urls.add(it["url"])
                seen_titles.add(tkey)
                out.append(it)
        except Exception as e:
            print(f"  warn: query {q!r} failed: {e}", flush=True)
    # Sort by parsed pubDate, newest first
    from email.utils import parsedate_to_datetime

    def key(x):
        try:
            return parsedate_to_datetime(x["_pub"]).timestamp()
        except Exception:
            return 0

    out.sort(key=key, reverse=True)
    for x in out:
        x.pop("_pub", None)
    return out[:18]


# ---------- Reddit (filtered to trend talk) ----------
def reddit_creators() -> list[dict]:
    url = (
        "https://www.reddit.com/r/"
        + "+".join(CREATOR_SUBS)
        + "/top.json?t=week&limit=80"
    )
    body = fetch_json(url)
    items: list[dict] = []
    for c in body.get("data", {}).get("children", []):
        p = c.get("data", {})
        if p.get("stickied"):
            continue
        title = (p.get("title") or "").strip()
        if not title:
            continue
        title_l = title.lower()
        if not any(k in title_l for k in TREND_KEYWORDS):
            continue

        thumb = p.get("thumbnail") or ""
        if thumb in ("self", "default", "nsfw", "spoiler", ""):
            try:
                thumb = (
                    p.get("preview", {})
                    .get("images", [{}])[0]
                    .get("source", {})
                    .get("url", "")
                    .replace("&amp;", "&")
                )
            except Exception:
                thumb = ""

        items.append(
            {
                "title": title,
                "subtitle": (p.get("selftext") or "")[:140].replace("\n", " ").strip(),
                "url": "https://www.reddit.com" + (p.get("permalink") or ""),
                "source": "r/" + (p.get("subreddit") or ""),
                "thumbnail": thumb,
                "meta": _short_int(p.get("ups", 0)) + " upvotes",
            }
        )
    return items[:15]


def _short_int(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# ---------- Main ----------
def main() -> int:
    sections: list[dict] = []
    notes: list[dict] = []

    for spec in NEWS_SECTIONS:
        try:
            items = news_section(spec["label"], spec["queries"])
            sections.append({"key": spec["key"], "label": spec["label"], "items": items})
            notes.append({"key": spec["key"], "count": len(items)})
            print(f"[trends] {spec['label']}: {len(items)} items", flush=True)
        except Exception as e:
            notes.append({"key": spec["key"], "error": str(e)})
            print(f"[trends] {spec['label']}: ERROR {e}", flush=True)

    try:
        items = reddit_creators()
        sections.append(
            {
                "key": "creator_chatter",
                "label": "O que os criadores estão comentando (Reddit, em inglês)",
                "items": items,
            }
        )
        notes.append({"key": "creator_chatter", "count": len(items)})
        print(f"[trends] creator chatter: {len(items)} items", flush=True)
    except Exception as e:
        notes.append({"key": "creator_chatter", "error": str(e)})
        print(f"[trends] creator chatter: ERROR {e}", flush=True)

    payload = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "_notes": notes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    total = sum(len(s["items"]) for s in sections)
    print(f"[done] wrote {total} items in {len(sections)} sections → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
