import os
import tempfile

import numpy as np
import pytest

from semantic_search.vectorstores.faiss_store import (
    NumpyVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)


def test_add_and_query_records() -> None:
    store = NumpyVectorStore(dimension=3, metric="l2")
    records = [
        VectorRecord("a", [1.0, 0.0, 0.0], {"tag": "alpha"}),
        VectorRecord("b", [0.0, 1.0, 0.0], {"tag": "beta"}),
        VectorRecord("c", [0.0, 0.0, 1.0], {"tag": "gamma"}),
    ]
    store.add(records)

    results = store.query([1.0, 0.0, 0.1], k=2)
    assert len(results) == 2
    assert results[0].record_id == "a"
    assert results[0].metadata["tag"] == "alpha"


def test_upsert_replaces_existing_vector() -> None:
    store = NumpyVectorStore(dimension=2)
    store.add([VectorRecord("doc-1", [1.0, 0.0], {})])
    store.upsert([VectorRecord("doc-1", [0.0, 1.0], {"updated": True})])

    result = store.query([0.0, 1.0], k=1)[0]
    assert result.record_id == "doc-1"
    assert result.metadata["updated"] is True


def test_delete_removes_vectors() -> None:
    store = NumpyVectorStore(dimension=2)
    store.add(
        [
            VectorRecord("x", [1.0, 0.0], {}),
            VectorRecord("y", [0.0, 1.0], {}),
        ]
    )
    store.delete(["x"])
    results = store.query([1.0, 0.0], k=2)
    assert all(res.record_id != "x" for res in results)


def test_query_with_filter_function() -> None:
    store = NumpyVectorStore(dimension=2)
    store.add(
        [
            VectorRecord("keep", [0.9, 0.1], {"keep": True}),
            VectorRecord("skip", [0.9, 0.1], {"keep": False}),
        ]
    )

    def filter_fn(result: QueryResult) -> bool:
        return result.metadata.get("keep", False)

    results = store.query([1.0, 0.0], k=5, filter_fn=filter_fn)
    assert len(results) == 1
    assert results[0].record_id == "keep"


def test_save_and_load_roundtrip(tmp_path) -> None:
    store = NumpyVectorStore(dimension=2)
    store.add(
        [
            VectorRecord("p", [0.5, 0.5], {"meta": "p"}),
            VectorRecord("q", [0.1, 0.9], {"meta": "q"}),
        ]
    )

    store_path = tmp_path / "vector_store"
    store.save(str(store_path))

    loaded = NumpyVectorStore.load(str(store_path))
    results = loaded.query([0.5, 0.4], k=2)
    assert {res.record_id for res in results} == {"p", "q"}


def test_load_missing_files_raises(tmp_path) -> None:
    store_path = tmp_path / "missing_store"
    with pytest.raises(VectorStoreError):
        NumpyVectorStore.load(str(store_path))


def test_invalid_dimension_raises() -> None:
    store = NumpyVectorStore(dimension=3)
    with pytest.raises(ValueError):
        store.add([VectorRecord("bad", [1.0, 0.0], {})])


def test_query_returns_empty_when_store_empty() -> None:
    store = NumpyVectorStore(dimension=3)
    assert store.query([1.0, 0.0, 0.0], k=5) == []


def test_cosine_metric_orders_results() -> None:
    store = NumpyVectorStore(dimension=2, metric="cosine")
    store.add(
        [
            VectorRecord("x", [1.0, 0.0], {}),
            VectorRecord("y", [0.0, 1.0], {}),
        ]
    )

    results = store.query([0.9, 0.1], k=2)
    assert [res.record_id for res in results] == ["x", "y"]


def test_inner_product_metric_orders_results() -> None:
    store = NumpyVectorStore(dimension=2, metric="inner_product")
    store.add(
        [
            VectorRecord("m", [0.2, 0.8], {}),
            VectorRecord("n", [0.9, 0.1], {}),
        ]
    )

    results = store.query([0.1, 0.99], k=2)
    assert [res.record_id for res in results] == ["m", "n"]
