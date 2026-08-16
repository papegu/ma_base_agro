import io
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import shapefile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "multimodal_base.sqlite"


def read_csv_with_fallback(file_obj):
    data = file_obj.read()
    for encoding in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
        try:
            text = data.decode(encoding)
            return pd.read_csv(io.StringIO(text), sep=';')
        except Exception:
            continue
    text = data.decode("latin-1", errors="replace")
    return pd.read_csv(io.StringIO(text), sep=';')


def clean_decimal(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip().replace(" ", "").replace(".", "").replace(",", ".")
        if value in ["", "-", "0"]:
            return 0.0
        try:
            return float(value)
        except ValueError:
            return None
    return float(value)


def ingest_climate_data(db_path: Path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for file_name in ["pluvio_statio-2023-2014.csv", "temp_statio-2023-2014.csv"]:
        df = pd.read_csv(PROJECT_ROOT / file_name, sep=';')
        if file_name.startswith("pluvio"):
            variable = "precipitation_mm"
            source = "pluviometrie"
        else:
            variable = "temperature_c"
            source = "temperature"

        for _, row in df.iterrows():
            station = str(row.iloc[0]).strip()
            for col in df.columns[1:]:
                year = int(str(col).strip())
                val = clean_decimal(row[col])
                if val is None:
                    continue
                cursor.execute(
                    "INSERT INTO climate(date, station_name, temperature_c, precipitation_mm, source, region) VALUES(?,?,?,?,?,?)",
                    (f"{year}-01-01", station, val if variable == "temperature_c" else None, val if variable == "precipitation_mm" else None, source, "Senegal"),
                )

    conn.commit()
    conn.close()
    print("Donnees climatiques chargees.")


def ingest_agricultural_data(db_path: Path):
    archive = PROJECT_ROOT / "production-agricole-2003-2012.zip"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    with zipfile.ZipFile(archive, "r") as zf:
        for file_name in sorted(zf.namelist()):
            if file_name.endswith(".csv") and not file_name.startswith("__MACOSX"):
                crop_name = file_name.replace(".csv", "")
                with zf.open(file_name) as f:
                    df = read_csv_with_fallback(f)
                for _, row in df.iterrows():
                    station = str(row.iloc[0]).strip()
                    for col in df.columns[1:]:
                        if "prod_tonn_" not in col:
                            continue
                        year_text = col.split("_")[-1]
                        if not year_text.isdigit():
                            continue
                        year = int(year_text)
                        val = clean_decimal(row[col])
                        if val is None:
                            continue
                        cursor.execute(
                            "INSERT INTO agriculture(year, crop_name, production_tonnes, area_ha, region, source) VALUES(?,?,?,?,?,?)",
                            (year, crop_name, val, None, station, "production_agricole"),
                        )

    conn.commit()
    conn.close()
    print("Donnees agricoles chargees.")


def ingest_vector_metadata(db_path: Path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    archives = [
        PROJECT_ROOT / "point_eau_pastoraux.zip",
        PROJECT_ROOT / "unites_pastorales-2.zip",
        PROJECT_ROOT / "infra_socio_economique.zip",
    ]

    for archive in archives:
        with zipfile.ZipFile(archive, 'r') as zf:
            shapes = [name for name in zf.namelist() if name.lower().endswith('.shp')]
            for shp in shapes:
                layer_name = Path(shp).stem
                cursor.execute(
                    "INSERT OR IGNORE INTO geospatial_layers(layer_name, geometry_type, file_path, crs, region, source) VALUES(?,?,?,?,?,?)",
                    (layer_name, 'vector', str(archive), 'EPSG:4326', 'Senegal', archive.name),
                )

    conn.commit()
    conn.close()
    print("Metadonnees geospatiales chargees.")


def shape_to_wkt(shape):
    shape_type = shape.shapeType
    points = shape.points

    if shape_type in {1, 11}:
        if not points:
            return None
        x, y = points[0]
        return f"POINT ({x} {y})"

    if shape_type in {3, 13, 23, 31, 32}:
        if not points:
            return None
        rings = []
        if hasattr(shape, "parts") and shape.parts:
            parts = list(shape.parts)
            parts.append(len(points))
            for start, end in zip(parts[:-1], parts[1:]):
                ring = [f"{x} {y}" for x, y in points[start:end]]
                if ring:
                    rings.append("(" + ", ".join(ring) + ")")
        else:
            rings.append("(" + ", ".join(f"{x} {y}" for x, y in points) + ")")

        if shape_type in {3, 13}:
            return "LINESTRING " + (rings[0] if rings else "EMPTY")
        return "POLYGON (" + ", ".join(rings) + ")" if rings else None

    return None


def ingest_water_points(db_path: Path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    candidates = [
        PROJECT_ROOT / "point_eau_pastoraux.zip",
        Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\BasesGeospatialeMultiModale\point_eau_pastoraux\Hydraulique\Abreuvoir_potence.shx").with_suffix('.shp'),
    ]

    for candidate in candidates:
        if not candidate.exists():
            continue

        if candidate.suffix.lower() == '.zip':
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                with zipfile.ZipFile(candidate, 'r') as zf:
                    zf.extractall(tmp_path)
                shapefiles = sorted(tmp_path.rglob('*.shp'))
                if not shapefiles:
                    continue
                for shp in shapefiles:
                    try:
                        sf = shapefile.Reader(str(shp))
                    except Exception as exc:
                        print(f"Impossible de lire {shp}: {exc}")
                        continue
                    layer_name = shp.stem
                    for record, shape in zip(sf.records(), sf.shapes()):
                        feature_name = record[0] if len(record) > 0 else layer_name
                        type_name = record[1] if len(record) > 1 else layer_name
                        geom_wkt = shape_to_wkt(shape)
                        cursor.execute(
                            "INSERT INTO water_points(feature_name, type_name, region, source, geom_wkt) VALUES(?,?,?,?,?)",
                            (str(feature_name), str(type_name), "Senegal", candidate.name, geom_wkt),
                        )
                    sf.close()
        else:
            shp = candidate
            try:
                sf = shapefile.Reader(str(shp))
            except Exception as exc:
                print(f"Impossible de lire {shp}: {exc}")
                continue
            layer_name = shp.stem
            for record, shape in zip(sf.records(), sf.shapes()):
                feature_name = record[0] if len(record) > 0 else layer_name
                type_name = record[1] if len(record) > 1 else layer_name
                geom_wkt = shape_to_wkt(shape)
                cursor.execute(
                    "INSERT INTO water_points(feature_name, type_name, region, source, geom_wkt) VALUES(?,?,?,?,?)",
                    (str(feature_name), str(type_name), "Senegal", shp.name, geom_wkt),
                )
            sf.close()

    conn.commit()
    conn.close()
    print("Points d'eau charges dans water_points.")


def safe_float(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip().replace(" ", "")
        if value in {"", "-", "NA", "N/A"}:
            return None
        if "," in value and "." in value:
            value = value.replace(".", "").replace(",", ".")
        elif "," in value:
            value = value.replace(",", ".")
        try:
            return float(value)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ingest_soils_data(db_path: Path):
    soil_files = [
        PROJECT_ROOT / "data" / "published_articles" / "article_SHI_AIT2025-main" / "LUCAS_2018_soil_functions.csv",
        PROJECT_ROOT / "data" / "published_articles" / "article 3 RTCNET" / "article rtcnet etat art" / "LUCAS_2018_soil_functions.csv",
    ]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    seen = set()

    for file_path in soil_files:
        if not file_path.exists():
            continue
        df = pd.read_csv(file_path)
        if "LUCAS_ID" not in df.columns:
            continue

        for _, row in df.iterrows():
            geom_id = row.get("LUCAS_ID")
            if pd.isna(geom_id):
                continue
            key = (str(geom_id), str(file_path))
            if key in seen:
                continue
            seen.add(key)

            organic_matter = safe_float(row.get("WHC"))
            ph_value = safe_float(row.get("pH")) if "pH" in df.columns else None

            cursor.execute(
                "INSERT INTO soils(geom_id, soil_type, texture, organic_matter, ph, region, source) VALUES(?,?,?,?,?,?,?)",
                (
                    str(geom_id),
                    "LUCAS_2018",
                    "unknown",
                    organic_matter,
                    ph_value,
                    "Senegal",
                    file_path.relative_to(PROJECT_ROOT).as_posix(),
                ),
            )

    conn.commit()
    conn.close()
    print("Donnees de sol chargees dans soils.")


def ingest_spectral_indices_from_train_data(db_path: Path):
    train_path = Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\article12publie\processed\train_data.csv")
    if not train_path.exists():
        print("Fichier spectral absent: train_data.csv")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    df = pd.read_csv(train_path)
    index_columns = [
        c for c in df.columns
        if any(token in c.lower() for token in ['ndvi', 'evi', 'ndwi', 'savi', 'mndwi'])
        and c.lower() not in {'region', 'year', 'region_id'}
    ]

    for _, row in df.iterrows():
        region = row.get('region')
        year_value = row.get('year')
        if pd.isna(year_value):
            continue
        for col in index_columns:
            val = safe_float(row.get(col))
            if val is None:
                continue
            cursor.execute(
                "INSERT INTO spectral_indices(image_name, index_name, date, min_value, max_value, mean_value, file_path, region, source) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    f"{region}_{year_value}",
                    col,
                    str(year_value),
                    val,
                    val,
                    val,
                    str(train_path),
                    str(region),
                    "train_data.csv",
                ),
            )
    conn.commit()
    conn.close()
    print("Indices spectraux issus du fichier train_data.csv charges dans spectral_indices.")


def ingest_spectral_indices_data(db_path: Path):
    spectral_files = sorted(PROJECT_ROOT.rglob("*indices*average*values*.csv"))
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    seen = set()

    for file_path in spectral_files:
        if ".venv" in file_path.parts:
            continue
        try:
            df = pd.read_csv(file_path)
        except Exception:
            continue
        if df.empty or "Year" not in df.columns:
            continue

        for _, row in df.iterrows():
            year_value = row.get("Year")
            if pd.isna(year_value):
                continue
            year_text = str(int(float(year_value))) if isinstance(year_value, (int, float)) else str(year_value)
            for index_name in df.columns:
                if index_name.lower() == "year":
                    continue
                value = safe_float(row.get(index_name))
                if value is None:
                    continue
                key = (file_path.as_posix(), year_text, str(index_name))
                if key in seen:
                    continue
                seen.add(key)
                cursor.execute(
                    "INSERT INTO spectral_indices(image_name, index_name, date, min_value, max_value, mean_value, file_path, region, source) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        file_path.stem,
                        str(index_name),
                        year_text,
                        value,
                        value,
                        value,
                        file_path.as_posix(),
                        "Senegal",
                        file_path.relative_to(PROJECT_ROOT).as_posix(),
                    ),
                )

    conn.commit()
    conn.close()
    print("Indices spectraux charges dans spectral_indices.")


def ingest_millet_yields(db_path: Path):
    yield_path = Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\article12publie\synthetic\senegal_mil_yields_2000_2020.csv")
    if not yield_path.exists():
        print("Fichier rendement mil absent.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    df = pd.read_csv(yield_path)
    for _, row in df.iterrows():
        cursor.execute(
            "INSERT INTO millet_yields(region_id, region, year, yield_kg_ha, yield_t_ha, baseline_yield, anomaly, anomaly_pct, rainfall_mm, temp_celsius, drought_indicator, good_year_indicator, latitude, longitude, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                safe_float(row.get('region_id')) if not pd.isna(row.get('region_id')) else None,
                row.get('region'),
                safe_float(row.get('year')) if not pd.isna(row.get('year')) else None,
                safe_float(row.get('yield_kg_ha')) if not pd.isna(row.get('yield_kg_ha')) else None,
                safe_float(row.get('yield_t_ha')) if not pd.isna(row.get('yield_t_ha')) else None,
                safe_float(row.get('baseline_yield')) if not pd.isna(row.get('baseline_yield')) else None,
                safe_float(row.get('anomaly')) if not pd.isna(row.get('anomaly')) else None,
                safe_float(row.get('anomaly_pct')) if not pd.isna(row.get('anomaly_pct')) else None,
                safe_float(row.get('rainfall_mm')) if not pd.isna(row.get('rainfall_mm')) else None,
                safe_float(row.get('temp_celsius')) if not pd.isna(row.get('temp_celsius')) else None,
                safe_float(row.get('drought_indicator')) if not pd.isna(row.get('drought_indicator')) else None,
                safe_float(row.get('good_year_indicator')) if not pd.isna(row.get('good_year_indicator')) else None,
                safe_float(row.get('latitude')) if not pd.isna(row.get('latitude')) else None,
                safe_float(row.get('longitude')) if not pd.isna(row.get('longitude')) else None,
                str(yield_path),
            ),
        )
    conn.commit()
    conn.close()
    print("Rendements de mil charges dans millet_yields.")


def ingest_livestock_units_data(db_path: Path):
    archive = Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\BasesGeospatialeMultiModale\unites_pastorales-2.zip")
    if not archive.exists():
        print("Archive unites_pastorales-2 absente.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        with zipfile.ZipFile(archive, 'r') as zf:
            zf.extractall(tmp_path)
        shapefiles = sorted(tmp_path.rglob('*.shp'))
        for shp in shapefiles:
            try:
                sf = shapefile.Reader(str(shp))
            except Exception as exc:
                print(f"Impossible de lire {shp}: {exc}")
                continue
            field_names = [field[0].lower() for field in sf.fields[1:]]
            for sr in sf.shapeRecords():
                record = sr.record
                values = {name: value for name, value in zip(field_names, record)}
                geom_wkt = shape_to_wkt(sr.shape)
                name_up = values.get('nom_up') or values.get('name_up') or values.get('unit_name')
                project = values.get('projet') or values.get('project')
                year = values.get('annee') or values.get('year')
                cursor.execute(
                    "INSERT INTO livestock_units(region, department, arrondissement, commune, locality, structure_type, structure_name, gestion, thematique, utm_x, utm_y, source, geom_wkt) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "Senegal",
                        project,
                        None,
                        None,
                        name_up,
                        "pastoral_unit",
                        name_up,
                        None,
                        f"pastoral_unit_{year}" if year is not None else "pastoral_unit",
                        None,
                        None,
                        archive.name,
                        geom_wkt,
                    ),
                )
            sf.close()
    conn.commit()
    conn.close()
    print("Informations geospatiales sur l'elevage chargees dans livestock_units.")


def ingest_remote_sensing_metadata(db_path: Path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    seen = set()

    for file_path in sorted(PROJECT_ROOT.rglob("*.tif")):
        if ".venv" in file_path.parts:
            continue
        if "site-packages" in str(file_path):
            continue
        if file_path.name.lower().endswith(".tif") is False:
            continue

        if file_path.as_posix() in seen:
            continue
        seen.add(file_path.as_posix())

        product_name = file_path.stem
        sensor = "unknown"
        lower_name = file_path.name.lower()
        if "sentinel" in lower_name:
            sensor = "Sentinel"
        elif "spi" in lower_name:
            sensor = "SPI"
        elif "out" in lower_name:
            sensor = "Raster output"

        acquisition_date = "unknown"
        for token in file_path.stem.split("_"):
            if len(token) == 4 and token.isdigit():
                acquisition_date = token
                break

        region = "Senegal" if "senegal" in lower_name or "senegal" in str(file_path).lower() else "unknown"
        resolution = 250.0 if "spi" in lower_name else 0.0

        cursor.execute(
            "INSERT INTO remote_sensing(product_name, sensor, acquisition_date, cloud_cover, resolution_m, file_path, region, source) VALUES(?,?,?,?,?,?,?,?)",
            (
                product_name,
                sensor,
                acquisition_date,
                None,
                resolution,
                file_path.as_posix(),
                region,
                file_path.relative_to(PROJECT_ROOT).as_posix(),
            ),
        )

    conn.commit()
    conn.close()
    print("Metadonnees de produits de teledetection chargees dans remote_sensing.")


def ingest_oni_data(db_path: Path):
    oni_path = Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset\codes false start of rainy season\oni\oni_annual_1981_2020.csv")
    if not oni_path.exists():
        print("Fichier ONI absent.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oni_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            oni REAL,
            source TEXT
        )
    """)
    df = pd.read_csv(oni_path)
    for _, row in df.iterrows():
        year = safe_float(row.get("year"))
        oni = safe_float(row.get("oni"))
        if year is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO oni_index(year, oni, source) VALUES(?,?,?)",
            (int(year), oni, oni_path.as_posix()),
        )
    conn.commit()
    conn.close()
    print("Indices ONI charges dans oni_index.")


def ingest_power_climate_data(db_path: Path):
    power_root = Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset\codes false start of rainy season\power data")
    if not power_root.exists():
        print("Dossier POWER absent.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS power_climate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            month INTEGER,
            source_file TEXT,
            variable_name TEXT,
            variable_value REAL,
            region TEXT,
            source TEXT
        )
    """)

    for excel_path in sorted(power_root.glob("*.xlsx")):
        try:
            df = pd.read_excel(excel_path)
        except Exception:
            continue
        if df.empty:
            continue
        for _, row in df.iterrows():
            if "YEAR" in df.columns:
                year_value = safe_float(row.get("YEAR"))
                date_year = int(year_value) if year_value is not None else None
            else:
                year_value = None
                for key in ["Year", "year", "annee"]:
                    if key in df.columns:
                        year_value = safe_float(row.get(key))
                        break
                date_year = int(year_value) if year_value is not None else None

            if date_year is None:
                continue
            for col in df.columns:
                if col.lower() in {"year", "annee", "years"}:
                    continue
                value = safe_float(row.get(col))
                if value is None:
                    continue
                conn.execute(
                    "INSERT INTO power_climate(year, month, source_file, variable_name, variable_value, region, source) VALUES(?,?,?,?,?,?,?)",
                    (date_year, None, excel_path.name, str(col), value, "Senegal", excel_path.as_posix()),
                )
    conn.commit()
    conn.close()
    print("Donnees climatiques POWER chargees dans power_climate.")


def ingest_rainy_season_model_dataset(db_path: Path):
    dataset_path = Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset\codes false start of rainy season\modeles_avec_timestep\donnees_avec_faux_demarage.xlsx")
    if not dataset_path.exists():
        print("Fichier donnees_avec_faux_demarage.xlsx absent.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rainy_season_model_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            RH2M REAL,
            PRECTOTCORR_SUM REAL,
            GWETTOP REAL,
            PS REAL,
            T2M REAL,
            WS2M REAL,
            ssrn REAL,
            lst_celsius REAL,
            ndvi REAL,
            sos_doy REAL,
            Evap_tavg REAL,
            LWdown_f_tavg REAL,
            Qair_f_tavg REAL,
            Qg_tavg REAL,
            Rainf_f_tavg REAL,
            SWdown_f_tavg REAL,
            oni REAL,
            SPEI_1_June REAL,
            SPEI_1_July REAL,
            SPEI_6_June REAL,
            SPEI_6_July REAL,
            faux_demarage INTEGER,
            source TEXT
        )
    """)

    df = pd.read_excel(dataset_path)
    for _, row in df.iterrows():
        conn.execute(
            "INSERT INTO rainy_season_model_data(year, RH2M, PRECTOTCORR_SUM, GWETTOP, PS, T2M, WS2M, ssrn, lst_celsius, ndvi, sos_doy, Evap_tavg, LWdown_f_tavg, Qair_f_tavg, Qg_tavg, Rainf_f_tavg, SWdown_f_tavg, oni, SPEI_1_June, SPEI_1_July, SPEI_6_June, SPEI_6_July, faux_demarage, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                safe_float(row.get('YEAR')),
                safe_float(row.get('RH2M')),
                safe_float(row.get('PRECTOTCORR_SUM')),
                safe_float(row.get('GWETTOP')),
                safe_float(row.get('PS')),
                safe_float(row.get('T2M')),
                safe_float(row.get('WS2M')),
                safe_float(row.get('ssrn')),
                safe_float(row.get('lst_celsius')),
                safe_float(row.get('ndvi')),
                safe_float(row.get('sos_doy')),
                safe_float(row.get('Evap_tavg')),
                safe_float(row.get('LWdown_f_tavg')),
                safe_float(row.get('Qair_f_tavg')),
                safe_float(row.get('Qg_tavg')),
                safe_float(row.get('Rainf_f_tavg')),
                safe_float(row.get('SWdown_f_tavg')),
                safe_float(row.get('oni')),
                safe_float(row.get('SPEI_1_June')),
                safe_float(row.get('SPEI_1_July')),
                safe_float(row.get('SPEI_6_June')),
                safe_float(row.get('SPEI_6_July')),
                safe_float(row.get('faux_demarage')),
                dataset_path.as_posix(),
            ),
        )
    conn.commit()
    conn.close()
    print("Jeu de donnees faux demarrage charge dans rainy_season_model_data.")


def ingest_soil_fertility_and_augmented_data(db_path: Path):
    soil_files = [
        Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset\article 3 RTCNET\fertilite_senegal_biom.xlsx"),
        Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset\article 3 RTCNET\fichier_augmenté.xlsx"),
        Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset\article 3 RTCNET\dataset_fertilite.xlsx"),
    ]
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS soil_fertility (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            region TEXT,
            ph REAL,
            argile REAL,
            matiere_organique REAL,
            azote_n REAL,
            phosphore_p REAL,
            potassium_k REAL,
            latitude REAL,
            longitude REAL,
            soc REAL,
            biomasse REAL,
            fertilite REAL,
            culture_adaptee TEXT,
            source TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fertility_augmented_dataset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            row_index INTEGER,
            biomasse_organique_pct REAL,
            carbone_organique_pct REAL,
            fertilite_peu_fertile INTEGER,
            PC1 REAL,
            PC2 REAL,
            PC3 REAL,
            PC4 REAL,
            PC5 REAL,
            raw_json TEXT
        )
    """)

    for file_path in soil_files:
        if not file_path.exists():
            continue
        try:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                df = xls.parse(sheet_name)
                if df.empty:
                    continue
                if "Fertilité" in df.columns or "Année" in df.columns or "Région" in df.columns:
                    for idx, row in df.iterrows():
                        year = safe_float(row.get('Année'))
                        region = row.get('Région')
                        ph_val = safe_float(row.get('pH'))
                        clay = safe_float(row.get('Argile'))
                        om = safe_float(row.get('Matière Organique'))
                        azote = safe_float(row.get('Azote (N)'))
                        phosphore = safe_float(row.get('Phosphore (P)'))
                        potassium = safe_float(row.get('Potassium (K)'))
                        lat = safe_float(row.get('Latitude'))
                        lon = safe_float(row.get('Longitude'))
                        soc = safe_float(row.get('SOC'))
                        biomass = safe_float(row.get('Biomasse '))
                        fertility = safe_float(row.get('Fertilité'))
                        crop = row.get('Culture Adaptée')
                        conn.execute(
                            "INSERT INTO soil_fertility(year, region, ph, argile, matiere_organique, azote_n, phosphore_p, potassium_k, latitude, longitude, soc, biomasse, fertilite, culture_adaptee, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                int(year) if year is not None else None,
                                str(region) if pd.notna(region) else None,
                                ph_val,
                                clay,
                                om,
                                azote,
                                phosphore,
                                potassium,
                                lat,
                                lon,
                                soc,
                                biomass,
                                fertility,
                                str(crop) if pd.notna(crop) else None,
                                file_path.as_posix(),
                            ),
                        )
                else:
                    for idx, row in df.iterrows():
                        conn.execute(
                            "INSERT INTO fertility_augmented_dataset(source_file, row_index, biomasse_organique_pct, carbone_organique_pct, fertilite_peu_fertile, PC1, PC2, PC3, PC4, PC5, raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                file_path.as_posix(),
                                int(idx),
                                safe_float(row.get('Biomasse_Organique_(%)')),
                                safe_float(row.get('Carbone_organique_(%)')),
                                safe_float(row.get('Fertilité_Peu fertile')),
                                safe_float(row.get('PC1')),
                                safe_float(row.get('PC2')),
                                safe_float(row.get('PC3')),
                                safe_float(row.get('PC4')),
                                safe_float(row.get('PC5')),
                                str(row.to_dict()),
                            ),
                        )
        except Exception as exc:
            print(f"Erreur lecture {file_path.name}: {exc}")
    conn.commit()
    conn.close()
    print("Donnees de fertilite et jeux augmentes charges dans soil_fertility et fertility_augmented_dataset.")


def ingest_spi_fleuve_senegal_indices(db_path: Path):
    candidates = [
        PROJECT_ROOT / "data" / "published_articles" / "article 4 PRedictSPI enhanced climat risk assesment tool" / "indices_fleuve_senegal_1990_2024.xlsx",
        Path(r"C:\Users\HP\Desktop\Mes Codes Recherche\Deja_publies_codes_dataset\article 4 PRedictSPI enhanced climat risk assesment tool\indices_fleuve_senegal_1990_2024.xlsx"),
    ]
    xlsx_path = next((p for p in candidates if p.exists()), None)
    if xlsx_path is None:
        print("Fichier indices_fleuve_senegal_1990_2024.xlsx absent.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spi_fleuve_senegal_indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            point_index INTEGER,
            b2 REAL,
            b3 REAL,
            b4 REAL,
            b8 REAL,
            evi REAL,
            msavi REAL,
            ndvi REAL,
            ndwi REAL,
            total_precip_mm REAL,
            spi REAL,
            period_start TEXT,
            period_end TEXT,
            region TEXT,
            source TEXT
        )
    """)
    conn.execute("DELETE FROM spi_fleuve_senegal_indices WHERE source = ?", (xlsx_path.as_posix(),))

    df = pd.read_excel(xlsx_path)
    for row_index, row in df.iterrows():
        conn.execute(
            "INSERT INTO spi_fleuve_senegal_indices(point_index, b2, b3, b4, b8, evi, msavi, ndvi, ndwi, total_precip_mm, spi, period_start, period_end, region, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                int(row_index),
                safe_float(row.get("B2")),
                safe_float(row.get("B3")),
                safe_float(row.get("B4")),
                safe_float(row.get("B8")),
                safe_float(row.get("EVI")),
                safe_float(row.get("MSAVI")),
                safe_float(row.get("NDVI")),
                safe_float(row.get("NDWI")),
                safe_float(row.get("TotalPrecip")),
                safe_float(row.get("SPI")),
                "1990-06-01",
                "2024-10-31",
                "Senegal River Valley",
                xlsx_path.as_posix(),
            ),
        )

    conn.commit()
    conn.close()
    print("Indices SPI du fleuve Senegal charges dans spi_fleuve_senegal_indices.")


if __name__ == "__main__":
    ingest_climate_data(DB_PATH)
    ingest_agricultural_data(DB_PATH)
    ingest_vector_metadata(DB_PATH)
    ingest_water_points(DB_PATH)
    ingest_soils_data(DB_PATH)
    ingest_spectral_indices_data(DB_PATH)
    ingest_spectral_indices_from_train_data(DB_PATH)
    ingest_millet_yields(DB_PATH)
    ingest_livestock_units_data(DB_PATH)
    ingest_remote_sensing_metadata(DB_PATH)
    ingest_oni_data(DB_PATH)
    ingest_power_climate_data(DB_PATH)
    ingest_rainy_season_model_dataset(DB_PATH)
    ingest_soil_fertility_and_augmented_data(DB_PATH)
    ingest_spi_fleuve_senegal_indices(DB_PATH)
    print("Import local termine.")
