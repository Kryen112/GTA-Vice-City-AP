"""Stop hook that forces a code review when watched source changes.

Reads the hook input JSON on stdin. When the working-tree state of the
watched directories differs from the last reviewed state, the stop is
blocked once with an instruction to run the code-reviewer subagent. The
state marker lives under .git so it never enters the repository. Any git
failure allows the stop; a broken hook must never trap the session.
"""

import hashlib
import json
import pathlib
import subprocess
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WATCHED_DIRECTORIES = ["apworld", "client", "mod", "scripts"]
STATE_FILE = REPOSITORY_ROOT / ".git" / "claude-code-review-digest"

REVIEW_INSTRUCTION = (
    "Source under apworld/, client/, mod/, or scripts/ changed this turn. "
    "Run the code-reviewer subagent on the current diff (git diff HEAD plus "
    "untracked files in those directories), report its findings, and fix "
    "any blocker-severity findings before stopping. This gate fires once "
    "per new working-tree state."
)


def run_git(arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def untracked_file_fingerprints(status_output: str) -> str:
    fingerprints = []
    for line in status_output.splitlines():
        if not line.startswith("??"):
            continue
        path = REPOSITORY_ROOT / line[3:].strip()
        if path.is_file():
            stat = path.stat()
            fingerprints.append(f"{path}|{stat.st_size}|{stat.st_mtime_ns}")
    return "\n".join(fingerprints)


def watched_state() -> tuple[str, bool]:
    status = run_git(["status", "--porcelain", "-uall", "--", *WATCHED_DIRECTORIES])
    diff = run_git(["diff", "HEAD", "--", *WATCHED_DIRECTORIES])
    combined = status + diff + untracked_file_fingerprints(status)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return digest, bool(status or diff)


def main() -> int:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        hook_input = {}
    if hook_input.get("stop_hook_active"):
        return 0
    try:
        digest, has_changes = watched_state()
    except (RuntimeError, OSError):
        return 0
    if not has_changes:
        return 0
    try:
        previous = STATE_FILE.read_text(encoding="utf-8")
    except OSError:
        previous = ""
    if digest == previous:
        return 0
    try:
        STATE_FILE.write_text(digest, encoding="utf-8")
    except OSError:
        return 0
    print(json.dumps({"decision": "block", "reason": REVIEW_INSTRUCTION}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
