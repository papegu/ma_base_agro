from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from inspect_multimodal_database import main


if __name__ == "__main__":
    raise SystemExit(main())
