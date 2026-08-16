import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from config.project_config import SPECTRAL_INDEXES


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = nir + red
    return np.divide(nir - red, denom, out=np.zeros_like(nir, dtype=float), where=denom != 0)


def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = green + nir
    return np.divide(green - nir, denom, out=np.zeros_like(nir, dtype=float), where=denom != 0)


def compute_evi(blue: np.ndarray, red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = nir + 6 * red - 7.5 * blue + 1
    return np.divide(2.5 * (nir - red), denom, out=np.zeros_like(nir, dtype=float), where=denom != 0)


def compute_savi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = nir + red + 0.5
    return np.divide((nir - red) / (nir + red + 0.5), 1.5, out=np.zeros_like(nir, dtype=float), where=denom != 0)


def compute_ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = swir + nir
    return np.divide(swir - nir, denom, out=np.zeros_like(nir, dtype=float), where=denom != 0)


def compute_mndwi(green: np.ndarray, swir: np.ndarray) -> np.ndarray:
    denom = green + swir
    return np.divide(green - swir, denom, out=np.zeros_like(green, dtype=float), where=denom != 0)


def compute_all_indices(bands: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    results = {}
    red = bands["red"]
    green = bands["green"]
    blue = bands["blue"]
    nir = bands["nir"]
    swir = bands["swir"]

    results["NDVI"] = compute_ndvi(red, nir)
    results["NDWI"] = compute_ndwi(green, nir)
    results["EVI"] = compute_evi(blue, red, nir)
    results["SAVI"] = compute_savi(red, nir)
    results["NDBI"] = compute_ndbi(swir, nir)
    results["MNDWI"] = compute_mndwi(green, swir)
    return results


if __name__ == "__main__":
    print("Indices spectraux disponibles:")
    for key, formula in SPECTRAL_INDEXES.items():
        print(f"- {key}: {formula}")
