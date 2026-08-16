import sqlite3
import sys
from pathlib import Path

try:
    import rasterio
except Exception:
    rasterio = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "multimodal_base.sqlite"
SOURCE_DIRS = [
    PROJECT_ROOT / "data",
    Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset"),
]


def infer_geotiff_metadata(file_path: Path):
    name = file_path.stem.lower()
    metadata = {
        "region": "Sénégal",
        "agro_zone": "Zone agro-écologique du Sénégal",
        "spectral_index": "NDVI" if "ndvi" in name else "Indice de végétation",
        "satellite_source": "MODIS/061/MOD13A2" if "ndvi" in name else "Source raster inconnue",
        "period_start": None,
        "period_end": None,
        "time_period": None,
        "use_case": "Suivi de la végétation et de l’état agroécologique",
    }
    import re
    match = re.search(r"(20\d{2})[_-](\d{2})", file_path.name)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        metadata["period_start"] = f"{year}-{month:02d}-01"
        metadata["period_end"] = f"{year}-{month:02d}-{28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31}"
        metadata["time_period"] = f"{year}-{month:02d}"
    return metadata


def ensure_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geotiff_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT,
            file_name TEXT,
            relative_path TEXT,
            width INTEGER,
            height INTEGER,
            count INTEGER,
            crs TEXT,
            bounds TEXT,
            dtype TEXT,
            source_root TEXT,
            region TEXT DEFAULT 'Sénégal',
            agro_zone TEXT DEFAULT 'Zone agro-écologique du Sénégal',
            spectral_index TEXT DEFAULT 'NDVI',
            satellite_source TEXT DEFAULT 'MODIS/061/MOD13A2',
            period_start TEXT,
            period_end TEXT,
            time_period TEXT,
            use_case TEXT DEFAULT 'Suivi de la végétation et de l’état agroécologique',
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def scan(dir_path: Path, conn: sqlite3.Connection, limit: int = 2000):
    if not dir_path.exists():
        return

    scanned = 0
    for file_path in sorted(dir_path.rglob('*')):
        if scanned >= limit:
            break
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix not in {'.tif', '.tiff'}:
            continue
        if file_path.stat().st_size > 250 * 1024 * 1024:
            continue

        try:
            relative = file_path.relative_to(dir_path)
        except ValueError:
            relative = file_path.name

        metadata = infer_geotiff_metadata(file_path)
        row = [str(file_path), file_path.name, str(relative), None, None, None, None, None, None, str(dir_path), metadata["region"], metadata["agro_zone"], metadata["spectral_index"], metadata["satellite_source"], metadata["period_start"], metadata["period_end"], metadata["time_period"], metadata["use_case"]]
        if rasterio is not None:
            try:
                with rasterio.open(file_path) as src:
                    row[3] = src.width
                    row[4] = src.height
                    row[5] = src.count
                    row[6] = str(src.crs)
                    row[7] = str(src.bounds)
                    row[8] = str(src.dtypes[0]) if src.dtypes else None
            except Exception:
                pass
        conn.execute(
            "INSERT OR IGNORE INTO geotiff_catalog(file_path, file_name, relative_path, width, height, count, crs, bounds, dtype, source_root, region, agro_zone, spectral_index, satellite_source, period_start, period_end, time_period, use_case) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            row,
        )
        scanned += 1


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH, timeout=60)
    ensure_table(conn)
    for base in SOURCE_DIRS:
        scan(base, conn, limit=2000)
    conn.commit()
    conn.close()
    print(f"Catalog GEE/geotiff construit dans {DB_PATH}")
