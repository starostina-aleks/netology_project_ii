import asyncio
from typing import Sequence
from sentence_transformers import SentenceTransformer
from pathlib import Path
import hashlib, json
from app.core.config import get_settings
import numpy as np
import time

#dim=768
class EmbeddingsClient:
    def __init__(
            self,
            model: SentenceTransformer,
            batch_size: int = 32,
            cache_dir: str = ".embedding_cache"
    ) -> None:
        self._model = model
        self._model_name = model[0].auto_model.config._name_or_path
        self._embedding_dim = model.get_embedding_dimension()
        self._batch_size = batch_size

        # Инициализация директории кеша
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def _encode_batch(self, batch: list[str]) -> list[list[float]]:

        embeddings = await asyncio.to_thread(
            self._model.encode,
            batch,
            normalize_embeddings=True,
            batch_size=len(batch),
            show_progress_bar=False
        )
        return embeddings.tolist()

    async def embed_cached(self,text: str,prompt_name: str = "") :
        if prompt_name:
            prepared_text = f"{prompt_name}: {text}"
        else:
            prepared_text = text

        key = hashlib.sha256(f"{self._model_name}|{self._embedding_dim}|{prepared_text}".encode()).hexdigest()
        path = self._cache_dir / f"{key}.json"
        if path.exists():
           return json.loads(path.read_text())
        vec = await self.embed_one(text,prompt_name=prompt_name)
        path.write_text(json.dumps(vec))
        return vec

    async def embed(self, texts: Sequence[str], prompt_name: str = "") -> list[list[float]]:
        if not texts:
            return []
        if prompt_name:
            prepared_texts = [f"{prompt_name}: {text}" for text in texts]
        else:
            prepared_texts = list(texts)
        return await self._encode_batch(prepared_texts)

    async def embed_query(self, text: str) -> list[float]:
        result = await self.embed([text], prompt_name="query")
        return result[0]


    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.embed(texts, prompt_name="passage")

    async def embed_one(self, text: str, prompt_name: str = "") -> list[float]:
        result = await self.embed([text], prompt_name=prompt_name)
        return result[0]

async def _smoke(client) -> None:
    mini_benchmark_path = "tests/eval/mini_benchmark.json"
    with open(mini_benchmark_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sim = lambda v1, v2: float(np.dot(v1, v2))
    gaps_pre, gaps_none = [], []
    start_time = time.perf_counter()
    for item in data:
        q, rel, irrel = item["query"], item["relevant"], item["irrelevant"]

        # С префиксами
        s_rel_p = sim(await client.embed_cached(q,"query"), await client.embed_cached(rel, "passage"))
        s_irr_p = sim(await client.embed_cached(q,"query"), await client.embed_cached(irrel, "passage"))
        gaps_pre.append(s_rel_p - s_irr_p)

        # Без префиксов
        s_rel_n = sim(await client.embed_cached(q), await client.embed_cached(rel))
        s_irr_n = sim(await client.embed_cached(q), await client.embed_cached(irrel))
        gaps_none.append(s_rel_n - s_irr_n)
    end_time = time.perf_counter()
    print(np.mean(gaps_pre) - np.mean(gaps_none))
    return end_time - start_time


async def main():
    settings = get_settings()
    model_path = settings.embedding_model
    model = SentenceTransformer(model_path)
    client = EmbeddingsClient(model)
    print(model.get_embedding_dimension())

    execution_time_1 = await _smoke(client)
    print(f"Время выполнения бенчмарка 1 (Холодный): {execution_time_1:.3f} сек.")

    execution_time_2 = await _smoke(client)
    print(f"Время выполнения бенчмарка 2 (Горячий): {execution_time_2:.3f} сек.")


if __name__ == "__main__":
    asyncio.run(main())


#0.0037056795146331867
#Время выполнения бенчмарка 1 (Холодный): 2.715 сек.
#0.0037056795146331867
#Время выполнения бенчмарка 2 (Горячий): 0.023 сек.