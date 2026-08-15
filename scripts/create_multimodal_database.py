from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion_pipeline import MultimodalIngestionPipeline, PipelineConfig, default_config


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    defaults = default_config(project_root)
    parser = argparse.ArgumentParser(description="Scan, clean, and ingest multimodal agro data into SQLite.")
    parser.add_argument("--source-dir", default=str(defaults.source_dir), help="Directory to scan (defaults to upload/ if present, else repo root).")
    parser.add_argument("--db-path", default=str(defaults.db_path), help="SQLite database output path.")
    parser.add_argument("--report-path", default=str(defaults.report_path), help="JSON scan/ingestion report output path.")
    parser.add_argument("--workspace-dir", default=str(defaults.workspace_dir), help="Workspace for extracted archives.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config = PipelineConfig(
        project_root=project_root,
        source_dir=Path(args.source_dir).resolve(),
        db_path=Path(args.db_path).resolve(),
        report_path=Path(args.report_path).resolve(),
        workspace_dir=Path(args.workspace_dir).resolve(),
    )
    report = MultimodalIngestionPipeline(config).run()
    summary = report.get("summary", {})
    status = "terminée avec succès" if summary.get("errors", 0) == 0 else "terminée avec erreurs"
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Ingestion {status}: {config.db_path}")
    print(f"Rapport JSON: {config.report_path}")
    return 0 if summary.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
