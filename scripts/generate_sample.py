from pathlib import Path
from datetime import datetime, timezone
import re
import json

def split_markdown(md: str) -> list[dict]:
    pattern = r"(?=^#{1,6}\s+)"
    sections = re.split(pattern, md, flags=re.MULTILINE)

    chunks = []
    hierarchy = []

    for section in sections:
        section = section.strip()

        if not section:
            continue

        # Ищем заголовок
        match = re.match(r"^(#{1,6})\s+(.+)$", section, re.MULTILINE)

        if match:
            level = len(match.group(1))
            title = match.group(2).strip()

            # Убираем из hierarchy всё того же или более глубокого уровня
            hierarchy = hierarchy[:level - 1]
            hierarchy.append(title)

            chunks.append({
                "title": title,
                "level": level,
                "hierarchy": hierarchy.copy(),
                "text": section,
            })
        else:
            chunks.append({
                "title": None,
                "level": None,
                "hierarchy": hierarchy.copy(),
                "text": section,
            })

    return chunks

def split_text(folder:Path) :
    source_docs=[]
    for path in folder.glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        docs= split_markdown(text)
        created_at = datetime.now(timezone.utc).isoformat()
        for i,doc in enumerate(docs):
            category = re.split(r'(?<=[.!?])\s+', doc["hierarchy"][0])[0]  if doc["hierarchy"] else None
            source_docs.append({
                "id": f"{path.stem}_{i}",
                "source": str(path),
                "filename": path.name,
                "chunk_index": i,
                "title": doc["title"],
                "level": doc["level"],
                "tenant_id":1,
                "hierarchy": doc["hierarchy"],
                "text": doc["text"],
                "length": len(doc["text"]),
                "created_at": created_at,
                "category": category,
            })
    return source_docs

