from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="List SQLite tables and row counts.")
    parser.add_argument(
        "--db-path",
        default=str(project_root / "data" / "multimodal_base.sqlite"),
        help="SQLite database path to inspect.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).resolve()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        for (name,) in rows:
            if name.startswith("sqlite_"):
                continue
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            print(f"{name}: {count}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
