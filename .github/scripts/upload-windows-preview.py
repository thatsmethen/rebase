#!/usr/bin/env python3
"""Upload hash-verified CI bytes to an existing draft; never publish or replace.

Uses GitHub's release-list API because draft tags need not resolve through the
release-by-tag endpoint. Only `gh release upload` mutates remote state.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


class Refused(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def inputs(env):
    patterns = {
        "RUN_ID": r"[1-9][0-9]{0,19}",
        "SOURCE_COMMIT": r"[0-9a-f]{40}",
        "EXPECTED_SHA256": r"[0-9a-f]{64}",
        "RELEASE_TAG": r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}",
        "ASSET_NAME": r"[A-Za-z0-9][A-Za-z0-9._-]{0,179}\.zip",
        "GITHUB_REPOSITORY": r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}",
    }
    values = {}
    for key, pattern in patterns.items():
        value = env.get(key, "")
        require(re.fullmatch(pattern, value) is not None, "invalid-" + key.lower())
        require(".." not in value and not value.endswith("."), "unsafe-" + key.lower())
        values[key] = value
    return values


def gh(arguments, *, timeout=120, allow_failure=False):
    # Do not echo subprocess output: errors can include signed download URLs.
    env = dict(os.environ)
    env.pop("GH_DEBUG", None)
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_HOST"] = "github.com"
    try:
        result = subprocess.run(["gh", *arguments], capture_output=True,
                                timeout=timeout, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired):
        if allow_failure:
            return None
        raise Refused("github-command-unavailable-or-timed-out") from None
    if result.returncode:
        if allow_failure:
            return None
        raise Refused("github-command-failed")
    return result.stdout


def api(path, *, pages=False):
    args = ["api", "--method", "GET", "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28", path]
    if pages:
        args += ["--paginate", "--slurp"]
    try:
        value = json.loads(gh(args))
    except (ValueError, TypeError):
        raise Refused("invalid-github-json") from None
    if pages:
        require(isinstance(value, list) and all(isinstance(p, list) for p in value), "invalid-page-list")
        return [item for page in value for item in page]
    return value


def verify_run(run, v):
    require(isinstance(run, dict) and str(run.get("id")) == v["RUN_ID"], "run-id-mismatch")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "run-not-successful")
    require(run.get("head_sha") == v["SOURCE_COMMIT"], "run-commit-mismatch")
    require(run.get("path") == ".github/workflows/windows-application.yml", "wrong-workflow")


def verify_release(release, v):
    require(isinstance(release, dict), "invalid-release")
    require(type(release.get("id")) is int and release["id"] > 0, "invalid-release-id")
    require(release.get("tag_name") == v["RELEASE_TAG"], "release-tag-mismatch")
    require(release.get("draft") is True and release.get("prerelease") is True, "release-not-draft-prerelease")
    require(release.get("target_commitish") == v["SOURCE_COMMIT"], "release-commit-mismatch")


def verify_tag(prefix, v):
    # target_commitish is ignored by GitHub when a tag already exists. A draft
    # may have no tag yet; an existing tag must resolve to the audited commit.
    refs = api(prefix + "/git/matching-refs/tags/" + v["RELEASE_TAG"])
    require(isinstance(refs, list), "invalid-tag-reference-list")
    matches = [r for r in refs if r.get("ref") == "refs/tags/" + v["RELEASE_TAG"]]
    require(len(matches) <= 1, "duplicate-tag-reference")
    if not matches:
        return
    obj = matches[0].get("object", {})
    seen = set()
    for _ in range(16):
        require(isinstance(obj, dict), "invalid-tag-object")
        sha = obj.get("sha", "")
        require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) is not None,
                "invalid-tag-object-sha")
        if obj.get("type") == "commit":
            require(sha == v["SOURCE_COMMIT"], "resolved-tag-commit-mismatch")
            return
        require(obj.get("type") == "tag" and sha not in seen, "invalid-or-cyclic-tag-object")
        seen.add(sha)
        annotation = api(prefix + "/git/tags/" + sha)
        require(isinstance(annotation, dict) and annotation.get("sha") == sha, "tag-object-mismatch")
        obj = annotation.get("object", {})
    raise Refused("tag-chain-too-deep")


def matching_asset(assets, v, size):
    matches = [a for a in assets if a.get("name") == v["ASSET_NAME"]]
    require(len(matches) <= 1, "duplicate-release-asset")
    if not matches:
        return None
    asset = matches[0]
    require(type(asset.get("id")) is int and asset["id"] > 0, "invalid-asset-id")
    require(asset.get("state") == "uploaded" and type(asset.get("size")) is int
            and asset["size"] == size
            and asset.get("digest") == "sha256:" + v["EXPECTED_SHA256"],
            "existing-asset-does-not-match-never-clobbered")
    return asset


def verify_package(evidence, package, v):
    record = evidence / "application-build.json"
    require(record.is_file() and not record.is_symlink() and record.stat().st_size <= 1_048_576,
            "missing-or-invalid-build-receipt")
    try:
        build = json.loads(record.read_bytes())
    except (ValueError, OSError):
        raise Refused("invalid-build-receipt-json") from None
    require(build.get("status") == "passed" and build.get("commit") == v["SOURCE_COMMIT"],
            "build-receipt-not-passed-or-wrong-commit")
    for gate in ["window_smoke_tested", "dependency_closure_checked", "app_local_modules_observed"]:
        require(build.get(gate) is True, "missing-build-gate-" + gate)
    entries = list(package.rglob("*"))
    require(not any(p.is_symlink() for p in entries), "package-artifact-contains-link")
    files = [p for p in entries if p.is_file()]
    require(len(files) == 1 and files[0].suffix == ".zip", "expected-exactly-one-zip")
    archive = files[0]
    info = build.get("package", {})
    size = archive.stat().st_size
    require(type(info.get("bytes")) is int and info["bytes"] == size and size > 0,
            "package-size-mismatch")
    require(archive.name == info.get("name"), "package-name-mismatch")
    require(info.get("sha256") == v["EXPECTED_SHA256"], "expected-hash-differs-from-build")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    require(digest == v["EXPECTED_SHA256"], "downloaded-package-hash-mismatch")
    require(zipfile.is_zipfile(archive), "package-is-not-zip")
    return archive, size


def upload(v):
    repo = v["GITHUB_REPOSITORY"]
    prefix = "repos/" + repo
    verify_run(api(prefix + "/actions/runs/" + v["RUN_ID"]), v)
    releases = api(prefix + "/releases?per_page=100", pages=True)
    matches = [r for r in releases if r.get("tag_name") == v["RELEASE_TAG"]]
    require(len(matches) == 1, "expected-one-existing-release")
    release = matches[0]
    verify_release(release, v)
    verify_tag(prefix, v)
    release_path = prefix + "/releases/" + str(release["id"])

    def verify_current_release():
        verify_release(api(release_path), v)
        verify_tag(prefix, v)

    temp_root = os.environ.get("RUNNER_TEMP", "")
    require(bool(temp_root) and Path(temp_root).is_dir(), "runner-temp-unavailable")
    with tempfile.TemporaryDirectory(prefix="rebase-preview-upload-", dir=temp_root) as temp:
        root = Path(temp)
        for name, folder in [("windows-application-evidence", "evidence"),
                             ("Rebase-Windows-x64-development-" + v["SOURCE_COMMIT"], "package")]:
            gh(["run", "download", v["RUN_ID"], "--repo", repo, "--name", name,
                "--dir", str(root / folder)], timeout=600)
        archive, size = verify_package(root / "evidence", root / "package", v)
        # Revalidate the draft immediately before the sole remote mutation.
        verify_current_release()
        asset = matching_asset(api(release_path + "/assets?per_page=100", pages=True), v, size)
        outcome = "already-uploaded"
        if asset is None:
            destination = root / v["ASSET_NAME"]
            shutil.copyfile(archive, destination)
            # No --clobber, automatic retry, deletion, release edit or publish.
            gh(["release", "upload", v["RELEASE_TAG"], str(destination), "--repo", repo],
               timeout=900, allow_failure=True)
            # A timeout can still have completed remotely; only server evidence
            # confirms success. A partial or different asset remains untouched.
            verify_current_release()
            asset = matching_asset(api(release_path + "/assets?per_page=100", pages=True), v, size)
            require(asset is not None, "upload-not-confirmed")
            outcome = "uploaded"
        verify_current_release()
        return {"schema": "rebase.draft-preview-upload.v1", "status": "passed", "outcome": outcome,
                "repository": repo, "source_run_id": v["RUN_ID"], "source_commit": v["SOURCE_COMMIT"],
                "release_tag": v["RELEASE_TAG"], "release_id": release["id"], "release_remains_draft": True,
                "asset_id": asset["id"], "asset_name": v["ASSET_NAME"], "bytes": size,
                "sha256": v["EXPECTED_SHA256"], "server_digest": asset["digest"],
                "server_state": asset["state"], "binaries_executed": False, "published": False}


def main():
    try:
        receipt = upload(inputs(os.environ))
    except Refused as error:
        receipt = {"schema": "rebase.draft-preview-upload.v1", "status": "failed", "reason": str(error),
                   "published": False}
    except Exception:
        # Never emit exception data or raw subprocess output into public logs.
        receipt = {"schema": "rebase.draft-preview-upload.v1", "status": "failed",
                   "reason": "unexpected-local-error", "published": False}
    encoded = json.dumps(receipt, sort_keys=True)
    if os.environ.get("UPLOAD_RECEIPT"):
        Path(os.environ["UPLOAD_RECEIPT"]).write_text(encoded + "\n")
    print(encoded)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
