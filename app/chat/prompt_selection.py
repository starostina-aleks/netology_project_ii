import hashlib
from app.chat.domain import SystemPrompt

def choose_by_split(
        owner_external_id:str,
        candidates:list[SystemPrompt],
    )->SystemPrompt | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    bucket = int(
        hashlib.sha256(owner_external_id.encode()).hexdigest()[:8],16
    ) % 100
    cumulative = 0
    for candidate in candidates:
        cumulative += candidate.traffic_pct
        if cumulative > bucket:
            return candidate
    return candidates[0]