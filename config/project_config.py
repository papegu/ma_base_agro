from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = DATA_DIR / "output"

EE_PROJECT_ID = "project37246"
EE_ASSET_PREFIX = "projects/project37246/assets/"

LOCAL_GEOFILES_EXTENSIONS = {".tif", ".tiff", ".shp", ".gpkg", ".geojson", ".csv"}

TERRITORY_BOUNDS = {
    "west_africa": {
        "min_lon": -20.0,
        "max_lon": 20.0,
        "min_lat": -5.0,
        "max_lat": 30.0,
    },
    "senegal": {
        "min_lon": -17.6,
        "max_lon": -11.3,
        "min_lat": 12.0,
        "max_lat": 17.3,
    },
}

SENTINEL_BANDS = {
    "B02": "Blue",
    "B03": "Green",
    "B04": "Red",
    "B08": "NIR",
    "B8A": "Red Edge 1",
    "B11": "SWIR 1",
    "B12": "SWIR 2",
}

SPECTRAL_INDEXES = {
    "NDVI": "(NIR - RED) / (NIR + RED)",
    "NDWI": "(GREEN - NIR) / (GREEN + NIR)",
    "EVI": "2.5 * (NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)",
    "SAVI": "((NIR - RED) / (NIR + RED + 0.5)) * (1.5)",
    "NDBI": "(SWIR - NIR) / (SWIR + NIR)",
    "MNDWI": "(GREEN - SWIR) / (GREEN + SWIR)",
}

