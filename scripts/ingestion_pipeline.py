from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sqlite3
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover - exercised in runtime checks
    pd = None
    PANDAS_IMPORT_ERROR = exc
else:
    PANDAS_IMPORT_ERROR = None

try:
    import geopandas as gpd
except Exception:
    gpd = None

try:
    import rasterio
except Exception:
    rasterio = None

try:
    import fiona
except Exception:
    fiona = None


TABULAR_EXTENSIONS = {".csv", ".xls", ".xlsx"}
VECTOR_EXTENSIONS = {".shp", ".gpkg"}
RASTER_EXTENSIONS = {".tif", ".tiff"}
ARCHIVE_EXTENSIONS = {".zip"}
SUPPORTED_EXTENSIONS = TABULAR_EXTENSIONS | VECTOR_EXTENSIONS | RASTER_EXTENSIONS | ARCHIVE_EXTENSIONS
YEAR_COLUMN_RE = re.compile(r"^(19|20)\d{2}$")
NORMALIZED_YEAR_COLUMN_RE = re.compile(r"^(?:year|column|field)_(19|20)\d{2}$")

TEMPORAL_HINTS = ("date", "time", "year", "annee", "mois", "month", "jour")
SPATIAL_HINTS = ("lat", "lon", "lng", "long", "x", "y", "geom", "shape", "wkt", "crs")
ADMIN_HINTS = ("region", "depart", "commune", "arrond", "village", "station", "local", "zone")
MEASURE_HINTS = ("mm", "temp", "value", "count", "qty", "surface", "prod", "yield", "rain")

SHAPEFILE_SIDECAR_EXTENSIONS = {".dbf", ".shx", ".prj", ".cpg", ".qix", ".sbn", ".sbx", ".shp.xml"}


@dataclass
class PipelineConfig:
    project_root: Path
    source_dir: Path
    db_path: Path
    report_path: Path
    workspace_dir: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_name(value: str, prefix: str = "field") -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.strip().lower().replace("\ufeff", "")
    if YEAR_COLUMN_RE.match(text):
        return f"year_{text}"
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = prefix
    if text[0].isdigit():
        text = f"{prefix}_{text}"
    return text[:120]


def uniquify_names(names: list[str], prefix: str = "field") -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        base = normalize_name(name, prefix=prefix)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.append(base if count == 0 else f"{base}_{count + 1}")
    return result


def detect_file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TABULAR_EXTENSIONS:
        return "tabular"
    if suffix in VECTOR_EXTENSIONS:
        return "vector"
    if suffix in RASTER_EXTENSIONS:
        return "raster"
    if suffix in ARCHIVE_EXTENSIONS:
        return "archive"
    return "unsupported"


def detect_csv_options(path: Path) -> dict[str, str]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    sample = None
    encoding = "utf-8-sig"
    for candidate in encodings:
        try:
            with path.open("r", encoding=candidate, errors="strict") as handle:
                sample = handle.read(4096)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if sample is None:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            sample = handle.read(4096)
        encoding = "utf-8"

    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        if sample.count(";") > sample.count(","):
            delimiter = ";"

    decimal = "," if delimiter == ";" and re.search(r"\d,\d", sample) else "."
    return {"encoding": encoding, "delimiter": delimiter, "decimal": decimal}


def infer_sqlite_type(series: "pd.Series") -> str:
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    return "TEXT"


def infer_semantic_role(column_name: str, series: "pd.Series") -> str:
    name = column_name.lower()
    if any(token in name for token in TEMPORAL_HINTS) or YEAR_COLUMN_RE.match(name) or NORMALIZED_YEAR_COLUMN_RE.match(name):
        return "temporal"
    if any(token in name for token in SPATIAL_HINTS):
        return "spatial"
    if any(token in name for token in ADMIN_HINTS):
        return "administrative"
    if pd.api.types.is_numeric_dtype(series) or any(token in name for token in MEASURE_HINTS):
        return "measure"
    return "attribute"


def ensure_pandas() -> None:
    if pd is None:
        message = "pandas is required for tabular ingestion. Install requirements.txt before running the pipeline."
        if PANDAS_IMPORT_ERROR is not None:
            message = f"{message} Original import error: {PANDAS_IMPORT_ERROR}"
        raise RuntimeError(message)


def ensure_parent_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


class MultimodalIngestionPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.report: dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": utc_now(),
            "source_dir": str(self.config.source_dir),
            "db_path": str(self.config.db_path),
            "workspace_dir": str(self.config.workspace_dir),
            "files_found": [],
            "tables_created": [],
            "warnings": [],
            "errors": [],
        }
        self.conn: sqlite3.Connection | None = None
        self._table_names_seen: set[str] = set()

    def run(self) -> dict[str, Any]:
        ensure_parent_directory(self.config.db_path)
        ensure_parent_directory(self.config.report_path)
        self.config.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.config.db_path)
        try:
            self._initialize_schema()
            self._register_run(status="running")
            for file_path in self._discover_files():
                self._process_file(file_path)
            self._register_run(status="completed", finished_at=utc_now())
        except Exception as exc:
            self.report["errors"].append({"scope": "run", "message": str(exc)})
            self._register_run(status="failed", finished_at=utc_now())
            raise
        finally:
            self.report["finished_at"] = utc_now()
            self._write_report()
            if self.conn is not None:
                self.conn.close()
                self.conn = None
        return self.report

    def _initialize_schema(self) -> None:
        assert self.conn is not None
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                source_dir TEXT NOT NULL,
                db_path TEXT NOT NULL,
                report_path TEXT NOT NULL,
                status TEXT NOT NULL,
                warnings_count INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS data_sources (
                source_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_path TEXT NOT NULL,
                detected_type TEXT NOT NULL,
                parent_archive TEXT,
                extracted_path TEXT,
                size_bytes INTEGER,
                sha256 TEXT,
                modified_at TEXT,
                status TEXT NOT NULL,
                message TEXT,
                discovered_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS table_catalog (
                catalog_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                source_id INTEGER,
                table_name TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                column_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS column_catalog (
                column_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                original_name TEXT NOT NULL,
                inferred_type TEXT NOT NULL,
                semantic_role TEXT NOT NULL,
                null_count INTEGER NOT NULL DEFAULT 0,
                unique_count INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geospatial_layers (
                layer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                source_id INTEGER,
                table_name TEXT,
                layer_name TEXT NOT NULL,
                source_path TEXT NOT NULL,
                geometry_types TEXT,
                feature_count INTEGER,
                crs TEXT,
                bounds TEXT,
                storage_format TEXT,
                status TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS raster_catalog (
                raster_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                source_id INTEGER,
                layer_name TEXT NOT NULL,
                source_path TEXT NOT NULL,
                driver TEXT,
                crs TEXT,
                width INTEGER,
                height INTEGER,
                band_count INTEGER,
                dtype TEXT,
                bounds TEXT,
                status TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def _register_run(self, status: str, finished_at: str | None = None) -> None:
        assert self.conn is not None
        self.conn.execute(
            """
            INSERT INTO ingestion_runs (
                run_id, started_at, finished_at, source_dir, db_path, report_path, status, warnings_count, errors_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                finished_at=excluded.finished_at,
                status=excluded.status,
                warnings_count=excluded.warnings_count,
                errors_count=excluded.errors_count
            """,
            (
                self.run_id,
                self.report["started_at"],
                finished_at,
                str(self.config.source_dir),
                str(self.config.db_path),
                str(self.config.report_path),
                status,
                len(self.report["warnings"]),
                len(self.report["errors"]),
            ),
        )
        self.conn.commit()

    def _discover_files(self) -> list[Path]:
        excluded_roots = {
            self.config.db_path.parent.resolve(),
            self.config.report_path.parent.resolve(),
            self.config.workspace_dir.resolve(),
        }
        results: list[Path] = []
        for path in sorted(self.config.source_dir.rglob("*")):
            if not path.is_file():
                continue
            if any(path.resolve().is_relative_to(root) for root in excluded_roots):
                continue
            if any(part.startswith(".") for part in path.parts if part not in {".", ".."}):
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            results.append(path)
            self.report["files_found"].append(
                {
                    "path": str(path),
                    "detected_type": detect_file_type(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        return results

    def _process_file(self, path: Path) -> None:
        file_type = detect_file_type(path)
        if file_type == "archive":
            self._process_archive(path)
            return

        source_id = self._record_source(
            source_name=path.name,
            source_path=str(path),
            detected_type=file_type,
            parent_archive=None,
            extracted_path=None,
            size_bytes=path.stat().st_size,
            modified_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            status="discovered",
            message=None,
        )
        self._process_registered_source(path, source_id, file_type, original_reference=str(path))

    def _process_archive(self, archive_path: Path) -> None:
        source_id = self._record_source(
            source_name=archive_path.name,
            source_path=str(archive_path),
            detected_type="archive",
            parent_archive=None,
            extracted_path=None,
            size_bytes=archive_path.stat().st_size,
            modified_at=datetime.fromtimestamp(archive_path.stat().st_mtime, timezone.utc).isoformat(),
            status="extracted",
            message=None,
        )

        extract_root = self.config.workspace_dir / self.run_id / normalize_name(archive_path.stem, prefix="archive")
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(archive_path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/") and "__MACOSX" not in name]
            archive.extractall(extract_root, members=members)

        nested_paths = sorted(
            path for path in extract_root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS - ARCHIVE_EXTENSIONS
        )
        for extracted_path in nested_paths:
            child_source_id = self._record_source(
                source_name=extracted_path.name,
                source_path=f"{archive_path}!{extracted_path.relative_to(extract_root).as_posix()}",
                detected_type=detect_file_type(extracted_path),
                parent_archive=str(archive_path),
                extracted_path=str(extracted_path),
                size_bytes=extracted_path.stat().st_size,
                modified_at=datetime.fromtimestamp(extracted_path.stat().st_mtime, timezone.utc).isoformat(),
                status="discovered",
                message=None,
            )
            self._process_registered_source(
                extracted_path,
                child_source_id,
                detect_file_type(extracted_path),
                original_reference=f"{archive_path}!{extracted_path.relative_to(extract_root).as_posix()}",
            )

    def _process_registered_source(self, path: Path, source_id: int, file_type: str, original_reference: str) -> None:
        try:
            if file_type == "tabular":
                self._process_tabular(path, source_id, original_reference)
            elif file_type == "vector":
                self._process_vector(path, source_id, original_reference)
            elif file_type == "raster":
                self._process_raster(path, source_id, original_reference)
        except Exception as exc:
            self._update_source_status(source_id, "failed", str(exc))
            self.report["errors"].append({"source": original_reference, "message": str(exc)})
        else:
            self._update_source_status(source_id, "ingested", None)

    def _record_source(
        self,
        *,
        source_name: str,
        source_path: str,
        detected_type: str,
        parent_archive: str | None,
        extracted_path: str | None,
        size_bytes: int | None,
        modified_at: str | None,
        status: str,
        message: str | None,
    ) -> int:
        assert self.conn is not None
        sha256 = None
        if extracted_path and Path(extracted_path).exists():
            sha256 = self._hash_file(Path(extracted_path))
        elif Path(source_path).exists():
            sha256 = self._hash_file(Path(source_path))
        cursor = self.conn.execute(
            """
            INSERT INTO data_sources (
                run_id, source_name, source_path, detected_type, parent_archive, extracted_path,
                size_bytes, sha256, modified_at, status, message, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                source_name,
                source_path,
                detected_type,
                parent_archive,
                extracted_path,
                size_bytes,
                sha256,
                modified_at,
                status,
                message,
                utc_now(),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def _update_source_status(self, source_id: int, status: str, message: str | None) -> None:
        assert self.conn is not None
        self.conn.execute("UPDATE data_sources SET status = ?, message = ? WHERE source_id = ?", (status, message, source_id))
        self.conn.commit()

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _process_tabular(self, path: Path, source_id: int, source_reference: str) -> None:
        ensure_pandas()
        sheets = self._read_tabular(path)
        for sheet_name, frame, cleanup_actions in sheets:
            original_columns = [str(column) for column in frame.columns]
            cleaned = self._clean_dataframe(frame)
            table_name = self._make_table_name(path, sheet_name)
            self._write_dataframe(cleaned, table_name)
            self._catalog_table(source_id, table_name, "tabular", cleaned, notes="; ".join(cleanup_actions))
            self._catalog_columns(table_name, original_columns, cleaned)
            self.report["tables_created"].append(
                {
                    "source": source_reference,
                    "table_name": table_name,
                    "row_count": int(len(cleaned.index)),
                    "column_count": int(len(cleaned.columns)),
                    "cleanup_actions": cleanup_actions,
                }
            )

            long_table = self._create_long_year_table(cleaned)
            if long_table is not None:
                long_name = self._dedupe_table_name(f"{table_name}_long")
                self._write_dataframe(long_table, long_name)
                self._catalog_table(source_id, long_name, "tabular_long", long_table, notes="Normalized wide year columns")
                self._catalog_columns(long_name, list(long_table.columns), long_table)
                self.report["tables_created"].append(
                    {
                        "source": source_reference,
                        "table_name": long_name,
                        "row_count": int(len(long_table.index)),
                        "column_count": int(len(long_table.columns)),
                        "cleanup_actions": ["melted year columns to long format"],
                    }
                )

    def _read_tabular(self, path: Path) -> list[tuple[str, "pd.DataFrame", list[str]]]:
        assert pd is not None
        suffix = path.suffix.lower()
        if suffix == ".csv":
            options = detect_csv_options(path)
            frame = pd.read_csv(
                path,
                sep=options["delimiter"],
                encoding=options["encoding"],
                decimal=options["decimal"],
            )
            return [("main", frame, [f"read csv delimiter={options['delimiter']}", f"encoding={options['encoding']}"])]

        workbook = pd.ExcelFile(path)
        sheets: list[tuple[str, "pd.DataFrame", list[str]]] = []
        for sheet_name in workbook.sheet_names:
            frame = workbook.parse(sheet_name=sheet_name)
            sheets.append((sheet_name, frame, [f"read excel sheet={sheet_name}"]))
        return sheets

    def _clean_dataframe(self, frame: "pd.DataFrame") -> "pd.DataFrame":
        assert pd is not None
        cleaned = frame.copy()
        cleaned.columns = uniquify_names([str(column) for column in cleaned.columns], prefix="column")
        cleaned = cleaned.dropna(axis=1, how="all")
        for column in cleaned.columns:
            series = cleaned[column]
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                normalized = (
                    series.astype("string")
                    .str.replace("\u00a0", " ", regex=False)
                    .str.strip()
                    .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NaT": pd.NA})
                )
                numeric_candidate = pd.to_numeric(
                    normalized.str.replace(" ", "", regex=False).str.replace(",", ".", regex=False),
                    errors="coerce",
                )
                if normalized.notna().sum() and numeric_candidate.notna().sum() / normalized.notna().sum() >= 0.85:
                    if numeric_candidate.dropna().apply(float.is_integer).all():
                        cleaned[column] = numeric_candidate.astype("Int64")
                    else:
                        cleaned[column] = numeric_candidate.astype(float)
                    continue

                datetime_candidate = pd.to_datetime(normalized, errors="coerce", utc=False, format="mixed")
                if normalized.notna().sum() and datetime_candidate.notna().sum() / normalized.notna().sum() >= 0.85:
                    cleaned[column] = datetime_candidate.dt.strftime("%Y-%m-%d %H:%M:%S").replace("NaT", pd.NA)
                    continue
                cleaned[column] = normalized
        return cleaned

    def _create_long_year_table(self, frame: "pd.DataFrame") -> "pd.DataFrame | None":
        assert pd is not None
        year_columns = [column for column in frame.columns if NORMALIZED_YEAR_COLUMN_RE.match(str(column)) or YEAR_COLUMN_RE.match(str(column))]
        if len(year_columns) < 2:
            return None
        if len(year_columns) < max(2, len(frame.columns) // 2):
            return None
        id_columns = [column for column in frame.columns if column not in year_columns]
        long_frame = frame.melt(id_vars=id_columns, value_vars=year_columns, var_name="year", value_name="value")
        long_frame["year"] = long_frame["year"].astype("string").str.extract(r"((?:19|20)\d{2})", expand=False)
        long_frame["year"] = pd.to_numeric(long_frame["year"], errors="coerce").astype("Int64")
        return long_frame

    def _process_vector(self, path: Path, source_id: int, source_reference: str) -> None:
        if gpd is None:
            message = "geopandas/fiona not available; vector layer catalogued without geometry ingestion"
            self._catalog_geospatial_layer(
                source_id=source_id,
                table_name=None,
                layer_name=path.stem,
                source_path=source_reference,
                geometry_types=None,
                feature_count=None,
                crs=None,
                bounds=None,
                storage_format=None,
                status="skipped_missing_dependency",
                message=message,
            )
            self.report["warnings"].append({"source": source_reference, "message": message})
            return

        layers = [None]
        if path.suffix.lower() == ".gpkg" and fiona is not None:
            layers = list(fiona.listlayers(path))

        for layer in layers:
            layer_label = layer or path.stem
            geodata = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
            cleaned = geodata.copy()
            geometry = cleaned.geometry if "geometry" in cleaned else None
            if geometry is not None:
                cleaned = cleaned.drop(columns="geometry")
                cleaned["geometry_wkt"] = geometry.apply(lambda value: value.wkt if value is not None else None)
                cleaned["geometry_type"] = geometry.geom_type
            cleaned = self._clean_dataframe(cleaned)
            table_name = self._make_table_name(path, layer_label)
            self._write_dataframe(cleaned, table_name)
            self._catalog_table(source_id, table_name, "vector", cleaned, notes="geometry stored as WKT")
            self._catalog_columns(table_name, list(cleaned.columns), cleaned)

            geometry_types = None
            bounds = None
            feature_count = len(geodata.index)
            crs = str(geodata.crs) if getattr(geodata, "crs", None) is not None else None
            if geometry is not None:
                geometry_types = ", ".join(sorted(set(geometry.geom_type.dropna().astype(str))))
                bounds_values = geodata.total_bounds.tolist() if not geodata.empty else []
                bounds = json.dumps(bounds_values)

            self._catalog_geospatial_layer(
                source_id=source_id,
                table_name=table_name,
                layer_name=layer_label,
                source_path=source_reference,
                geometry_types=geometry_types,
                feature_count=feature_count,
                crs=crs,
                bounds=bounds,
                storage_format="WKT",
                status="ingested",
                message=None,
            )
            self.report["tables_created"].append(
                {
                    "source": source_reference,
                    "table_name": table_name,
                    "row_count": int(len(cleaned.index)),
                    "column_count": int(len(cleaned.columns)),
                    "cleanup_actions": ["stored geometry_wkt", "catalogued vector layer metadata"],
                }
            )

    def _process_raster(self, path: Path, source_id: int, source_reference: str) -> None:
        if rasterio is None:
            message = "rasterio not available; raster catalogued with file metadata only"
            self._catalog_raster(
                source_id=source_id,
                layer_name=path.stem,
                source_path=source_reference,
                driver=None,
                crs=None,
                width=None,
                height=None,
                band_count=None,
                dtype=None,
                bounds=None,
                status="skipped_missing_dependency",
                message=message,
            )
            self.report["warnings"].append({"source": source_reference, "message": message})
            return

        with rasterio.open(path) as dataset:
            self._catalog_raster(
                source_id=source_id,
                layer_name=path.stem,
                source_path=source_reference,
                driver=dataset.driver,
                crs=str(dataset.crs) if dataset.crs else None,
                width=dataset.width,
                height=dataset.height,
                band_count=dataset.count,
                dtype=",".join(dataset.dtypes),
                bounds=json.dumps(list(dataset.bounds)),
                status="catalogued",
                message=None,
            )

    def _make_table_name(self, path: Path, sheet_name: str | None = None) -> str:
        parts = [normalize_name(path.stem, prefix="table")]
        if sheet_name and sheet_name not in {"main", path.stem}:
            parts.append(normalize_name(sheet_name, prefix="sheet"))
        return self._dedupe_table_name("_".join(parts))

    def _dedupe_table_name(self, base_name: str) -> str:
        candidate = normalize_name(base_name, prefix="table")
        index = 2
        while candidate in self._table_names_seen:
            candidate = f"{normalize_name(base_name, prefix='table')}_{index}"
            index += 1
        self._table_names_seen.add(candidate)
        return candidate

    def _write_dataframe(self, frame: "pd.DataFrame", table_name: str) -> None:
        assert self.conn is not None
        frame.to_sql(table_name, self.conn, if_exists="replace", index=False)
        self.conn.commit()

    def _catalog_table(self, source_id: int, table_name: str, source_kind: str, frame: "pd.DataFrame", notes: str | None) -> None:
        assert self.conn is not None
        self.conn.execute(
            """
            INSERT INTO table_catalog (run_id, source_id, table_name, source_kind, row_count, column_count, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                source_id,
                table_name,
                source_kind,
                int(len(frame.index)),
                int(len(frame.columns)),
                "created",
                notes,
                utc_now(),
            ),
        )
        self.conn.commit()

    def _catalog_columns(self, table_name: str, original_columns: list[str], frame: "pd.DataFrame") -> None:
        assert self.conn is not None
        for original_name, column_name in zip(original_columns, frame.columns):
            series = frame[column_name]
            self.conn.execute(
                """
                INSERT INTO column_catalog (
                    run_id, table_name, column_name, original_name, inferred_type, semantic_role, null_count, unique_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    table_name,
                    str(column_name),
                    str(original_name),
                    infer_sqlite_type(series),
                    infer_semantic_role(str(column_name), series),
                    int(series.isna().sum()),
                    int(series.nunique(dropna=True)),
                    utc_now(),
                ),
            )
        self.conn.commit()

    def _catalog_geospatial_layer(
        self,
        *,
        source_id: int,
        table_name: str | None,
        layer_name: str,
        source_path: str,
        geometry_types: str | None,
        feature_count: int | None,
        crs: str | None,
        bounds: str | None,
        storage_format: str | None,
        status: str,
        message: str | None,
    ) -> None:
        assert self.conn is not None
        self.conn.execute(
            """
            INSERT INTO geospatial_layers (
                run_id, source_id, table_name, layer_name, source_path, geometry_types, feature_count,
                crs, bounds, storage_format, status, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                source_id,
                table_name,
                layer_name,
                source_path,
                geometry_types,
                feature_count,
                crs,
                bounds,
                storage_format,
                status,
                message,
                utc_now(),
            ),
        )
        self.conn.commit()

    def _catalog_raster(
        self,
        *,
        source_id: int,
        layer_name: str,
        source_path: str,
        driver: str | None,
        crs: str | None,
        width: int | None,
        height: int | None,
        band_count: int | None,
        dtype: str | None,
        bounds: str | None,
        status: str,
        message: str | None,
    ) -> None:
        assert self.conn is not None
        self.conn.execute(
            """
            INSERT INTO raster_catalog (
                run_id, source_id, layer_name, source_path, driver, crs, width, height, band_count, dtype, bounds, status, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                source_id,
                layer_name,
                source_path,
                driver,
                crs,
                width,
                height,
                band_count,
                dtype,
                bounds,
                status,
                message,
                utc_now(),
            ),
        )
        self.conn.commit()

    def _write_report(self) -> None:
        self.report["summary"] = {
            "files_found": len(self.report["files_found"]),
            "tables_created": len(self.report["tables_created"]),
            "warnings": len(self.report["warnings"]),
            "errors": len(self.report["errors"]),
        }
        with self.config.report_path.open("w", encoding="utf-8") as handle:
            json.dump(self.report, handle, ensure_ascii=False, indent=2)


def default_config(project_root: Path) -> PipelineConfig:
    upload_dir = project_root / "upload"
    source_dir = upload_dir if upload_dir.exists() else project_root
    return PipelineConfig(
        project_root=project_root,
        source_dir=source_dir,
        db_path=project_root / "data" / "multimodal_base.sqlite",
        report_path=project_root / "reports" / "latest_ingestion_report.json",
        workspace_dir=project_root / "data" / "workspace",
    )
