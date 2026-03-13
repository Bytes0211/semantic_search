"""Tests for the EmbeddingPipeline."""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

import pytest

from semantic_search.embeddings.base import EmbeddingInput, EmbeddingProvider, EmbeddingResult
from semantic_search.embeddings.spot import SpotEmbeddingProvider
from semantic_search.pipeline.embedding_pipeline import EmbeddingPipeline, PipelineResult
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

DIMENSION = 16


def _make_inputs(n: int, prefix: str = "doc") -> List[EmbeddingInput]:
    """Generate ``n`` deterministic EmbeddingInput records."""
    return [EmbeddingInput(record_id=f"{prefix}-{i}", text=f"text {i}") for i in range(n)]


def _make_pipeline(
    batch_size: int = 64,
    s3_bucket: str | None = None,
    s3_client: Any = None,
) -> tuple[EmbeddingPipeline, NumpyVectorStore]:
    provider = SpotEmbeddingProvider(dimension=DIMENSION, salt="test", normalize=True)
    store = NumpyVectorStore(dimension=DIMENSION)
    pipeline = EmbeddingPipeline(
        provider,
        store,
        batch_size=batch_size,
        s3_bucket=s3_bucket,
        s3_client=s3_client,
    )
    return pipeline, store


# ---------------------------------------------------------------------------
# Basic run
# ---------------------------------------------------------------------------


def test_run_empty_inputs_returns_zero_counts() -> None:
    pipeline, _ = _make_pipeline()
    result = pipeline.run([])

    assert result.total == 0
    assert result.succeeded == 0
    assert result.failed == 0


def test_run_indexes_all_records() -> None:
    pipeline, store = _make_pipeline()
    inputs = _make_inputs(10)
    result = pipeline.run(inputs)

    assert result.total == 10
    assert result.succeeded == 10
    assert result.failed == 0
    assert result.failed_ids == []

    # All records should be queryable
    query_results = store.query([0.0] * DIMENSION, k=10)
    indexed_ids = {r.record_id for r in query_results}
    assert indexed_ids == {inp.record_id for inp in inputs}


def test_run_result_is_pipeline_result_instance() -> None:
    pipeline, _ = _make_pipeline()
    result = pipeline.run(_make_inputs(3))
    assert isinstance(result, PipelineResult)


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def test_run_respects_batch_size() -> None:
    """Records processed in small batches produce the same final store state."""
    pipeline_small, store_small = _make_pipeline(batch_size=3)
    pipeline_large, store_large = _make_pipeline(batch_size=100)

    inputs = _make_inputs(9)

    result_small = pipeline_small.run(inputs)
    result_large = pipeline_large.run(inputs)

    assert result_small.succeeded == result_large.succeeded == 9

    ids_small = {r.record_id for r in store_small.query([0.0] * DIMENSION, k=9)}
    ids_large = {r.record_id for r in store_large.query([0.0] * DIMENSION, k=9)}
    assert ids_small == ids_large


def test_invalid_batch_size_raises() -> None:
    provider = SpotEmbeddingProvider(dimension=DIMENSION)
    store = NumpyVectorStore(dimension=DIMENSION)
    with pytest.raises(ValueError, match="batch_size"):
        EmbeddingPipeline(provider, store, batch_size=0)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_rerun_same_inputs_is_idempotent() -> None:
    """Running the pipeline twice with identical inputs should not duplicate records."""
    pipeline, store = _make_pipeline()
    inputs = _make_inputs(5)

    result1 = pipeline.run(inputs)
    result2 = pipeline.run(inputs)

    assert result1.succeeded == result2.succeeded == 5

    # Store should still contain exactly 5 unique records
    all_results = store.query([0.0] * DIMENSION, k=20)
    assert len(all_results) == 5


def test_rerun_updates_vectors() -> None:
    """Second run with same IDs but new text should overwrite vectors."""
    provider = SpotEmbeddingProvider(dimension=DIMENSION, salt="v1", normalize=True)
    store = NumpyVectorStore(dimension=DIMENSION)
    pipeline_v1 = EmbeddingPipeline(provider, store, batch_size=4)

    pipeline_v1.run([EmbeddingInput(record_id="doc-0", text="original text")])
    vector_before = store.query([0.0] * DIMENSION, k=1)[0].score

    # Switch to a different salt (simulates updated embeddings)
    provider_v2 = SpotEmbeddingProvider(dimension=DIMENSION, salt="v2", normalize=True)
    pipeline_v2 = EmbeddingPipeline(provider_v2, store, batch_size=4)
    pipeline_v2.run([EmbeddingInput(record_id="doc-0", text="original text")])
    vector_after = store.query([0.0] * DIMENSION, k=1)[0].score

    # Scores will differ because the vector changed
    assert vector_before != vector_after


# ---------------------------------------------------------------------------
# Provider silent drops
# ---------------------------------------------------------------------------


def test_silently_dropped_records_counted_as_failed() -> None:
    """Records missing from provider output are added to failed_ids, not silently lost."""
    inputs = _make_inputs(3)  # doc-0, doc-1, doc-2

    class DroppingProvider(EmbeddingProvider):
        """Returns embeddings for only the first input, silently dropping the rest."""

        def generate(self, batch, *, model=None, **_):
            return [
                EmbeddingResult(
                    record_id=batch[0].record_id,
                    vector=[0.1] * DIMENSION,
                    metadata={},
                )
            ]

    store = NumpyVectorStore(dimension=DIMENSION)
    pipeline = EmbeddingPipeline(DroppingProvider(), store, batch_size=64)
    result = pipeline.run(inputs)

    assert result.total == 3
    assert result.succeeded == 1
    assert result.failed == 2
    assert result.total == result.succeeded + result.failed
    assert "doc-1" in result.failed_ids
    assert "doc-2" in result.failed_ids


# ---------------------------------------------------------------------------
# S3 backup
# ---------------------------------------------------------------------------


def test_s3_backup_uploads_both_files(tmp_path: Any) -> None:
    """Both store files are staged and a latest pointer is written on success."""
    mock_s3 = MagicMock()
    pipeline, _ = _make_pipeline(s3_bucket="my-bucket", s3_client=mock_s3)

    pipeline.run(_make_inputs(4))

    uploaded_filenames = [
        call.args[0].split("/")[-1]  # local path basename
        for call in mock_s3.upload_file.call_args_list
    ]
    assert "vectors.npy" in uploaded_filenames
    assert "metadata.json" in uploaded_filenames
    assert mock_s3.upload_file.call_count == 2

    # Pointer written exactly once after both uploads succeed
    mock_s3.put_object.assert_called_once()
    pointer_call = mock_s3.put_object.call_args
    assert pointer_call.kwargs["Bucket"] == "my-bucket"
    assert pointer_call.kwargs["Key"].endswith("/latest")


def test_s3_backup_uses_correct_bucket_and_prefix(tmp_path: Any) -> None:
    mock_s3 = MagicMock()
    provider = SpotEmbeddingProvider(dimension=DIMENSION)
    store = NumpyVectorStore(dimension=DIMENSION)
    pipeline = EmbeddingPipeline(
        provider,
        store,
        s3_bucket="test-bucket",
        s3_prefix="embeddings/v1",
        s3_client=mock_s3,
    )

    pipeline.run(_make_inputs(2))

    for call in mock_s3.upload_file.call_args_list:
        _, bucket, key = call.args
        assert bucket == "test-bucket"
        # Files go to a timestamped subdirectory under the prefix
        assert key.startswith("embeddings/v1/")
        assert key != "embeddings/v1/latest"  # staged, not the pointer

    pointer_call = mock_s3.put_object.call_args
    assert pointer_call.kwargs["Key"] == "embeddings/v1/latest"


def test_no_s3_backup_when_bucket_is_none() -> None:
    """When s3_bucket is None, no S3 calls should be made."""
    mock_s3 = MagicMock()
    pipeline, _ = _make_pipeline(s3_bucket=None, s3_client=mock_s3)

    pipeline.run(_make_inputs(3))

    mock_s3.upload_file.assert_not_called()
    mock_s3.put_object.assert_not_called()


def test_s3_backup_pointer_not_written_on_upload_failure() -> None:
    """If the first upload fails, the latest pointer must not be written."""
    mock_s3 = MagicMock()
    mock_s3.upload_file.side_effect = OSError("network error")
    pipeline, _ = _make_pipeline(s3_bucket="my-bucket", s3_client=mock_s3)

    result = pipeline.run(_make_inputs(2))

    mock_s3.put_object.assert_not_called()
    assert result.backup_error is not None
    assert "Failed to stage" in result.backup_error


def test_s3_backup_failure_still_returns_pipeline_result() -> None:
    """A backup failure must not suppress the PipelineResult from a successful embedding run."""
    mock_s3 = MagicMock()
    mock_s3.upload_file.side_effect = OSError("permission denied")
    pipeline, store = _make_pipeline(s3_bucket="my-bucket", s3_client=mock_s3)
    inputs = _make_inputs(5)

    result = pipeline.run(inputs)

    # Embeddings succeeded despite backup failure
    assert result.total == 5
    assert result.succeeded == 5
    assert result.failed == 0
    assert result.backup_error is not None
    # Store is intact
    assert len(store.query([0.0] * DIMENSION, k=10)) == 5


def test_successful_backup_leaves_backup_error_as_none() -> None:
    """backup_error is None when the S3 backup completes without error."""
    mock_s3 = MagicMock()
    pipeline, _ = _make_pipeline(s3_bucket="my-bucket", s3_client=mock_s3)

    result = pipeline.run(_make_inputs(3))

    assert result.backup_error is None
