"""Atomic JSON state file I/O with advisory file locking.

Both server.py and opengear_poller.py read/write .poller_state.json. Without
coordination, a reader can observe a half-written file and crash. These helpers
use fcntl.flock for mutual exclusion and os.rename for atomic writes.
"""

import fcntl
import json
import os
import tempfile


def load_state(path):
    """Return parsed JSON from path, or {} if missing/corrupt."""
    try:
        with open(path, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path, data):
    """Write data as JSON to path atomically (temp file + rename)."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix='.poller_state.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.chmod(tmp, 0o664)
        os.rename(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
