"""Copy generated JSON into docs/ so GitHub Pages can serve it."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)

for name in ("trending.json", "trends.json"):
    src = ROOT / "data" / name
    if src.exists():
        dst = DOCS / name
        shutil.copyfile(src, dst)
        print(f"copied {src} -> {dst}")
