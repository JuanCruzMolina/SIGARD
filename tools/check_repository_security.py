"""Read-only Git/Docker/static-resource checks; no model loading or source ingestion."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PRIVATE_PATHS = [
    ".env.local", "backend/.env.production", "frontend/nested/.env.backup", "ml/configs/official.research.private.json",
    "ml/configs/settings.private.toml", "backend/app/config_private.ini", "config/private.yaml",
    "docs/report.private.html", "docs/authorization.private", "docs/integrity_manifest.private.json",
    "data/datos oficiales/fictional.xlsx", "data/interim/official/fictional/.gitkeep",
    "data/processed/official/fictional/predictions.parquet", "docs/fictional.XLSM", "docs/fictional.xlsb",
    "ml/models/nested/fictional.joblib", "ml/artifacts/nested/fictional.pkl", "exports/fictional.onnx",
    "config/credentials.json", "keys/fictional.pem", "frontend/public/data/patient-residence.geojson",
    "frontend/public/data/new-score.json", "frontend/public/patients.json", "frontend/public/data/fictional.private.xlsx",
    ".agents/skills/fictional/SKILL.md", "skills-lock.json",
    ".ENV.backup", "config/SETTINGS.PRIVATE.YAML", "exports/fictional.JOBLIB", "exports/fictional.PARQUET",
    "docs/individual_locations.geojson", ".npmrc", "nested/.aws/credentials",
]
PUBLIC_CODE_PATHS = [".env.example", "frontend/.env.example", "ml/configs/official.example.json",
    "ml/configs/official.spatial-research.example.json", "ml/configs/fictional.example.toml",
    "ml/tests/fixtures/fictional.json", "backend/app/security.py", "docs/fictional.md"]
DOCKER_PRIVATE_PATHS = [".env.local", "nested/.env.secret", "configs/settings.private.toml",
    "nested/private.json", "app/config_private.ini", "data/interim/official/fictional/.gitkeep",
    "data/processed/official/fictional/predictions.parquet", "nested/fictional.XLSM", "nested/fictional.xlsb",
    "models/nested/fictional.joblib", "nested/fictional.pkl", "keys/fictional.key", "config/credentials.json",
    ".agents/skills/fictional/SKILL.md", "skills-lock.json"]
DOCKER_PRIVATE_PATHS += [".ENV.backup", "config/SETTINGS.PRIVATE.YAML", "exports/fictional.JOBLIB", "exports/fictional.PARQUET"]
DOCKER_PRIVATE_PATHS += ["exports/individual_locations.geojson", ".npmrc", "nested/.aws/credentials"]


def git_ignored(root, path):
    result = subprocess.run(["git", "check-ignore", "--no-index", "-v", "--", path],
                            cwd=root, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):
        raise ValueError("Git ignore check failed")
    if not result.stdout:
        return False
    rule = result.stdout.split("\t", 1)[0].split(":", 2)[-1]
    return not rule.startswith("!")


def docker_regex(pattern):
    """Explicit current-rule subset, not a substitute for a BuildKit build.

    Supports *, ?, **, simple alphanumeric bracket classes and parent matching.
    Unknown pattern constructs fail closed. Never creates/sends a build context.
    """
    if "\\" in pattern:
        raise ValueError("Unsupported Docker pattern")
    out, pos = "", 0
    while pos < len(pattern):
        if pattern[pos:pos+3] == "**/":
            out += "(?:.*/)?"
            pos += 3
        elif pattern[pos:pos+2] == "**":
            out += ".*"
            pos += 2
        elif pattern[pos] == "[":
            end = pattern.find("]", pos + 1)
            members = pattern[pos+1:end]
            if end < 0 or not re.fullmatch(r"[A-Za-z0-9]+", members):
                raise ValueError("Unsupported Docker bracket pattern")
            out += "[" + members + "]"
            pos = end + 1
        else:
            char = pattern[pos]
            out += "[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char)
            pos += 1
    return re.compile("^" + out + "$")


def docker_rules(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def docker_ignored(path, rules):
    parts = path.strip("/").split("/")
    ancestry = ["/".join(parts[:length]) for length in range(1, len(parts)+1)]
    ignored = False
    for rule in rules:
        included = rule.startswith("!")
        pattern = rule[1:] if included else rule
        regex = docker_regex(pattern.strip("/"))
        if any(regex.fullmatch(parent) for parent in ancestry):
            ignored = not included
    return ignored


def public_hash(path):
    if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Invalid public resource")
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_public(root, assets):
    folder = root / "frontend/public"
    entries = list(folder.rglob("*"))
    if folder.is_symlink() or any(path.is_symlink() for path in entries):
        raise ValueError("Public resource link is forbidden")
    actual = {path.relative_to(folder).as_posix() for path in entries if path.is_file()}
    if actual != set(assets):
        raise ValueError("Unapproved public resource; stop without deleting or logging contents")
    if any(public_hash(folder / path) != expected for path, expected in assets.items()):
        raise ValueError("Changed public resource; stop without serving")


def check_actual_contexts(root):
    """Metadata-only scan; never reads excluded patient files or sends a context."""
    sensitive = re.compile(r"(?:\.private(?:\.|$|-)|_private(?:\.|$)|^\.env(?:\.|$)|\.(?:xls\w*|parquet|feather|arrow|joblib|pkl|pickle|h5|hdf5|onnx|pt|pth|pem|key|p12|pfx|sqlite3?|dump)$)", re.I)
    totals = {}
    for context in (".", "backend", "frontend", "ml"):
        base = root / context
        rules = docker_rules(base / ".dockerignore")
        visible = 0
        for folder, directories, filenames in os.walk(base, followlinks=False):
            # These generated/vendor folders are explicitly excluded in every context.
            directories[:] = [name for name in directories if name not in {
                ".git", "node_modules", "venv", ".venv", "__pycache__", ".tmp", ".cache", ".pytest_cache", "dist", ".agents"}]
            for name in filenames:
                path = Path(folder) / name
                relative = path.relative_to(base).as_posix()
                if docker_ignored(relative, rules):
                    continue
                visible += 1
                if path.is_symlink():
                    raise ValueError("Visible Docker source link requires review; stop without transfer")
                if sensitive.search(name) and name != ".env.example":
                    raise ValueError("Sensitive filename visible to Docker; stop without transfer")
        totals[context] = visible
    return totals


def audit(root):
    root = root.resolve()
    registry = json.loads((root / "frontend/security/public-assets.json").read_text(encoding="utf-8"))
    assets = registry["assets"]
    check_public(root, assets)
    checks = []
    for path in PRIVATE_PATHS:
        if not git_ignored(root, path):
            raise ValueError("Private Git probe is not excluded: " + path)
        checks.append({"engine": "Git", "path": path, "excluded": True})
    for path in PUBLIC_CODE_PATHS + ["frontend/public/" + name for name in assets]:
        if git_ignored(root, path):
            raise ValueError("Legitimate example/code/resource was excluded: " + path)
        checks.append({"engine": "Git", "path": path, "excluded": False})
    for context in (".", "backend", "frontend", "ml"):
        rules = docker_rules(root / context / ".dockerignore")
        cases = list(DOCKER_PRIVATE_PATHS)
        if context == ".":
            cases += ["frontend/public/data/new-score.json", "frontend/public/patients.geojson"]
        if context == "frontend":
            cases += ["public/data/new-score.json", "public/patients.geojson"]
        for path in cases:
            if not docker_ignored(path, rules):
                raise ValueError("Private Docker probe is not excluded: " + context + ":" + path)
            checks.append({"engine": "Docker static subset", "context": context, "path": path, "excluded": True})
        allowed = [".env.example", "configs/fictional.example.json", "src/fictional.py", "tests/fixtures/fictional.json"]
        if context == "ml":
            allowed.remove("tests/fixtures/fictional.json")  # Existing ML image deliberately excludes tests.
        if context in (".", "frontend"):
            allowed += [("frontend/" if context == "." else "") + "public/" + name for name in assets]
        for path in allowed:
            if docker_ignored(path, rules):
                raise ValueError("Legitimate Docker source/resource excluded: " + context + ":" + path)
            checks.append({"engine": "Docker static subset", "context": context, "path": path, "excluded": False})
    tracked = [name for name in subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0") if name]
    # Ignores are tested with --no-index: tracked status does not bypass this check.
    tracked_suspects = [name for name in tracked if git_ignored(root, name)]
    if tracked_suspects:
        raise ValueError("Tracked excluded file found; stop and report without untracking or deleting")
    signatures = [re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")]
    untracked = [name for name in subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root).decode().split("\0") if name]
    for name in sorted(set(tracked + untracked)):
        path = root / name
        if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
            content = path.read_bytes().decode("utf-8", errors="replace")
            if any(pattern.search(content) for pattern in signatures):
                raise ValueError("Tracked secret signature found; stop without logging values")
    context_counts = check_actual_contexts(root)
    return {"checks_passed": len(checks), "tracked_files_checked": len(tracked), "public_assets_checked": len(assets),
        "visible_text_candidate_paths_checked": len(set(tracked + untracked)), "actual_context_visible_files": context_counts,
        "tracked_sensitive_candidates": 0, "models_loaded": False, "build_context_sent": False,
        "docker_check_scope": "static current-pattern subset; not a BuildKit attestation", "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    if args.output:
        target = args.output.resolve()
        allowed = (args.root / "data/interim/official/repository_security_v1").resolve()
        if not target.is_relative_to(allowed) or target.exists():
            raise ValueError("Audit output must be new and private")
        target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}))


if __name__ == "__main__":
    main()
