import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DB_PATH = PROJECT_ROOT / "data" / "multimodal_base.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT,
    source_type TEXT,
    region TEXT,
    temporal_start TEXT,
    temporal_end TEXT,
    spatial_resolution REAL,
    file_path TEXT,
    format TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS climate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    station_name TEXT,
    temperature_c REAL,
    precipitation_mm REAL,
    source TEXT,
    region TEXT
);

CREATE TABLE IF NOT EXISTS soils (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    geom_id TEXT,
    soil_type TEXT,
    texture TEXT,
    organic_matter REAL,
    ph REAL,
    region TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS agriculture (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER,
    crop_name TEXT,
    production_tonnes REAL,
    area_ha REAL,
    region TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS water_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_name TEXT,
    type_name TEXT,
    region TEXT,
    source TEXT,
    geom_wkt TEXT
);

CREATE TABLE IF NOT EXISTS millet_yields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INTEGER,
    region TEXT,
    year INTEGER,
    yield_kg_ha REAL,
    yield_t_ha REAL,
    baseline_yield REAL,
    anomaly REAL,
    anomaly_pct REAL,
    rainfall_mm REAL,
    temp_celsius REAL,
    drought_indicator INTEGER,
    good_year_indicator INTEGER,
    latitude REAL,
    longitude REAL,
    source TEXT
);

CREATE TABLE IF NOT EXISTS livestock_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region TEXT,
    department TEXT,
    arrondissement TEXT,
    commune TEXT,
    locality TEXT,
    structure_type TEXT,
    structure_name TEXT,
    gestion TEXT,
    thematique TEXT,
    utm_x REAL,
    utm_y REAL,
    source TEXT,
    geom_wkt TEXT
);

CREATE TABLE IF NOT EXISTS remote_sensing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT,
    sensor TEXT,
    acquisition_date TEXT,
    cloud_cover REAL,
    resolution_m REAL,
    file_path TEXT,
    region TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS spectral_indices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_name TEXT,
    index_name TEXT,
    date TEXT,
    min_value REAL,
    max_value REAL,
    mean_value REAL,
    file_path TEXT,
    region TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS geospatial_layers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer_name TEXT,
    geometry_type TEXT,
    file_path TEXT,
    crs TEXT,
    region TEXT,
    source TEXT
);
"""


def create_database(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"Base de donnees creee: {db_path}")


def insert_local_metadata(db_path: Path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    entries = [
        ("pluviometrie", "tabulaire", "Senegal", "2013-01-01", "2014-12-31", 0.0, str(PROJECT_ROOT / "pluvio_statio-2023-2014.csv"), "CSV", "Stations pluviometriques"),
        ("temperature", "tabulaire", "Senegal", "2013-01-01", "2014-12-31", 0.0, str(PROJECT_ROOT / "temp_statio-2023-2014.csv"), "CSV", "Stations meteorologiques"),
        ("production_agricole", "tabulaire", "Senegal", "2003", "2012", 0.0, str(PROJECT_ROOT / "production-agricole-2003-2012.zip"), "ZIP", "Productions agricoles"),
        ("points_eau", "vectoriel", "Senegal", "N/A", "N/A", 0.0, str(PROJECT_ROOT / "point_eau_pastoraux.zip"), "ZIP", "Points d'eau pastoraux"),
        ("unites_pastorales", "vectoriel", "Senegal", "N/A", "N/A", 0.0, str(PROJECT_ROOT / "unites_pastorales-2.zip"), "ZIP", "Unites pastorales"),
        ("infra_socio_economique", "vectoriel", "Senegal", "N/A", "N/A", 0.0, str(PROJECT_ROOT / "infra_socio_economique.zip"), "ZIP", "Infrastructure socio-economique"),
    ]

    cursor.executemany(
        "INSERT OR IGNORE INTO metadata(source_name, source_type, region, temporal_start, temporal_end, spatial_resolution, file_path, format, notes) VALUES(?,?,?,?,?,?,?,?,?)",
        entries,
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_database(DB_PATH)
    insert_local_metadata(DB_PATH)
    print("Base multimodale initialisee avec le schema principal.")
