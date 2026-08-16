import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ee

from config.project_config import EE_PROJECT_ID


def init_ee():
    try:
        if hasattr(ee, "data") and hasattr(ee.data, "initialized") and ee.data.initialized():
            print(f"Earth Engine déjà initialisé pour le projet: {EE_PROJECT_ID}")
            return
    except Exception:
        pass

    try:
        ee.Initialize(project=EE_PROJECT_ID)
        print(f"Earth Engine initialisé pour le projet: {EE_PROJECT_ID}")
        return
    except Exception:
        try:
            ee.Initialize()
            print(f"Earth Engine initialisé avec le contexte par défaut pour le projet: {EE_PROJECT_ID}")
            return
        except Exception as exc:
            raise RuntimeError(
                "Earth Engine n'est pas authentifié ou n'est pas correctement configuré. "
                "Exécute d'abord: earthengine authenticate --project project37246"
            ) from exc


def get_senegal_roi():
    return ee.Geometry.Rectangle([
        -17.6, 12.0,
        -11.3, 17.3,
    ], None, False)


def export_sentinel_2_timeseries(output_dir: str = "data/raw/gee"):
    init_ee()
    out = Path(PROJECT_ROOT) / output_dir
    out.mkdir(parents=True, exist_ok=True)

    roi = get_senegal_roi()
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi)
        .filterDate("2023-01-01", "2024-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .select(["B2", "B3", "B4", "B8", "B11", "B12"])
    )

    image = collection.median().clip(roi)
    task = ee.batch.Export.image.toDrive(
        image=image,
        description="senegal_sentinel2_median_2023_2024",
        folder="senegal_gee",
        fileNamePrefix="senegal_sentinel2_median_2023_2024",
        region=roi.getInfo()["coordinates"],
        scale=10,
        maxPixels=1e13,
    )
    task.start()
    print(f"Tâche exportée vers Google Drive: {task.id}")


def export_terrain_data():
    init_ee()
    roi = get_senegal_roi()

    precipitation = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").filterDate("2023-01-01", "2024-12-31").filterBounds(roi)
    task_precip = ee.batch.Export.image.toDrive(
        image=precipitation.mean().clip(roi),
        description="senegal_chirps_mean",
        folder="senegal_gee",
        fileNamePrefix="senegal_chirps_mean",
        region=roi.getInfo()["coordinates"],
        scale=5500,
        maxPixels=1e13,
    )
    task_precip.start()
    print(f"Tâche CHIRPS exportée: {task_precip.id}")

    ndvi = (
        ee.ImageCollection("MODIS/061/MOD13A2")
        .filterBounds(roi)
        .filterDate("2023-01-01", "2024-12-31")
        .select("NDVI")
    )
    task_ndvi = ee.batch.Export.image.toDrive(
        image=ndvi.mean().clip(roi),
        description="senegal_modis_ndvi_mean",
        folder="senegal_gee",
        fileNamePrefix="senegal_modis_ndvi_mean",
        region=roi.getInfo()["coordinates"],
        scale=250,
        maxPixels=1e13,
    )
    task_ndvi.start()
    print(f"Tâche MODIS NDVI exportée: {task_ndvi.id}")


def list_common_gee_datasets():
    datasets = [
        "COPERNICUS/S2_SR_HARMONIZED",
        "LANDSAT/LC08/C02/T1_L2",
        "MODIS/061/MOD13A2",
        "UCSB-CHG/CHIRPS/PENTAD",
        "ECMWF/ERA5_LAND/HOURLY",
        "OpenLandMap/soil",
        "USGS/SRTMGL1_003",
    ]
    for dataset in datasets:
        print(dataset)


if __name__ == "__main__":
    print("=== Telechargement des donnees Earth Engine ===")
    list_common_gee_datasets()
    export_sentinel_2_timeseries()
    export_terrain_data()
