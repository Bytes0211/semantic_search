from __future__ import annotations

import hashlib
from typing import Iterable, Sequence

from .base import Vector


def hash_vector(vector: Sequence[float], *, precision: int = 6) -> str:
    """Return a deterministic hash for the provided vector.

    Args:
        vector: Numerical embedding values.
        precision: Number of decimal places to keep when normalising values
            prior to hashing. Defaults to six decimal places.

    Returns:
        A hexadecimal SHA256 digest representing the vector contents.

    Notes:
        - Normalisation mitigates minor floating-point differences between
          providers or hardware.
        - The hash is suitable for deduplication checks but should not be
          considered cryptographic proof of equivalence.
    """
    if precision < 0:
        raise ValueError("precision must be non-negative")

    formatted = ",".join(f"{value:.{precision}f}" for value in vector)
    digest = hashlib.sha256(formatted.encode("utf-8"))
    return digest.hexdigest()
