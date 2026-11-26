"""Run the full suite in disposable schemas without printing DB credentials.

Uses TEST_DATABASE_URL when supplied, otherwise the application's configured DB.
The tests create random test_marketplace_* schemas and drop only those schemas.
No initialization or reseeding is performed in the application's default schema.
"""
from pathlib import Path
import logging
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import database

if __name__ == '__main__':
    if not os.environ.get('TEST_DATABASE_URL'):
        os.environ['TEST_DATABASE_URL'] = database.database_url()
    logging.disable(logging.CRITICAL)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / 'tests')))
    raise SystemExit(not result.wasSuccessful())
