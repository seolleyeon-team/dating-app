from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Iterable, List, Optional, Sequence, TypeVar

from avatar_generation.job_lease import (
    AvatarJobLeaseConfig,
    ClaimDeadline,
    LeasedAvatarJob,
    claim_next_avatar_job,
    normalize_datetime,
    utcnow,
)


T = TypeVar("T")


def iter_batches(items: Sequence[T], batch_size: int) -> Iterable[List[T]]:
    size = max(1, int(batch_size))
    for index in range(0, len(items), size):
        yield list(items[index : index + size])


def bounded_batch_size(batch_size: Optional[int], config: AvatarJobLeaseConfig) -> int:
    if config.force_single_job_mode or not config.batching_enabled or config.batch_mode in {"single", "single_job"}:
        return 1
    requested = config.batch_size if batch_size is None else batch_size
    return max(1, min(int(requested), config.max_scan))


def claim_avatar_job_batch(
    firestore_client: Any,
    *,
    worker_id: str,
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
    batch_size: Optional[int] = None,
    deadline: Optional[ClaimDeadline] = None,
) -> List[LeasedAvatarJob]:
    config = config or AvatarJobLeaseConfig.from_env()
    current = normalize_datetime(now or utcnow())
    if deadline is not None and deadline.should_stop(now=current):
        return []

    leases: List[LeasedAvatarJob] = []
    batch_id = f"batch_{uuid.uuid4().hex[:16]}"
    for _ in range(bounded_batch_size(batch_size, config)):
        if deadline is not None and deadline.should_stop(now=current):
            break
        lease = claim_next_avatar_job(
            firestore_client,
            worker_id=worker_id,
            now=current,
            config=config,
            deadline=deadline,
            batch_id=batch_id,
        )
        if lease is None:
            break
        leases.append(lease)
    return leases
