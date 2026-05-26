#!/opt/homebrew/bin/python3
"""Fallback GitHub API push for cron environments where git smart HTTP is denied.

Creates one squashed commit on origin/main from the local diff against origin/main.
Requires GITHUB_TOKEN or GITHUB_BACKUP_TOKEN with repo contents write access.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "MartinPetrov8/real-estate-price-matching"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API = "https://api.github.com"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def request(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {exc.code}: {body}") from exc


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_BACKUP_TOKEN")
    if not token:
        print("missing GITHUB_TOKEN/GITHUB_BACKUP_TOKEN", file=sys.stderr)
        return 2

    message = sys.argv[1] if len(sys.argv) > 1 else "data: Daily pipeline update"
    diff_lines = git("diff", "--name-status", "origin/main..HEAD").splitlines()
    if not diff_lines:
        print("no changes to push")
        return 0

    ref = request("GET", f"/repos/{REPO}/git/ref/heads/main", token)
    base_commit = ref["object"]["sha"]
    base_tree = request("GET", f"/repos/{REPO}/git/commits/{base_commit}", token)["tree"]["sha"]

    tree_entries = []
    for line in diff_lines:
        parts = line.split("\t")
        status, path = parts[0], parts[-1]
        if status == "D":
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue

        with open(os.path.join(ROOT, path), "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
        blob = request(
            "POST",
            f"/repos/{REPO}/git/blobs",
            token,
            {"content": encoded, "encoding": "base64"},
        )
        tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    tree = request("POST", f"/repos/{REPO}/git/trees", token, {"base_tree": base_tree, "tree": tree_entries})
    commit = request(
        "POST",
        f"/repos/{REPO}/git/commits",
        token,
        {"message": message, "tree": tree["sha"], "parents": [base_commit]},
    )
    request("PATCH", f"/repos/{REPO}/git/refs/heads/main", token, {"sha": commit["sha"], "force": False})
    print(f"pushed {commit['sha'][:7]} via GitHub API ({len(tree_entries)} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
