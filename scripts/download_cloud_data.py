import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from config.project_config import RAW_DIR


PUBLIC_SOURCES = {
    "worldclim": "https://biogeo.ucdavis.edu/data/worldclim/v2.1/base/wc2.1_30s_prec.zip",
    "chirps_monthly": "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/chirps-v2.0.monthly.nc",
}


def download_file(url: str, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()

    with open(destination, "wb") as file_obj:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file_obj.write(chunk)

    print(f"Telechargement termine: {destination}")


def download_public_cloud_data():
    cloud_dir = RAW_DIR / "cloud_public"
    cloud_dir.mkdir(parents=True, exist_ok=True)

    for name, url in PUBLIC_SOURCES.items():
        target = cloud_dir / f"{name}.zip" if url.endswith(".zip") else cloud_dir / f"{name}.nc"
        print(f"Telechargement de {name} depuis {url}")
        try:
            download_file(url, target)
        except Exception as exc:
            print(f"Echec pour {name}: {exc}")


def unzip_archives_in_folder(folder: Path):
    for archive in folder.glob("*.zip"):
        print(f"Extraction du zip: {archive}")
        with zipfile.ZipFile(archive, "r") as archive_obj:
            archive_obj.extractall(folder)


if __name__ == "__main__":
    download_public_cloud_data()
    unzip_archives_in_folder(RAW_DIR / "cloud_public")
