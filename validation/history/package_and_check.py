#!/usr/bin/env python3
"""Allowlisted packaging and integrity checks; uses existing PyYAML for YAML validation."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
import yaml

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE / "graph-loop"
V = BASE / "validation"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_member(name):
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and "\\" not in name and not re.match(r"^[A-Za-z]:", name)


def collect(folder):
    out = []
    for p in sorted(folder.rglob("*")):
        require(not p.is_symlink(), "symlink excluded from delivery")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            out.append(p)
    return out


def write_zip(name, files):
    path = BASE / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            rel = f.relative_to(BASE).as_posix()
            require(safe_member(rel), "unsafe archive path")
            info = zipfile.ZipInfo(rel, date_time=(2026, 10, 31, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(info, f.read_bytes())
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None, "zip CRC failed")
        require(len(z.namelist()) == len(set(z.namelist())) == len(files), "zip duplicate/missing entries")
        for info, f in zip(z.infolist(), files):
            require(safe_member(info.filename), "unsafe archive member")
            require(not stat.S_ISLNK(info.external_attr >> 16), "symlink archive member")
            require(z.read(info.filename) == f.read_bytes(), "zip source byte mismatch")
    return {"file": name, "files": len(files), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    text = (SKILL / "SKILL.md").read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    require(match is not None, "frontmatter missing")
    frontmatter = yaml.safe_load(match.group(1))
    require(set(frontmatter) == {"name", "description", "metadata"}, "unexpected frontmatter")
    require(frontmatter["name"] == SKILL.name == "graph-loop", "name mismatch")
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", frontmatter["name"]) is not None, "invalid skill name")
    require(1 <= len(frontmatter["name"]) <= 64 and 1 <= len(frontmatter["description"]) <= 1024, "length outside spec")
    require(all(isinstance(k, str) and isinstance(v, str) for k, v in frontmatter["metadata"].items()), "metadata must map string to string")
    require(len(text.splitlines()) < 500, "core exceeds progressive disclosure guideline")
    skill_files = collect(SKILL)
    require(all(p.relative_to(SKILL).parts[0] in {"SKILL.md", "references", "scripts", "assets"} for p in skill_files), "unexpected skill file")
    root_files = [BASE / "review.zh-CN.md", BASE / "install-prompt.en.md"]
    validation_files = [V / n for n in ("run_validation.py", "package_and_check.py", "verification-report.zh-CN.md", "results.json", "test-output.log", "skill-creator-check.log")]
    source_files = skill_files + root_files + validation_files + collect(V / "runs")
    require(all(f.is_file() and not f.is_symlink() for f in source_files), "missing or symlinked input")
    tests = json.loads((V / "results.json").read_text())
    require(tests["successful"] and tests["tests_run"] == 20, "behavior fixture checks not successful")
    # Compare only allowlisted file bytes with secret-like env values; never print/persist values.
    private_values = [value.encode() for key, value in os.environ.items() if any(word in key.upper() for word in ("TOKEN", "SECRET", "PRIVATE", "PASSWORD", "KEY")) and len(value) >= 12]
    for f in source_files:
        data = f.read_bytes()
        require(not any(value in data for value in private_values), "sensitive environment value in package input")
        require(not any(part in {".env", ".git", ".paperclip", ".ssh"} for part in f.relative_to(BASE).parts), "private config path in package")
    require(all(not safe_member(n) for n in ("../escape", "/absolute", "a/../../b", "C:/secret", "a\\b")), "unsafe-path probes failed")
    require(safe_member("graph-loop/references/state-contract.md"), "safe-path probe failed")
    generated = {V / "package-check.json", V / "source-manifest.json"}
    links_checked = 0
    for f in source_files:
        if f.suffix != ".md":
            continue
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", f.read_text()):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            path = (f.parent / target.split("#")[0]).resolve()
            require(path.is_relative_to(BASE), "local markdown link escapes package")
            require(path.exists() or path in generated, "broken local markdown link: " + str(f.relative_to(BASE)) + " -> " + target)
            links_checked += 1
    manifest = {str(f.relative_to(BASE)): hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files}
    (V / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    checks = {"success": True, "format": "YAML name/description/metadata and directory conventions checked", "skill_core_lines": len(text.splitlines()), "skill_files": len(skill_files), "payload_sources": len(source_files), "local_markdown_links_checked": links_checked, "source_sensitive_env_scan": "no exact matches in allowlisted sources; values not persisted", "unsafe_archive_path_probes": "5 rejected, valid path accepted", "archive_integrity": "CRC and every entry compared to source bytes; no symlinks or duplicate names", "scope": "no host discovery, model evaluation, external upload or global installation"}
    # Final archive checks below must all pass for this script to succeed.
    (V / "package-check.json").write_text(json.dumps(checks, indent=2) + "\n")
    records = [write_zip("graph-loop.zip", skill_files), write_zip("graph-loop-review-bundle.zip", source_files + sorted(generated))]
    for record in records:
        with zipfile.ZipFile(BASE / record["file"]) as z:
            require(not any(value in z.read(name) for name in z.namelist() for value in private_values), "sensitive value in archive")
    (V / "archive-manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps({"checks": checks, "archives": records}, indent=2))


if __name__ == "__main__":
    main()
