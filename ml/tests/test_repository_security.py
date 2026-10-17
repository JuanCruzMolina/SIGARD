"""Exclusion probes and fictitious static files only; no medical sources or models."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("repository_security", ROOT / "tools/check_repository_security.py")
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


@pytest.mark.parametrize("path", security.PRIVATE_PATHS)
def test_git_private_probes_are_ignored(path):
    assert security.git_ignored(ROOT, path)


@pytest.mark.parametrize("path", security.PUBLIC_CODE_PATHS)
def test_git_code_and_examples_remain_allowed(path):
    assert not security.git_ignored(ROOT, path)


@pytest.mark.parametrize("context", [".", "backend", "frontend", "ml"])
@pytest.mark.parametrize("path", security.DOCKER_PRIVATE_PATHS)
def test_docker_static_private_probes(context, path):
    assert security.docker_ignored(path, security.docker_rules(ROOT / context / ".dockerignore"))


def test_public_resources_match_registry_and_are_not_ignored():
    assets = json.loads((ROOT / "frontend/security/public-assets.json").read_text())["assets"]
    assert len(assets) == 10
    security.check_public(ROOT, assets)
    for path in assets:
        assert not security.git_ignored(ROOT, "frontend/public/" + path)


def test_unmarked_fictitious_public_file_is_rejected_without_deletion(tmp_path):
    folder = tmp_path / "frontend/public"
    folder.mkdir(parents=True)
    target = folder / "ordinary.json"
    target.write_text('{"fictional":true}')
    with pytest.raises(ValueError, match="Unapproved"):
        security.check_public(tmp_path, {})
    assert target.exists()


def test_replaced_fictitious_allowed_file_is_rejected(tmp_path):
    folder = tmp_path / "frontend/public"
    folder.mkdir(parents=True)
    target = folder / "approved.json"
    target.write_text('{"fictional":true}')
    allowed = {"approved.json": security.public_hash(target)}
    target.write_text('{"changed_fictional":true}')
    with pytest.raises(ValueError, match="Changed"):
        security.check_public(tmp_path, allowed)


def test_docker_parent_exception_does_not_reopen_the_public_directory():
    rules = security.docker_rules(ROOT / "frontend/.dockerignore")
    assert security.docker_ignored("public/data/ordinary.json", rules)
    assert security.docker_ignored("public/ordinary.json", rules)
    assert not security.docker_ignored("public/data/available_weeks.json", rules)


def test_unknown_docker_construct_fails_closed():
    with pytest.raises(ValueError):
        security.docker_regex(r"unsupported\pattern")


def test_complete_read_only_security_check():
    result = security.audit(ROOT)
    assert result["checks_passed"] >= 143 and result["tracked_sensitive_candidates"] == 0
    assert not result["models_loaded"] and not result["build_context_sent"]
