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
        print("self._embedding_dim=",self._embedding_dim)
        self._batch_size = batch_size

        # Инициализация директории кеша
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def _encode_batch(self, texts: list[str]) -> list[list[float]]:

        embeddings = await asyncio.to_thread(
            self._model.encode,
            texts,
            normalize_embeddings=True,
            batch_size=self._batch_size,
            show_progress_bar=True
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
    relevant_scores = []
    irrelevant_scores = []
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

        q_vec = await client.embed_cached(q, "query")
        rel_vec = await client.embed_cached(rel, "passage")
        irrel_vec = await client.embed_cached(irrel, "passage")
        relevant_scores.append(sim(q_vec, rel_vec))
        irrelevant_scores.append(sim(q_vec, irrel_vec))


    end_time = time.perf_counter()
    print("difference:", np.mean(gaps_pre) - np.mean(gaps_none))

    min_rel = min(relevant_scores)
    max_irrel = max(irrelevant_scores)

    print(f"Минимум релевантных (min_relevant):   {min_rel:.4f}")
    print(f"Максимум нерелевантных (max_irrelevant): {max_irrel:.4f}")
    threshold = 0
    if min_rel > max_irrel:
        # Идеальное разделение классов
        threshold = (min_rel + max_irrel) / 2
        print(f"✅ Классы идеально разделены!")
        print(f"Рекомендуемый порог (середина): {threshold:.4f}")

    else:
        # Диапазоны пересекаются (шум в данных)
        print(f"⚠️ Внимание: диапазоны пересекаются (min_rel < max_irrel).")
        # В случае пересечения часто берут среднее арифметическое между границами
        threshold = (min_rel + max_irrel) / 2
        print(f"Альтернативный порог (компромисс): {threshold:.4f}")


    return end_time - start_time


async def main():
    settings = get_settings()
    model_path = settings.embedding_model
    model = SentenceTransformer(model_path)
    client = EmbeddingsClient(model)

    execution_time_1 = await _smoke(client)
    print(f"Время выполнения бенчмарка 1 (Холодный): {execution_time_1:.3f} сек.")

    execution_time_2 = await _smoke(client)
    print(f"Время выполнения бенчмарка 2 (Горячий): {execution_time_2:.3f} сек.")


if __name__ == "__main__":
    asyncio.run(main())

"""
difference: 0.005959369927004715
Минимум релевантных (min_relevant):   0.8503
Максимум нерелевантных (max_irrelevant): 0.7864
✅ Классы идеально разделены!
Рекомендуемый порог (середина): 0.8183
Время выполнения бенчмарка 1 (Холодный): 9.208 сек.

difference: 0.005959369927004715
Минимум релевантных (min_relevant):   0.8503
Максимум нерелевантных (max_irrelevant): 0.7864
✅ Классы идеально разделены!
Рекомендуемый порог (середина): 0.8183
Время выполнения бенчмарка 2 (Горячий): 0.040 сек.
"""