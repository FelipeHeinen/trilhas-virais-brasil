"""
Scrape Brazil (BR) trending TikTok sounds and songs from tokchart.com.

Why tokchart and not TikTok Creative Center directly: TikTok now requires
ad-account login on the Creative Center API (returns 40101 "no permission").
tokchart.com publishes the same data on plain HTML pages with no auth.

Output: data/trending.json
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
OUT = ROOT / "data" / "trending.json"
DEBUG_DIR = ROOT / "debug"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Each "lens" = a tokchart page for Brazil. period_days is kept for
# back-compat with the dashboard pills.
REGION = "BR"
LENSES = [
    {"period_days": 7, "label": "Áudios em alta no Brasil", "url": "https://tokchart.com/pt-br/audios-do-tiktok"},
    {"period_days": 30, "label": "Músicas em alta no Brasil", "url": "https://tokchart.com/pt-br/musicas-do-tiktok"},
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _num(txt: str) -> int:
    """'+12,100' -> 12100, '117K' -> 117000, '1.2M' -> 1200000."""
    t = txt.strip().lstrip("+").replace(",", "")
    m = re.match(r"([\d.]+)\s*([KMB]?)", t, re.I)
    if not m:
        return 0
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[m.group(2).upper()]
    return int(float(m.group(1)) * mult)


def _text(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html)).strip()


def parse(html: str, period: int) -> list[dict]:
    """
    tokchart (2026 layout) renders each chart as a table:

      <tbody><tr ...>
        <td class="ch-c-rk"><span class="ch-rkn">{rank}</span>...</td>
        <td><div class="ui-sndcell"><img src="{cover}">
              <a class="ui-t ..." href="https://www.tiktok.com/music/-{id}">{title}</a>  (or <div class="ui-t">)
              <div class="ui-a ...">{artist}</div></td>
        [<td class="ch-genre">{genre}</td>]          (songs page)
        <td class="ui-r ui-num">+{videos/day}</td>  <td class="ui-r ui-num">{videos}</td>  (sounds page)

    Numbers behind tokchart's paywall (songs page, class ui-blv) are skipped.
    """
    m_body = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not m_body:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", m_body.group(1), re.S):
        m_title = re.search(r'class="ui-t\b[^"]*"[^>]*>(.*?)</(?:a|div)>', row, re.S)
        if not m_title:
            continue
        title = _text(m_title.group(1))
        m_artist = re.search(r'class="ui-a\b[^"]*"[^>]*>(.*?)</div>', row, re.S)
        artist = _text(m_artist.group(1)) if m_artist else ""
        m_rank = re.search(r'class="ch-rkn"[^>]*>\s*(\d+)', row)
        m_cover = re.search(r'<img[^>]+src="([^"]+)"', row)
        m_genre = re.search(r'class="ch-genre"[^>]*>(.*?)</td>', row, re.S)
        m_tt = re.search(r'href="(https://www\.tiktok\.com/music/[^"]+)"', row)
        clip_id = re.search(r"-(\d+)$", m_tt.group(1)).group(1) if m_tt else ""
        # Public numeric cells only (paywalled ones use class ui-blv inside a button)
        nums = [_text(c) for c in re.findall(r'<td class="ui-r ui-num"[^>]*>(.*?)</td>', row, re.S)]

        key = clip_id or f"{title}|{artist}"
        if not title or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "rank": int(m_rank.group(1)) if m_rank else len(out) + 1,
                "title": title,
                "artist": artist,
                "genre": _text(m_genre.group(1)) if m_genre else "",
                "clip_id": key,
                "tiktok_uses": _num(nums[1]) if len(nums) > 1 else 0,
                "tiktok_uses_24h": _num(nums[0]) if nums else 0,
                "tiktok_link": m_tt.group(1) if m_tt else
                    "https://www.tiktok.com/search?q=" + urllib.parse.quote(f"{title} {artist}"),
                "cover": m_cover.group(1) if m_cover else "",
                "period_days": period,
            }
        )
    return out


def main() -> int:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    notes: list[dict] = []

    for lens in LENSES:
        print(f"[scrape] {lens['label']} ← {lens['url']}", flush=True)
        try:
            html = fetch(lens["url"])
            (DEBUG_DIR / f"raw_{lens['period_days']}.html").write_text(html[:500_000])
            rows = parse(html, lens["period_days"])
        except Exception as e:
            print(f"  error: {e}", flush=True)
            notes.append({"lens": lens["label"], "error": str(e)})
            rows = []
        print(f"  {len(rows)} rows", flush=True)
        notes.append({"lens": lens["label"], "rows": len(rows)})
        all_rows.extend(rows)

    (DEBUG_DIR / "summary.json").write_text(
        json.dumps({"runs": notes, "total_rows": len(all_rows)}, indent=2)
    )

    payload = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "region": REGION,
        "source": "tokchart.com",
        "count": len(all_rows),
        "lenses": [{"period_days": l["period_days"], "label": l["label"]} for l in LENSES],
        "sounds": all_rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[done] wrote {len(all_rows)} sounds → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
