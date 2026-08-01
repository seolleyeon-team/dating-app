from pathlib import Path
from scripts import privacy_client_scanner as scanner
root=Path.cwd()
for path in scanner._iter_surface_files(root, festival_roots=()):
    text=path.read_text(encoding="utf-8", errors="ignore")
    if scanner._file_has_leak(path, text):
        print(path.relative_to(root).as_posix())