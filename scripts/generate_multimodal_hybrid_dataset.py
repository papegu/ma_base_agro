import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "multimodal_base.sqlite"
OUT_DIR = PROJECT_ROOT / "data" / "multimodal_hybrid_dataset"
GEOTIFF_DIR = OUT_DIR / "geotiffs"


def ensure_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GEOTIFF_DIR.mkdir(parents=True, exist_ok=True)


def read_table(conn, table_name):
    return pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)


def aggregate_climate(conn):
    df = read_table(conn, "climate")
    if df.empty:
        return pd.DataFrame(columns=["region", "year", "precipitation_mm", "temperature_c"])
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date"].dt.year
    return (
        df.groupby(["region", "year"], as_index=False)
        .agg({"precipitation_mm": "mean", "temperature_c": "mean"})
        .rename(columns={"region": "region", "year": "year"})
    )


def aggregate_agriculture(conn):
    df = read_table(conn, "agriculture")
    if df.empty:
        return pd.DataFrame(columns=["region", "year", "production_tonnes", "area_ha"])
    df = df.copy()
    return (
        df.groupby(["region", "year"], as_index=False)
        .agg({"production_tonnes": "sum", "area_ha": "sum"})
    )


def aggregate_yields(conn):
    df = read_table(conn, "millet_yields")
    if df.empty:
        return pd.DataFrame(columns=["region", "year", "yield_kg_ha", "rainfall_mm", "temp_celsius", "anomaly_pct"])
    df = df.copy()
    return (
        df.groupby(["region", "year"], as_index=False)
        .agg({"yield_kg_ha": "mean", "rainfall_mm": "mean", "temp_celsius": "mean", "anomaly_pct": "mean"})
    )


def aggregate_spectral(conn):
    df = read_table(conn, "spectral_indices")
    if df.empty:
        return pd.DataFrame(columns=["region", "year", "mean_ndvi", "mean_value"])
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date"].dt.year
    df["region"] = df["region"].fillna("senegal")
    return (
        df.groupby(["region", "year"], as_index=False)
        .agg({"mean_value": "mean"})
        .rename(columns={"mean_value": "mean_ndvi"})
    )


def build_multimodal_dataset():
    conn = sqlite3.connect(DB_PATH)
    climate = aggregate_climate(conn)
    agriculture = aggregate_agriculture(conn)
    yields = aggregate_yields(conn)
    spectral = aggregate_spectral(conn)
    conn.close()

    df = climate.merge(agriculture, on=["region", "year"], how="outer")
    df = df.merge(yields, on=["region", "year"], how="outer")
    df = df.merge(spectral, on=["region", "year"], how="outer")

    df = df.sort_values(["region", "year"]).reset_index(drop=True)
    df["region"] = df["region"].fillna("senegal")
    df["year"] = df["year"].fillna(0).astype(int)

    for col in [
        "precipitation_mm",
        "temperature_c",
        "production_tonnes",
        "area_ha",
        "yield_kg_ha",
        "rainfall_mm",
        "temp_celsius",
        "anomaly_pct",
        "mean_ndvi",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["target_yield_kg_ha"] = df["yield_kg_ha"].fillna(df["production_tonnes"].div(10).replace([np.inf, -np.inf], np.nan))
    df = df.drop_duplicates(subset=["region", "year"]).reset_index(drop=True)
    return df


def save_dataset_files(df):
    ensure_dirs()
    csv_path = OUT_DIR / "multimodal_hybrid_dataset.csv"
    xlsx_path = OUT_DIR / "multimodal_hybrid_dataset.xlsx"
    metadata_path = OUT_DIR / "dataset_metadata.json"

    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)

    metadata = {
        "dataset_name": "multimodal_hybrid_agroecology_dataset",
        "rows": int(len(df)),
        "columns": list(df.columns),
        "target_col": "target_yield_kg_ha",
        "output_files": [
            csv_path.name,
            xlsx_path.name,
            "geotiffs/",
            metadata_path.name,
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def create_geotiffs(df, max_years=5):
    years = sorted(df["year"].dropna().unique().astype(int))[:max_years]
    for year in years:
        year_df = df[df["year"] == year].copy()
        if year_df.empty:
            continue
        ndvi_base = year_df["mean_ndvi"].fillna(0.5).to_numpy()
        ndvi_base = np.nan_to_num(ndvi_base, nan=0.5)
        array = np.zeros((32, 32), dtype=np.float32)
        for idx, val in enumerate(ndvi_base[:array.size]):
            r = idx // 32
            c = idx % 32
            array[r, c] = float(val)
        if array.sum() == 0:
            array[:] = 0.5
        profile = {
            "driver": "GTiff",
            "height": array.shape[0],
            "width": array.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:4326",
            "transform": from_origin(-18.0, 17.5, 0.05, 0.05),
        }
        out_path = GEOTIFF_DIR / f"ndvi_{year}.tif"
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(array, 1)
        print(f"Created GeoTIFF: {out_path}")


def main():
    df = build_multimodal_dataset()
    save_dataset_files(df)
    create_geotiffs(df)
    print(f"Hybrid multimodal dataset saved in: {OUT_DIR}")
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()
