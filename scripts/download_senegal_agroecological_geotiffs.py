import sqlite3
import sys
from pathlib import Path

import ee
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.project_config import EE_PROJECT_ID

DB_PATH = PROJECT_ROOT / 'data' / 'multimodal_base.sqlite'
OUT_DIR = PROJECT_ROOT / 'data' / 'raw' / 'gee' / 'senegal_agroecology'
MAX_FILE_SIZE_MB = 400


def init_ee():
    try:
        ee.Initialize(project=EE_PROJECT_ID)
        print(f'Earth Engine initialisé pour {EE_PROJECT_ID}')
    except Exception:
        try:
            ee.Initialize()
            print(f'Earth Engine initialisé avec le contexte par défaut pour {EE_PROJECT_ID}')
        except Exception as exc:
            raise RuntimeError(
                "Earth Engine non authentifié ou non configuré. Exécute d'abord: earthengine authenticate --project project37246"
            ) from exc


def senegal_agro_roi():
    return ee.Geometry.Rectangle([-17.5, 12.0, -14.0, 16.8])


def month_end(year: int, month: int) -> int:
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if month in (4, 6, 9, 11):
        return 30
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    raise ValueError(f'Mois invalide: {month}')


def download_monthly_ndvi(year: int, month: int):
    region = senegal_agro_roi()
    start = f'{year}-{month:02d}-01'
    end_day = month_end(year, month)
    end = f'{year}-{month:02d}-{end_day:02d}'

    collection = (
        ee.ImageCollection('MODIS/061/MOD13A2')
        .filterBounds(region)
        .filterDate(start, end)
        .select('NDVI')
    )
    count = collection.size().getInfo()
    if count == 0:
        print(f'Aucune donnée MODIS NDVI pour {year}-{month:02d}, skip.')
        return None

    image = collection.mean().clip(region)
    filename = f'senegal_ndvi_{year}_{month:02d}'
    output_path = OUT_DIR / f'{filename}.tif'
    region_coords = region.getInfo()['coordinates']
    url = image.getDownloadURL({
        'name': filename,
        'region': region_coords,
        'scale': 5000,
        'format': 'GEO_TIFF',
        'filePerBand': False,
        'maxPixels': 1e13,
    })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f'Téléchargement {filename} ...')
    response = requests.get(url, timeout=600)
    response.raise_for_status()
    with open(output_path, 'wb') as fh:
        fh.write(response.content)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f'Fichier {filename}: {size_mb:.2f} Mo')
    if size_mb > MAX_FILE_SIZE_MB:
        print(f'Attention: le fichier dépasse la limite de {MAX_FILE_SIZE_MB} Mo.')

    return output_path


def infer_geotiff_metadata(file_path: Path):
    name = file_path.stem.lower()
    region = "Sénégal"
    agro_zone = "Zone agro-écologique du Sénégal"
    spectral_index = "NDVI" if "ndvi" in name else "Indice de végétation"
    satellite_source = "MODIS/061/MOD13A2" if "ndvi" in name else "Source raster inconnue"
    use_case = "Suivi de la végétation et de l’état agroécologique"
    period_start = None
    period_end = None
    time_period = None

    import re
    match = re.search(r"(20\d{2})[_-](\d{2})", file_path.name)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        period_start = f"{year}-{month:02d}-01"
        period_end = f"{year}-{month:02d}-{28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31}"
        time_period = f"{year}-{month:02d}"

    return {
        "region": region,
        "agro_zone": agro_zone,
        "spectral_index": spectral_index,
        "satellite_source": satellite_source,
        "period_start": period_start,
        "period_end": period_end,
        "time_period": time_period,
        "use_case": use_case,
    }


def ensure_catalog_table(conn: sqlite3.Connection):
    conn.execute('''
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
    ''')
    conn.commit()


def insert_geotiff_record(conn: sqlite3.Connection, file_path: Path):
    relative = file_path.relative_to(PROJECT_ROOT).as_posix()
    metadata = infer_geotiff_metadata(file_path)
    try:
        import rasterio
        with rasterio.open(file_path) as src:
            width = src.width
            height = src.height
            count = src.count
            crs = str(src.crs)
            bounds = str(src.bounds)
            dtype = str(src.dtypes[0]) if src.dtypes else None
    except Exception:
        width = height = count = None
        crs = bounds = dtype = None

    conn.execute(
        "INSERT OR IGNORE INTO geotiff_catalog(file_path, file_name, relative_path, width, height, count, crs, bounds, dtype, source_root, region, agro_zone, spectral_index, satellite_source, period_start, period_end, time_period, use_case) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(file_path),
            file_path.name,
            relative,
            width,
            height,
            count,
            crs,
            bounds,
            dtype,
            str(file_path.parent),
            metadata["region"],
            metadata["agro_zone"],
            metadata["spectral_index"],
            metadata["satellite_source"],
            metadata["period_start"],
            metadata["period_end"],
            metadata["time_period"],
            metadata["use_case"],
        ),
    )
    conn.commit()


def main():
    init_ee()
    conn = sqlite3.connect(DB_PATH, timeout=60)
    ensure_catalog_table(conn)

    total = 0
    for year in range(2003, 2026):
        for month in [7, 8, 9]:
            try:
                out_path = download_monthly_ndvi(year, month)
                if out_path is not None:
                    insert_geotiff_record(conn, out_path)
                    total += 1
                    print(f'Enregistré dans la base: {out_path.name}')
            except Exception as exc:
                print(f'Erreur pour {year}-{month:02d}: {type(exc).__name__}: {exc}')

    conn.close()
    print(f'Téléchargements GeoTIFF terminés: {total} fichiers enregistrés dans la base SQLite.')


if __name__ == '__main__':
    main()
