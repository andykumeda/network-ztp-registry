"""lookup.py — Serial-to-PID lookup for the ZTP registry.

At device registration time, server.py calls get_lookup_source().find_by_serial(serial)
to retrieve the Cisco PID (product ID) for the device. The PID is then used by
SlotAssigner in server.py to find the correct installation slot in model-loc.csv.

Environment variables:
    LOOKUP_SOURCE   — "csv" (default) or "none" to disable
    LOOKUP_CSV_PATH — path to model-sn.csv (default: model-sn.csv in this directory)
"""

import csv
import logging
import os

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CSV = os.path.join(_HERE, 'model-sn.csv')


class LookupSource:
    def find_by_serial(self, serial: str) -> dict | None:
        """Return {'pid': '...'} or None if serial not found."""
        raise NotImplementedError


class CSVLookupSource(LookupSource):
    """Looks up device PID by serial number from model-sn.csv.

    Expected columns: PID, SN
    Serial matching is case-insensitive.
    Hot-reloads when the file is modified — no service restart needed.
    """

    def __init__(self, path: str):
        self._path = path
        self._cache: dict[str, dict] = {}
        self._mtime: float | None = None

    def _load(self):
        try:
            mtime = os.path.getmtime(self._path)
        except OSError:
            if self._cache:
                logger.warning('lookup: %s no longer accessible, using cached data', self._path)
            return
        if mtime == self._mtime:
            return
        try:
            with open(self._path, newline='', encoding='utf-8') as f:
                new_cache = {}
                for row in csv.DictReader(f):
                    serial = row.get('SN', '').strip().upper()
                    pid = row.get('PID', '').strip()
                    if serial and pid:
                        new_cache[serial] = {'pid': pid}
            self._cache = new_cache
            self._mtime = mtime
            logger.info('lookup: loaded %d entries from %s', len(self._cache), self._path)
        except Exception as exc:
            logger.warning('lookup: failed to load %s: %s', self._path, exc)

    def find_by_serial(self, serial: str) -> dict | None:
        try:
            self._load()
            return self._cache.get(serial.upper())
        except Exception as exc:
            logger.warning('lookup: find_by_serial error: %s', exc)
            return None


class NoOpLookupSource(LookupSource):
    def find_by_serial(self, serial: str) -> dict | None:
        return None


def get_lookup_source() -> LookupSource:
    source = os.environ.get('LOOKUP_SOURCE', 'csv').lower().strip()
    if source in ('none', 'disabled', 'off'):
        logger.info('lookup: disabled (LOOKUP_SOURCE=%s)', source)
        return NoOpLookupSource()
    path = os.environ.get('LOOKUP_CSV_PATH', _DEFAULT_CSV)
    logger.info('lookup: using CSV source at %s', path)
    return CSVLookupSource(path)
