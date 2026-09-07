import pytest

import datetime
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from tests.conftest import vector_store,temp_collection_name
from app.services.vector_store import VectorStore,VectorStoreDimensionMismatch

async def test_vector_store_happy_path(vector_store):
    """Позитивный сценарий: создание, вставка, подсчет и поиск."""
    await vector_store.ensure_collection()

    test_points = [
        PointStruct(
            id=1, vector=[1.0, 0.0, 0.0, 0.0],
            payload={"source": "v1", "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "category": "A"}
        ),
        PointStruct(
            id=2, vector=[0.0, 1.0, 0.0, 0.0],
            payload={"source": "v2", "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     "category": "B"}
        )
    ]

    await vector_store.upsert(points=test_points, batch_size=1)
    count,_,_= await vector_store.get_params()
    assert  count == 2

    # Базовый поиск
    res = await vector_store.search(query_vector=[0.9, 0.1, 0.0, 0.0], top_k=1)
    assert res[0].id == 1


async def test_search_with_metadata_filter(vector_store):
    """Интеграционный тест: проверка фильтрации по метаданным (payload)."""
    await vector_store.ensure_collection()

    # Добавляем две точки. Векторно точка 2 дальше от запроса, но она подходит по фильтру
    test_points = [
        PointStruct(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload={"category": "A", "source": "v1"}),
        PointStruct(id=2, vector=[0.0, 1.0, 0.0, 0.0], payload={"category": "B", "source": "v2"})
    ]
    await vector_store.upsert(points=test_points)

    # Ищем вектор, который ближе к ID 1, но ставим жесткий фильтр на категорию 'B'
    search_filter = Filter(
        must=[
            FieldCondition(key="category", match=MatchValue(value="B"))
        ]
    )

    res = await vector_store.search(
        query_vector=[0.9, 0.1, 0.0, 0.0],
        top_k=1,
        query_filter=search_filter
    )

    # База обязана проигнорировать ближайший вектор 1 и вернуть вектор 2 из-за фильтра
    assert len(res) == 1
    assert res[0].id == 2, "Фильтрация Qdrant не сработала, вернулся вектор с неверной категорией"


async def test_dimension_mismatch_raises_exception(vector_store, pre_vector_store, temp_collection_name):
    """Негативный тест: проверка защиты от несовпадения размерности векторов."""

    await pre_vector_store.ensure_collection()
    await pre_vector_store.close()

     # Проверяем, что метод .ensure_collection() выбросит кастомное исключение
    with pytest.raises(VectorStoreDimensionMismatch) as exc_info:
        await vector_store.ensure_collection()

    # Проверяем текст ошибки, чтобы убедиться, что сработало именно наше условие
    assert f"Коллекция '{temp_collection_name}' имеет dim=1536" in str(exc_info.value)

    await vector_store.close()



