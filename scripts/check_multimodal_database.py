import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.sqlite_auth import SQLITE_DB_PASSWORD, SQLITE_DB_PATH, SQLITE_DB_USER

DB_PATH = SQLITE_DB_PATH

print('DB_LOGIN', SQLITE_DB_USER)
print('DB_EXISTS', DB_PATH.exists())

conn = sqlite3.connect(DB_PATH, timeout=60)
cur = conn.cursor()

print('DB_AUTH_OK', SQLITE_DB_PASSWORD is not None and len(SQLITE_DB_PASSWORD) > 0)
print('TABLES', cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall())
print('METADATA_COUNT', cur.execute('SELECT COUNT(*) FROM metadata').fetchone()[0])
print('CLIMATE_COUNT', cur.execute('SELECT COUNT(*) FROM climate').fetchone()[0])
print('AGRICULTURE_COUNT', cur.execute('SELECT COUNT(*) FROM agriculture').fetchone()[0])
print('ARTICLE_TABLE_EXISTS', cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='article_artifacts'").fetchone()[0])
print('ARTICLE_COUNT', cur.execute('SELECT COUNT(*) FROM article_artifacts').fetchone()[0] if cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='article_artifacts'").fetchone()[0] else 0)
print('GEOTIFF_TABLE_EXISTS', cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='geotiff_catalog'").fetchone()[0])
print('GEOTIFF_COUNT', cur.execute('SELECT COUNT(*) FROM geotiff_catalog').fetchone()[0] if cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='geotiff_catalog'").fetchone()[0] else 0)
print('SAMPLE_ARTIFACTS', cur.execute('SELECT relative_path, category FROM article_artifacts ORDER BY id LIMIT 5').fetchall())

conn.close()
