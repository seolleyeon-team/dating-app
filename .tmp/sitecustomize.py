from __future__ import annotations

import os

_original_mkdir = os.mkdir


def _workspace_mkdir(path, mode=0o777, *, dir_fd=None):
    effective_mode = 0o777 if mode == 0o700 else mode
    if dir_fd is None:
        return _original_mkdir(path, effective_mode)
    return _original_mkdir(path, effective_mode, dir_fd=dir_fd)


os.mkdir = _workspace_mkdir