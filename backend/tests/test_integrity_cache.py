"""Per-process integrity cache. Fictional bytes only; no research artifacts are read."""
import hashlib
import os

import pytest

from app import experimental_results as er
from app.experimental_results import ArtifactBlocked, local_bytes, verify_local


@pytest.fixture
def counted(monkeypatch):
    calls = []
    original = er._digest
    monkeypatch.setattr(er, '_digest', lambda chunks: calls.append(1) or original(chunks))
    er.clear_verification_cache()
    yield calls
    er.clear_verification_cache()


def fictional(tmp_path, body=b'FICTIONAL_ARTIFACT_A'):
    (tmp_path / 'f.private.bin').write_bytes(body)
    return 'f.private.bin', hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize('check', [
    lambda root, rel, sha: local_bytes(root, rel, sha),
    lambda root, rel, sha: verify_local(root, rel, sha, 1024)])
def test_unchanged_file_is_hashed_once_per_process(tmp_path, counted, check):
    rel, sha = fictional(tmp_path)
    for _ in range(3):
        check(tmp_path, rel, sha)
    assert len(counted) == 1


@pytest.mark.parametrize('check', [
    lambda root, rel, sha: local_bytes(root, rel, sha),
    lambda root, rel, sha: verify_local(root, rel, sha, 1024)])
def test_same_size_altered_file_with_new_mtime_is_rehashed_and_blocked(tmp_path, counted, check):
    rel, sha = fictional(tmp_path)
    check(tmp_path, rel, sha)
    path = tmp_path / rel
    before = path.stat()
    path.write_bytes(b'FICTIONAL_ARTIFACT_B')  # same size
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
    assert path.stat().st_size == before.st_size
    with pytest.raises(ArtifactBlocked):
        check(tmp_path, rel, sha)
    assert len(counted) == 2
    with pytest.raises(ArtifactBlocked):  # a failed verification is never cached
        check(tmp_path, rel, sha)
    assert len(counted) == 3


def test_size_change_or_other_expected_digest_rehashes(tmp_path, counted):
    rel, sha = fictional(tmp_path)
    verify_local(tmp_path, rel, sha, 1024)
    with pytest.raises(ArtifactBlocked):
        verify_local(tmp_path, rel, '0' * 64, 1024)
    (tmp_path / rel).write_bytes(b'FICTIONAL_LONGER_ARTIFACT')
    with pytest.raises(ArtifactBlocked):
        verify_local(tmp_path, rel, sha, 1024)
    assert len(counted) == 3


def test_cached_restoration_requires_original_bytes(tmp_path, counted):
    rel, sha = fictional(tmp_path)
    local_bytes(tmp_path, rel, sha)
    (tmp_path / rel).write_bytes(b'FICTIONAL_ARTIFACT_A')  # rewritten identical: new mtime, re-verified, accepted
    assert local_bytes(tmp_path, rel, sha) == b'FICTIONAL_ARTIFACT_A'


def test_limits_and_traversal_still_apply_with_cache(tmp_path, counted):
    rel, sha = fictional(tmp_path)
    verify_local(tmp_path, rel, sha, 1024)
    with pytest.raises(ArtifactBlocked):
        verify_local(tmp_path, rel, sha, 4)
    with pytest.raises(ArtifactBlocked):
        verify_local(tmp_path, '../' + rel, sha, 1024)
