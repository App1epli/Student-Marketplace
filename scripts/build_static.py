"""Verify runtime, apply pending schema upgrades on Vercel, and copy assets."""
from pathlib import Path
import shutil
import sys
import os

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    # Catch missing runtime libraries during the build, before publishing a function.
    from backend.app import app
    assert callable(app), "Flask entrypoint is not callable"
    if os.environ.get('VERCEL'):
        if not os.environ.get('DATABASE_URL'):
            raise RuntimeError('Set DATABASE_URL for this deployment environment in Vercel before building.')
        from backend.database import migrate_database
        migrate_database()
        print('Database schema migrations applied. Existing records preserved.')
    shutil.copytree(ROOT / "frontend/static", ROOT / "public/static", dirs_exist_ok=True)
    print("Flask entrypoint verified; frontend assets copied to public/static")
