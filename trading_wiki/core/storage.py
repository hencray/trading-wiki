import hashlib
import shutil
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def compute_file_hash(path: Path) -> str:
    """Return SHA-256 hex digest of file contents."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def content_addressed_path(
    storage_dir: Path,
    source_type: str,
    sha: str,
    ext: str,
) -> Path:
    """Resolve the content-addressed location for a file."""
    return storage_dir / source_type / sha[:2] / f"{sha}{ext}"


def store_file(
    source_path: Path,
    source_type: str,
    storage_dir: Path,
) -> tuple[str, Path]:
    """Copy ``source_path`` into the content-addressed location.

    Returns ``(sha, dest_path)``. Idempotent — if the destination already
    holds the same hash, the copy is skipped.
    """
    sha = compute_file_hash(source_path)
    dest = content_addressed_path(storage_dir, source_type, sha, source_path.suffix)
    if dest.exists():
        return sha, dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, dest)
    return sha, dest
