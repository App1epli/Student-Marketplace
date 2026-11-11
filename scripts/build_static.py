"""Copy frontend assets to Vercel's public directory without connecting to a DB."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    shutil.copytree(ROOT / "frontend/static", ROOT / "public/static", dirs_exist_ok=True)
    print("Frontend assets copied to public/static")
