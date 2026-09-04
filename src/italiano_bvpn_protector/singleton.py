from __future__ import annotations

import sys
from pathlib import Path
from typing import IO


class AlreadyRunningError(Exception):
    pass


def acquire_singleton_lock(lock_path: Path) -> IO[str]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fh = open(lock_path, "a+")  # noqa: SIM115
    fh.seek(0, 2)
    if fh.tell() == 0:
        fh.write("lock")
        fh.flush()
    fh.seek(0)

    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise AlreadyRunningError(
            f"Another instance appears to already be running (lock held on {lock_path})"
        ) from exc

    return fh
