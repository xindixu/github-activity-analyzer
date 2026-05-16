#!/usr/bin/env python3
"""
Copy output/ artifacts to the pr-reports repo and create a git commit.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PREFIX_RE = re.compile(r"^pr_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def output_dir() -> Path:
    return repo_root() / "output"


def default_reports_dir() -> Path:
    env = os.getenv("PR_REPORTS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (repo_root().parent / "pr-reports").resolve()


def prefix_from_csv(csv_path: Path) -> str:
    name = csv_path.name
    if name.endswith("_detailed.csv"):
        return name[: -len("_detailed.csv")]
    if name.endswith("_summarized.csv"):
        return name[: -len("_summarized.csv")]
    raise ValueError(f"Unexpected CSV filename: {name}")


def latest_prefix() -> str:
    output = output_dir()
    candidates = sorted(
        output.glob("pr_*_detailed.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No PR output CSVs found in {output}")
    return prefix_from_csv(candidates[0])


def files_for_prefix(prefix: str) -> list[Path]:
    output = output_dir()
    matches = sorted(output.glob(f"{prefix}*"))
    if not matches:
        raise FileNotFoundError(f"No output files matching {prefix}* in {output}")
    return [p for p in matches if p.is_file()]


def commit_message(prefix: str) -> str:
    match = PREFIX_RE.match(prefix)
    if match:
        start, end = match.group(1), match.group(2)
        repo = os.getenv("GITHUB_REPO", "")
        repo_note = f" ({repo})" if repo else ""
        return f"Add PR reports for {start}–{end}{repo_note}"
    return f"Add PR reports ({prefix})"


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def publish(
    prefix: str,
    reports_dir: Path | None = None,
    *,
    push: bool = False,
) -> bool:
    """Copy output files for prefix into pr-reports and commit. Returns True if committed."""
    dest = (reports_dir or default_reports_dir()).resolve()
    if not dest.is_dir():
        raise FileNotFoundError(f"PR reports directory does not exist: {dest}")
    if not (dest / ".git").is_dir():
        raise RuntimeError(f"Not a git repository: {dest}")

    sources = files_for_prefix(prefix)
    copied_names: list[str] = []
    for src in sources:
        target = dest / src.name
        shutil.copy2(src, target)
        copied_names.append(src.name)

    print(f"📤 Copied {len(copied_names)} file(s) to {dest}:")
    for name in copied_names:
        print(f"   • {name}")

    run_git(dest, "add", *copied_names)
    status = run_git(dest, "status", "--porcelain")
    if not status.stdout.strip():
        print("ℹ️  No changes to commit (files already up to date).")
        return False

    message = commit_message(prefix)
    commit = run_git(dest, "commit", "-m", message)
    if commit.returncode != 0:
        print(commit.stderr or commit.stdout, file=sys.stderr)
        raise RuntimeError("git commit failed")

    print(f"✅ Committed: {message}")

    if push:
        push_result = run_git(dest, "push")
        if push_result.returncode != 0:
            print(push_result.stderr or push_result.stdout, file=sys.stderr)
            raise RuntimeError("git push failed")
        print(f"✅ Pushed to {dest}")

    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish output/ PR reports to the pr-reports repository."
    )
    parser.add_argument(
        "--prefix",
        help="File prefix (e.g. pr_2026-05-09_2026-05-16). Defaults to latest run.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Path to a detailed or summarized CSV (prefix inferred from filename).",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        help="Path to pr-reports clone (default: PR_REPORTS_DIR or ../pr-reports).",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push after commit (or set PUBLISH_PUSH=1).",
    )
    args = parser.parse_args(argv)

    push = args.push or os.getenv("PUBLISH_PUSH", "").lower() in ("1", "true", "yes")

    try:
        if args.csv:
            prefix = prefix_from_csv(args.csv.resolve())
        elif args.prefix:
            prefix = args.prefix.removeprefix("output/").removesuffix("/")
        else:
            prefix = latest_prefix()

        publish(prefix, args.reports_dir, push=push)
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
