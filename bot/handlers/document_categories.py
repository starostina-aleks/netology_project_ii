from app.core.config import get_settings
import json
from pathlib import Path

settings = get_settings()

def get_top_level_categories() -> list[str]:
    json_path=settings.rag_data_dir/"documents.json"
    with Path(json_path).open("r", encoding="utf-8") as f:
        data = json.load(f)

    categories = {
        doc["category"].split("/", maxsplit=1)[0].strip()
        for doc in data["documents"]
        if doc.get("category", "").strip()
    }

    return sorted(categories)