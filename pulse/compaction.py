"""Merge each day's many small Parquet files into one bigger file ("compaction").

Every save writes a new small file. Thousands of tiny files make DuckDB slower,
so from time to time we "bind the loose pages into one booklet":

  1. read all files of a day and write them into ONE new file with a temporary
     name ending in .tmp (DuckDB only reads *.parquet, so it can't see it yet)
  2. note inside the new file which small files it was made from
  3. rename it to compacted_<random>.parquet, then delete the small files

If Pulse crashes halfway, `recover()` (run at start-up) cleans up so that no
event is lost or counted twice.
"""
import threading
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import duckdb
import pyarrow.parquet as pq

# Merge a day's folder once it holds this many files
COMPACT_AT_FILES = 50

# Rows per block inside a merged file. Several blocks let DuckDB use several
# CPU cores at once (one giant block made the funnel about 2x slower).
ROW_GROUP_SIZE = 100_000

# Key in the merged file's metadata that lists the small files it replaced
_SOURCES_KEY = b"pulse_sources"


def compact_if_needed(data_dir: Path, files_lock: threading.Lock | None = None) -> int:
    """Merge day folders that need it. Returns how many folders were merged.

    A folder is merged when it has COMPACT_AT_FILES or more files, or when the
    day is over (yesterday or older, UTC) and it still has more than one file.
    """
    if not data_dir.exists():
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    merged = 0
    for day_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        count = len(list(day_dir.glob("*.parquet")))
        day_is_over = day_dir.name < today
        if count >= COMPACT_AT_FILES or (day_is_over and count > 1):
            compact_day(day_dir, files_lock)
            merged += 1
    return merged


def compact_day(day_dir: Path, files_lock: threading.Lock | None = None) -> None:
    """Merge every Parquet file in one day folder into a single file."""
    # Take a fixed list of files now. Files saved while we work are simply
    # not part of this merge and stay as they are.
    sources = sorted(day_dir.glob("*.parquet"))
    if len(sources) < 2:
        return

    # The slow part (read + write) happens WITHOUT the lock, so charts keep
    # working. The .tmp file is invisible to queries until we rename it.
    table = _read_all(sources)
    # Remember which files this one replaces (used by recover())
    table = table.replace_schema_metadata(
        {_SOURCES_KEY: "\n".join(path.name for path in sources).encode()}
    )
    final_path = day_dir / f"compacted_{uuid4().hex}.parquet"
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    # Write in blocks ("row groups") so DuckDB can read them in parallel later
    pq.write_table(table, tmp_path, row_group_size=ROW_GROUP_SIZE)

    # The quick swap holds the lock, so no query ever sees both the merged
    # file and the small files at once (that would count events twice)
    with files_lock or nullcontext():
        tmp_path.replace(final_path)  # now visible to DuckDB
        for path in sources:
            path.unlink(missing_ok=True)


def _read_all(paths: list[Path]):
    """Read many Parquet files into one table, sorted by time.

    DuckDB reads lots of small files much faster than pyarrow file-by-file
    (about 0.2 s instead of minutes for 5,000 files).
    """
    file_list = ", ".join("'" + str(p).replace("\\", "/").replace("'", "''") + "'" for p in paths)
    with duckdb.connect() as conn:
        return conn.execute(
            f"SELECT * FROM read_parquet([{file_list}], union_by_name=true) ORDER BY timestamp"
        ).to_arrow_table()


def recover(data_dir: Path) -> None:
    """Clean up after a crash in the middle of compact_day()."""
    if not data_dir.exists():
        return
    for day_dir in (p for p in data_dir.iterdir() if p.is_dir()):
        # Crash while writing: the merge never finished, originals are intact
        for tmp in day_dir.glob("*.tmp"):
            tmp.unlink(missing_ok=True)

        # Crash after renaming: small files still exist next to the merged
        # file that already contains their events -> delete the small files
        for merged in day_dir.glob("compacted_*.parquet"):
            metadata = pq.read_schema(merged).metadata or {}
            for name in metadata.get(_SOURCES_KEY, b"").decode().splitlines():
                if name and name != merged.name:
                    (day_dir / name).unlink(missing_ok=True)
