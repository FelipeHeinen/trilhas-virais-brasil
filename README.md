# Trilhas Virais Brasil (fork BR do trending-audio-tracker)

Painel com os áudios e músicas em alta no TikTok **no Brasil** (fonte: tokchart.com/pt-br), atualizado a cada 4 horas, mais notícias de trends do Google Notícias Brasil.

---

Original: Daily-refreshed dashboard of trending TikTok sounds, with a one-click "Find on Instagram" search per sound. Runs free on GitHub Actions + GitHub Pages.

## What it does

1. **Scrapes** tokchart.com Brazil pages (`/pt-br/audios-do-tiktok` and `/pt-br/musicas-do-tiktok`).
2. **Stores** results as JSON in `data/trending.json`.
3. **Publishes** a simple dashboard to GitHub Pages reading that JSON.
4. **Cross-references** to Instagram via a Google search button (no IG scraping needed — just opens a pre-built search).

## Setup

1. Create a new repo on GitHub and push this folder to it.
2. In repo Settings → Actions → General → Workflow permissions, enable **Read and write permissions** (so the cron job can commit the refreshed JSON).
3. In repo Settings → Pages, set Source = "Deploy from a branch", Branch = `main`, Folder = `/docs`.
4. In Actions tab, run the **Scrape TikTok Trending Sounds (BR)** workflow manually once to populate data.
5. Visit `https://<your-username>.github.io/<repo>/` to see the dashboard.

The cron runs daily at 14:00 UTC. You can adjust in `.github/workflows/scrape.yml`.

## Local dev

```bash
pip install -r scripts/requirements.txt
python -m playwright install chromium
python scripts/scrape_tiktok.py
python scripts/build_dashboard.py
open docs/index.html
```

## Files

- `scripts/scrape_tiktok.py` — Playwright scraper, intercepts TikTok's internal JSON API
- `scripts/build_dashboard.py` — copies data into `docs/`
- `docs/index.html` — dashboard (served by GitHub Pages)
- `.github/workflows/scrape.yml` — daily cron + auto-commit

## Cost

$0/month. GitHub Actions free tier (2000 min/mo) is more than enough — each run takes ~1 min.

## Caveats

- TikTok occasionally changes their internal API shape. If a run starts returning 0 sounds, check the response shape in the scraper's `normalize()` function and adjust field names.
- The "Find on IG" button uses Google search, which works ~60–70% of the time. Some TikTok sounds don't have an IG counterpart, or have a different title.
