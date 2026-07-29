from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import uuid4

import pytest

_ROOT = Path(r"C:\Users\samsung\StudioProjects\semisemifinal\tmp\g007_pytest_owned")


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    digest = hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:12]
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", request.node.name)[:48]
    path = _ROOT / f"{name}_{digest}_{uuid4().hex[:8]}"
    path.mkdir(parents=True, mode=0o777, exist_ok=False)
    return path