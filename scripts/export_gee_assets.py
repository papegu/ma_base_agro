import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ee

from config.project_config import EE_PROJECT_ID, TERRITORY_BOUNDS


def init_ee():
    ee.Initialize(project=EE_PROJECT_ID)
    print(f"Earth Engine initialisé: {EE_PROJECT_ID}")


def senegal_geometry():
    bounds = TERRITORY_BOUNDS["senegal"]
    return ee.Geometry.Rectangle(
        [bounds["min_lon"], bounds["min_lat"], bounds["max_lon"], bounds["max_lat"]],
        None,
        False,
    )


def export_sentinel2_asset():
    roi = senegal_geometry()
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi)
        .filterDate("2023-01-01", "2024-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 25))
        .select(["B2", "B3", "B4", "B8", "B11", "B12"])
    )
    image = collection.median().clip(roi)
    asset_id = "projects/project37246/assets/agroecology/senegal_sentinel2_median_2023_2024"
    task = ee.batch.Export.image.toAsset(
        image=image,
        description="senegal_sentinel2_median_2023_2024",
        assetId=asset_id,
        region=roi.getInfo()["coordinates"],
        scale=10,
        maxPixels=1e13,
    )
    task.start()
    print(f"Tâche d’export asset lancée: {task.id} -> {asset_id}")


def export_chirps_asset():
    roi = senegal_geometry()
    col = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").filterBounds(roi).filterDate("2023-01-01", "2024-12-31")
    image = col.mean().clip(roi)
    asset_id = "projects/project37246/assets/agroecology/senegal_chirps_mean_2023_2024"
    task = ee.batch.Export.image.toAsset(
        image=image,
        description="senegal_chirps_mean_2023_2024",
        assetId=asset_id,
        region=roi.getInfo()["coordinates"],
        scale=5500,
        maxPixels=1e13,
    )
    task.start()
    print(f"Tâche CHIRPS asset lancée: {task.id} -> {asset_id}")


def export_vector_asset():
    roi = senegal_geometry()
    fc = ee.FeatureCollection("users/your_user_name/your_table") if False else ee.FeatureCollection([])
    if fc.size().getInfo() == 0:
        print("Aucune feature de référence disponible pour l’export vectoriel. Préparez d’abord votre table GEE.")
        return
    task = ee.batch.Export.table.toAsset(
        collection=fc,
        description="senegal_vector_dataset",
        assetId="projects/project37246/assets/agroecology/senegal_vector_dataset",
    )
    task.start()
    print(f"Tâche vectorielle lancée: {task.id}")


if __name__ == "__main__":
    init_ee()
    export_sentinel2_asset()
    export_chirps_asset()
    export_vector_asset()
