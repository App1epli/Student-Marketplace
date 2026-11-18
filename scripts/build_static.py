"""Copy frontend assets to Vercel's public directory without connecting to a DB."""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    # Catch missing runtime libraries during the build, before publishing a function.
    from backend.app import app
    assert callable(app), "Flask entrypoint is not callable"
    shutil.copytree(ROOT / "frontend/static", ROOT / "public/static", dirs_exist_ok=True)
    print("Flask entrypoint verified; frontend assets copied to public/static")
