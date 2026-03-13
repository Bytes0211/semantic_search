"""Embedding job pipeline: batch embed, upsert to vector store, backup to S3."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

from ..embeddings.base import EmbeddingInput, EmbeddingProvider
from ..vectorstores.faiss_store import NumpyVectorStore, VectorRecord

LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Summary statistics returned by a completed pipeline run.

    Attributes:
        total: Total number of input records submitted.
        succeeded: Number of records successfully embedded and upserted.
        failed: Number of records that could not be processed.
        failed_ids: Record IDs of every failed input, in encounter order.
    """

    total: int
    succeeded: int
    failed: int
    failed_ids: List[str] = field(default_factory=list)


class EmbeddingPipeline:
    """Orchestrates embedding generation, vector store persistence, and S3 backup.

    Accepts a sequence of :class:`~semantic_search.embeddings.base.EmbeddingInput`
    records, generates embeddings in configurable batches using the supplied
    :class:`~semantic_search.embeddings.base.EmbeddingProvider`, upserts the
    results into a :class:`~semantic_search.vectorstores.faiss_store.NumpyVectorStore`,
    and optionally archives the updated store to S3.

    Idempotency is guaranteed by the underlying ``upsert`` operation: re-running
    the pipeline with the same record IDs simply overwrites the previous vectors
    with the latest values, leaving the store in a consistent state.

    Example:
        .. code-block:: python

            from semantic_search.embeddings.factory import get_provider
            from semantic_search.vectorstores import NumpyVectorStore
            from semantic_search.pipeline.embedding_pipeline import EmbeddingPipeline

            provider = get_provider("spot", {"dimension": 768})
            store = NumpyVectorStore(dimension=768)
            pipeline = EmbeddingPipeline(provider, store, batch_size=32)

            result = pipeline.run(inputs)
            print(result.succeeded, "records indexed")
    """

    def __init__(
        self,
        provider: EmbeddingProvider,
        store: NumpyVectorStore,
        *,
        batch_size: int = 64,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "vector-store",
        s3_client: Optional[Any] = None,
    ) -> None:
        """Initialise the embedding pipeline.

        Args:
            provider: Embedding provider used to generate vectors.
            store: Vector store that receives the upserted embeddings.
            batch_size: Number of records to embed per provider call. Larger
                batches reduce call overhead; smaller batches limit memory
                usage and provide finer-grained error isolation. Defaults
                to 64.
            s3_bucket: S3 bucket name for post-run store backups. When
                ``None`` (default) no S3 backup is performed.
            s3_prefix: Key prefix (folder path) under which the store files
                are uploaded inside ``s3_bucket``. Defaults to
                ``"vector-store"``.
            s3_client: Pre-configured boto3 S3 client. When ``None`` a
                default client is created via ``boto3.client("s3")`` at
                backup time. Supply an explicit client in tests or when
                custom credentials / endpoint URLs are required.

        Raises:
            ValueError: If ``batch_size`` is not a positive integer.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")

        self._provider = provider
        self._store = store
        self._batch_size = batch_size
        self._s3_bucket = s3_bucket
        self._s3_prefix = s3_prefix.strip("/")
        self._s3_client = s3_client

    def run(self, inputs: Sequence[EmbeddingInput]) -> PipelineResult:
        """Embed all inputs, upsert into the vector store, and optionally backup.

        Processing is split into batches of :attr:`batch_size`. Failures within
        a batch are caught per-record so that a single bad input does not abort
        the remainder of the run. After all batches complete, the store is
        backed up to S3 if ``s3_bucket`` was supplied at construction.

        Args:
            inputs: Sequence of records to embed and index. May be empty, in
                which case the method returns immediately with zero counts.

        Returns:
            A :class:`PipelineResult` summarising successes and failures.
        """
        if not inputs:
            LOGGER.info("EmbeddingPipeline.run called with empty input; skipping.")
            return PipelineResult(total=0, succeeded=0, failed=0)

        total = len(inputs)
        succeeded = 0
        failed_ids: List[str] = []

        batches = [
            inputs[i : i + self._batch_size]
            for i in range(0, total, self._batch_size)
        ]

        LOGGER.info(
            "EmbeddingPipeline starting: %d records across %d batch(es).",
            total,
            len(batches),
        )

        for batch_index, batch in enumerate(batches):
            batch_records, batch_failed = self._process_batch(batch)
            if batch_records:
                self._store.upsert(batch_records)
                succeeded += len(batch_records)
            if batch_failed:
                failed_ids.extend(batch_failed)
            LOGGER.debug(
                "Batch %d/%d: %d succeeded, %d failed.",
                batch_index + 1,
                len(batches),
                len(batch_records),
                len(batch_failed),
            )

        result = PipelineResult(
            total=total,
            succeeded=succeeded,
            failed=len(failed_ids),
            failed_ids=failed_ids,
        )

        LOGGER.info(
            "EmbeddingPipeline complete: %d/%d succeeded, %d failed.",
            succeeded,
            total,
            len(failed_ids),
        )

        if self._s3_bucket:
            self._backup_to_s3()

        return result

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _process_batch(
        self, batch: Sequence[EmbeddingInput]
    ) -> tuple[List[VectorRecord], List[str]]:
        """Embed a single batch and convert results to VectorRecord objects.

        Failures are caught per-record so that a provider error for one item
        does not discard successfully generated vectors from the same batch.

        Args:
            batch: A slice of the full input sequence, sized up to
                :attr:`batch_size`.

        Returns:
            A 2-tuple of:

            - ``records``: List of :class:`~..vectorstores.faiss_store.VectorRecord`
              ready for upsert.
            - ``failed_ids``: List of record IDs that could not be embedded.
        """
        records: List[VectorRecord] = []
        failed_ids: List[str] = []

        try:
            results = self._provider.generate(list(batch))
        except Exception as exc:  # noqa: BLE001
            LOGGER.error(
                "Provider.generate failed for entire batch of %d records: %s",
                len(batch),
                exc,
            )
            failed_ids.extend(item.record_id for item in batch)
            return records, failed_ids

        for embedding in results:
            try:
                records.append(
                    VectorRecord(
                        record_id=embedding.record_id,
                        vector=embedding.vector,
                        metadata=dict(embedding.metadata),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "Failed to build VectorRecord for record_id=%r: %s",
                    embedding.record_id,
                    exc,
                )
                failed_ids.append(embedding.record_id)

        return records, failed_ids

    def _backup_to_s3(self) -> None:
        """Serialise the vector store to a temp directory and upload to S3.

        Saves ``vectors.npy`` and ``metadata.json`` produced by
        :meth:`~..vectorstores.faiss_store.NumpyVectorStore.save` and uploads
        each file to ``s3://<s3_bucket>/<s3_prefix>/<filename>``.

        Raises:
            RuntimeError: If the S3 upload fails (wraps the underlying
                boto3 exception with context).
        """
        import boto3  # local import — only needed when S3 backup is active

        client = self._s3_client or boto3.client("s3")

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._store.save(tmp_dir)

            for filename in ("vectors.npy", "metadata.json"):
                local_path = os.path.join(tmp_dir, filename)
                s3_key = (
                    f"{self._s3_prefix}/{filename}"
                    if self._s3_prefix
                    else filename
                )
                try:
                    client.upload_file(local_path, self._s3_bucket, s3_key)
                    LOGGER.info(
                        "Uploaded %s to s3://%s/%s",
                        filename,
                        self._s3_bucket,
                        s3_key,
                    )
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"Failed to upload {filename} to "
                        f"s3://{self._s3_bucket}/{s3_key}: {exc}"
                    ) from exc
