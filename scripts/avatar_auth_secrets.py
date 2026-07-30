from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable


def load_auth_secret_users(
    paths: list[Path],
    *,
    load_json: Callable[[Path], dict[str, Any]],
) -> list[Mapping[str, Any]]:
    users: list[Mapping[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
        payload = load_json(path)
        entries = payload.get("users") or {}
        if isinstance(entries, Mapping):
            labeled_entries = entries.items()
        elif isinstance(entries, list):
            labeled_entries = (
                (str(index), entry) for index, entry in enumerate(entries, start=1)
            )
        else:
            continue
        for label, entry in labeled_entries:
            if not isinstance(entry, Mapping):
                continue
            item = dict(entry)
            item.setdefault("label", str(label))
            users.append(item)
    return users