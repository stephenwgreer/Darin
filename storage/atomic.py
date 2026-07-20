"""Atomic file writes for the flat-file stores.

A plain ``Path.write_text()`` truncates the target before writing, so a crash,
full disk, or I/O error mid-write leaves an empty/partial file — destroying the
previously-good contents. ``atomic_write_text`` writes to a temp file in the
same directory, flushes it to disk, then ``os.replace()``s it over the target,
which is atomic on POSIX and Windows. A failed write can never clobber the
existing good file: the target is only ever swapped for a fully-written temp.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, data: str, *, encoding: str = "utf-8") -> None:
    """Write ``data`` to ``path`` atomically (temp file + fsync + os.replace).

    The temp file is created in the target's own directory so the final
    ``os.replace`` is a same-filesystem rename (a cross-device rename would not
    be atomic and would raise). On any failure the temp file is removed and the
    original ``path`` is left untouched.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(directory), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Never leave the temp file behind, and never touch the good original.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
