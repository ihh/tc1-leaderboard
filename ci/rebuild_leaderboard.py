#!/usr/bin/env python3
"""Rebuild the leaderboard by re-validating all entries.

Usage:
    python ci/rebuild_leaderboard.py [--commit SHA]

Re-runs validation on every entry in entries/, overwrites all score files,
rebuilds leaderboard.json, and copies everything to docs/ for GitHub Pages.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate import validate_entry, update_leaderboard
import json


def main():
    parser = argparse.ArgumentParser(description="Rebuild the full leaderboard")
    parser.add_argument("--commit", default="", help="Git commit SHA (auto-detected if omitted)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    entries_dir = root / "entries"
    scores_dir = root / "scores"
    docs_dir = root / "docs"
    leaderboard_path = root / "leaderboard.json"

    commit = args.commit
    if not commit:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root, text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            commit = ""

    # Find all entry directories
    entry_dirs = sorted(
        d for d in entries_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    if not entry_dirs:
        print("No entries found.")
        return

    # Clear stale scores for entries that no longer exist
    if scores_dir.exists():
        for score_file in scores_dir.glob("*.json"):
            team = score_file.stem
            if not (entries_dir / team).is_dir():
                score_file.unlink()
                print(f"Removed stale score: {score_file.name}")

    # Validate all entries
    scores_dir.mkdir(parents=True, exist_ok=True)
    for entry_dir in entry_dirs:
        team = entry_dir.name
        print(f"=== {team} ===")
        report = validate_entry(entry_dir, commit=commit)
        score_path = scores_dir / f"{team}.json"
        score_path.write_text(json.dumps(report, indent=2) + "\n")

        total = report["scores"]["total"]
        status = "PASS" if total > 0 else "FAIL"
        print(f"  {status} (score: {total})")

    # Rebuild leaderboard
    update_leaderboard(scores_dir, leaderboard_path)
    print(f"\nUpdated {leaderboard_path}")

    # Copy to docs/
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_scores = docs_dir / "scores"
    docs_scores.mkdir(parents=True, exist_ok=True)
    shutil.copy2(leaderboard_path, docs_dir / "leaderboard.json")
    for f in scores_dir.glob("*.json"):
        shutil.copy2(f, docs_scores / f.name)
    # Remove stale docs scores
    for f in docs_scores.glob("*.json"):
        if not (scores_dir / f.name).exists():
            f.unlink()
    print(f"Updated {docs_dir}/")


if __name__ == "__main__":
    main()
