import hashlib
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ARTICLE_ROOT = PROJECT_ROOT / "data" / "published_articles"
DB_PATH = PROJECT_ROOT / "data" / "multimodal_base.sqlite"

COPYABLE_EXTENSIONS = {
    ".py", ".ipynb", ".csv", ".xlsx", ".xls", ".txt", ".json",
    ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".zip",
    ".h5", ".dbf", ".shp", ".gpkg", ".geojson", ".gdb", ".html",
    ".pdf", ".yml", ".yaml"
}

EXCLUDED_DIRS = {"__pycache__", ".git", ".venv", ".idea", ".mypy_cache", ".ipynb_checkpoints", "node_modules"}


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".py":
        return "python_code"
    if suffix in {".ipynb"}:
        return "notebook_or_code"
    if suffix in {".csv", ".xlsx", ".xls", ".json", ".txt", ".md", ".yaml", ".yml"}:
        return "tabular_data"
    if suffix == ".pdf":
        return "pdf_article"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "image_output"
    if suffix in {".tif", ".tiff", ".shp", ".gpkg", ".geojson", ".dbf", ".gdb"}:
        return "geospatial_dataset"
    if suffix in {".h5", ".pkl", ".sav"}:
        return "model_artifact"
    if suffix == ".zip":
        return "archive"
    return "other"


def ensure_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_name TEXT NOT NULL,
            source_folder TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS article_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            extension TEXT,
            category TEXT,
            is_python INTEGER DEFAULT 0,
            is_excel INTEGER DEFAULT 0,
            is_pdf INTEGER DEFAULT 0,
            file_size_bytes INTEGER,
            sha256 TEXT,
            copied INTEGER DEFAULT 0,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES articles(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS article_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_root TEXT,
            source_path TEXT,
            stored_path TEXT,
            relative_path TEXT,
            file_name TEXT,
            extension TEXT,
            file_size_bytes INTEGER,
            category TEXT,
            is_code INTEGER,
            is_tabular INTEGER,
            is_geospatial INTEGER,
            sha256 TEXT,
            copied INTEGER,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def iter_article_dirs(root: Path):
    if not root.exists():
        return []
    return [p for p in sorted(root.iterdir()) if p.is_dir() and p.name not in EXCLUDED_DIRS]


def index_dataset(root: Path):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    ensure_schema(conn)

    if not root.exists():
        print(f"Dossier source introuvable: {root}")
        conn.close()
        return 0

    article_count = 0
    file_count = 0

    for article_dir in iter_article_dirs(root):
        article_count += 1
        conn.execute(
            "INSERT INTO articles(article_name, source_folder) VALUES(?, ?)",
            (article_dir.name, str(article_dir)),
        )
        article_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for file_path in sorted(article_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if any(part in EXCLUDED_DIRS for part in file_path.parts):
                continue
            suffix = file_path.suffix.lower()
            if suffix in {".pyc", ".pyo", ".so", ".dll", ".exe", ".class"}:
                continue
            if suffix not in COPYABLE_EXTENSIONS:
                continue

            rel_path = str(file_path.relative_to(article_dir))
            category = classify_file(file_path)
            file_size = file_path.stat().st_size
            file_count += 1

            conn.execute(
                """
                INSERT INTO article_files(
                    article_id, file_name, relative_path, extension, category,
                    is_python, is_excel, is_pdf, file_size_bytes, sha256, copied
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    article_id,
                    file_path.name,
                    rel_path,
                    suffix,
                    category,
                    int(suffix == ".py"),
                    int(suffix in {".xlsx", ".xls", ".csv"}),
                    int(suffix == ".pdf"),
                    file_size,
                    sha256_of_file(file_path),
                    1,
                ),
            )

            conn.execute(
                """
                INSERT INTO article_artifacts(
                    source_root, source_path, stored_path, relative_path, file_name,
                    extension, file_size_bytes, category, is_code, is_tabular,
                    is_geospatial, sha256, copied
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(root),
                    str(file_path),
                    str(file_path),
                    rel_path,
                    file_path.name,
                    suffix,
                    file_size,
                    category,
                    int(suffix == ".py"),
                    int(suffix in {".csv", ".xlsx", ".xls", ".json", ".txt", ".md", ".yaml", ".yml"}),
                    int(suffix in {".tif", ".tiff", ".shp", ".gpkg", ".geojson", ".dbf", ".gdb"}),
                    sha256_of_file(file_path),
                    1,
                ),
            )

    conn.commit()
    conn.close()
    print(f"Indexation terminee: {article_count} articles et {file_count} fichiers references dans la base")
    return article_count, file_count


if __name__ == "__main__":
    print(f"Dossier source: {ARTICLE_ROOT}")
    index_dataset(ARTICLE_ROOT)
