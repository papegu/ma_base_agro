import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ee

from config.project_config import EE_PROJECT_ID


def init_ee():
    try:
        ee.Initialize(project=EE_PROJECT_ID)
        return
    except Exception:
        try:
            ee.Initialize()
            return
        except Exception as exc:
            raise RuntimeError(
                "Earth Engine n'est pas authentifié ou n'est pas correctement configuré. "
                "Exécute d'abord: earthengine authenticate --project project37246"
            ) from exc


def iter_senegal_tasks():
    init_ee()
    tasks = ee.batch.Task.list()
    for task in tasks:
        status = task.status()
        desc = status.get("description", "")
        name = status.get("name", "")
        state = status.get("state", "UNKNOWN")
        dest = status.get("destination_uris", [])
        if "senegal" in desc.lower() or "senegal" in name.lower():
            yield status, task
        elif state in {"COMPLETED", "RUNNING", "READY", "FAILED", "CANCELLED"} and (
            "senegal" in str(dest).lower() or "senegal" in str(status).lower()
        ):
            yield status, task


if __name__ == "__main__":
    print("=== Vérification des exports Earth Engine ===")
    found = False
    for status, task in iter_senegal_tasks():
        found = True
        desc = status.get("description", "<sans description>")
        state = status.get("state", "UNKNOWN")
        destination = status.get("destination_uris", [])
        print(f"Task: {desc}")
        print(f"  state: {state}")
        print(f"  destination: {destination}")

    if not found:
        print("Aucune tâche GEE de type Senegal n'a été trouvée dans la liste actuelle.")
        print("Vérifie que tu as bien exécuté le script d'export et que l'authentification Earth Engine est active.")
