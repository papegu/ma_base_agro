import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ee

from config.project_config import EE_PROJECT_ID


def initialize_gee():
    ee.Initialize(project=EE_PROJECT_ID)
    print(f"Earth Engine initialise avec le projet {EE_PROJECT_ID}")


def list_available_collections():
    collection_names = [
        "COPERNICUS/S2_SR_HARMONIZED",
        "LANDSAT/LC08/C02/T1_L2",
        "MODIS/061/MOD13A2",
        "UCSB-CHG/CHIRPS/PENTAD",
        "ECMWF/ERA5_LAND/HOURLY",
        "OpenLandMap/soil",
        "USGS/SRTMGL1_003",
    ]
    for name in collection_names:
        print(name)


def scan_local_workspace(root_dir: str):
    root = Path(root_dir)
    print(f"Scan du repertoire local: {root}")
    for file in sorted(root.rglob('*')):
        if file.is_file():
            print(file)


if __name__ == "__main__":
    initialize_gee()
    list_available_collections()
    scan_local_workspace(r"C:\Users\HP\Desktop\Mes Codes Recherche\BasesGeospatialeMultiModale")
