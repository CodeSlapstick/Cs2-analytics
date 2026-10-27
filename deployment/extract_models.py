"""Extract the Windows-created model archive safely on Linux containers."""

from pathlib import Path
import sys
from zipfile import ZipFile


archive = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()

with ZipFile(archive) as bundle:
    for entry in bundle.infolist():
        # The archive was produced on Windows and stores backslashes in names.
        relative = Path(entry.filename.replace("\\", "/"))
        target = (destination / relative).resolve()
        if destination not in target.parents and target != destination:
            raise ValueError(f"Unsafe archive path: {entry.filename}")
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bundle.read(entry))
