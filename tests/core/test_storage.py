import hashlib

import pytest

from trading_wiki.core.storage import compute_file_hash, content_addressed_path, store_file


def test_compute_file_hash_returns_sha256_hex(tmp_path):
    f = tmp_path / "test.txt"
    f.write_bytes(b"hello world")
    assert compute_file_hash(f) == hashlib.sha256(b"hello world").hexdigest()


def test_compute_file_hash_same_content_same_hash(tmp_path):
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"identical content")
    f2.write_bytes(b"identical content")
    assert compute_file_hash(f1) == compute_file_hash(f2)


def test_compute_file_hash_handles_large_file(tmp_path):
    f = tmp_path / "big.bin"
    payload = b"x" * (5 * 1024 * 1024)
    f.write_bytes(payload)
    assert compute_file_hash(f) == hashlib.sha256(payload).hexdigest()


def test_content_addressed_path_uses_first_two_hex_chars_as_subdir(tmp_path):
    sha = "deadbeef" + "0" * 56
    result = content_addressed_path(tmp_path, "local_video", sha, ".mp4")
    assert result == tmp_path / "local_video" / "de" / f"{sha}.mp4"


def test_store_file_copies_to_content_addressed_location(tmp_path):
    src = tmp_path / "input.mp4"
    src.write_bytes(b"video bytes")
    storage_dir = tmp_path / "storage"

    sha, dest = store_file(src, "local_video", storage_dir)

    assert sha == hashlib.sha256(b"video bytes").hexdigest()
    assert dest.exists()
    assert dest.read_bytes() == b"video bytes"
    assert dest == storage_dir / "local_video" / sha[:2] / f"{sha}.mp4"


def test_store_file_is_idempotent(tmp_path):
    src = tmp_path / "input.mp4"
    src.write_bytes(b"video bytes")
    storage_dir = tmp_path / "storage"

    sha1, dest1 = store_file(src, "local_video", storage_dir)
    sha2, dest2 = store_file(src, "local_video", storage_dir)

    assert sha1 == sha2
    assert dest1 == dest2
    assert dest1.exists()


def test_store_file_preserves_extension(tmp_path):
    src = tmp_path / "audio.WAV"
    src.write_bytes(b"audio")
    storage_dir = tmp_path / "storage"

    _, dest = store_file(src, "local_video", storage_dir)
    assert dest.suffix == ".WAV"


def test_store_file_rejects_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        store_file(tmp_path / "missing.mp4", "local_video", tmp_path / "storage")
