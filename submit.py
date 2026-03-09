#!/usr/bin/env python3
"""Submit an entry to the tc1-leaderboard.

Validates your entry locally, creates a branch and PR, monitors CI,
and reports back with pass/fail status and feedback.

Usage:
    python submit.py                    # auto-detects entries/{github-username}
    python submit.py entries/my-team    # explicit entry directory
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# ── Helpers ──────────────────────────────────────────────────────────────

PASS = "\033[32m\u2713\033[0m"
FAIL = "\033[31m\u2717\033[0m"
WARN = "\033[33m\u26A0\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

STATUS_ICON = {"pass": PASS, "warn": WARN, "fail": FAIL}


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def run_or_die(cmd: list[str], msg: str) -> str:
    r = run(cmd)
    if r.returncode != 0:
        print(f"{FAIL} {msg}")
        err = (r.stderr or r.stdout or "").strip()
        if err:
            print(f"   {DIM}{err}{RESET}")
        sys.exit(1)
    return r.stdout.strip()


def gh_username() -> str | None:
    r = run(["gh", "auth", "status", "--active", "-t"])
    text = r.stdout + r.stderr
    for line in text.splitlines():
        if "Logged in to" in line and "account" in line:
            # "Logged in to github.com account USER ..."
            parts = line.split("account")
            if len(parts) >= 2:
                return parts[1].strip().split()[0].strip("()")
    # Fallback: try `gh api user`
    r2 = run(["gh", "api", "user", "-q", ".login"])
    if r2.returncode == 0 and r2.stdout.strip():
        return r2.stdout.strip()
    return None


# ── Local validation ────────────────────────────────────────────────────

def validate_locally(entry_dir: Path) -> dict:
    """Run the validation pipeline locally and return the report."""
    ci_dir = Path(__file__).resolve().parent / "ci"
    sys.path.insert(0, str(ci_dir))
    from validate import validate_entry
    return validate_entry(entry_dir, commit="local")


def print_report(report: dict) -> None:
    """Print a human-friendly summary of validation results."""
    team = report["team"]
    scores = report["scores"]
    total = scores["total"]

    print()
    print(f"{BOLD}Entry: {team}{RESET}")
    print(f"  Sequences: {report['n_sequences']}   Families: {report['n_families']}")
    print()

    # Checks
    print(f"{BOLD}Checks:{RESET}")
    for cat, info in report["checks"].items():
        icon = STATUS_ICON.get(info["status"], "?")
        label = cat.replace("_", " ").title()
        print(f"  {icon} {label}")
        for msg in info.get("messages", []):
            print(f"    {DIM}{msg}{RESET}")

    # Per-sequence issues (only show sequences with issues)
    issues = report.get("per_sequence_issues", {})
    seqs_with_issues = {k: v for k, v in issues.items() if v}
    if seqs_with_issues:
        print()
        print(f"{BOLD}Per-sequence issues:{RESET}")
        for sid, msgs in seqs_with_issues.items():
            print(f"  {WARN} {sid}")
            for msg in msgs:
                print(f"    {DIM}{msg}{RESET}")

    # Scores
    print()
    print(f"{BOLD}Scores:{RESET}")
    for component in ["diversity", "annotation", "functionality", "size"]:
        val = scores.get(component, 0)
        bar = bar_chart(val, 1.0, 20)
        print(f"  {component:15s} {bar} {val:.2f}")
    print(f"  {'':15s} {'─' * 26}")
    bar = bar_chart(total, 100, 20)
    print(f"  {BOLD}{'total':15s}{RESET} {bar} {BOLD}{total:.1f}{RESET}/100")


def bar_chart(value: float, max_val: float, width: int = 20) -> str:
    frac = min(1.0, value / max_val) if max_val > 0 else 0
    filled = int(frac * width)
    if frac > 0.7:
        color = "\033[32m"
    elif frac > 0.4:
        color = "\033[33m"
    else:
        color = "\033[31m"
    return f"{color}{'█' * filled}{'░' * (width - filled)}{RESET}"


def has_hard_fail(report: dict) -> bool:
    return any(
        report["checks"][cat]["status"] == "fail"
        for cat in ["format", "annotation"]
    )


# ── Git + PR ─────────────────────────────────────────────────────────────

def create_pr(entry_dir: Path, team: str) -> str | None:
    """Create a branch, commit, push, and open a PR. Returns the PR URL."""
    branch = f"entry/{team}"

    # Check for uncommitted changes in the entry dir
    r = run(["git", "status", "--porcelain", str(entry_dir)])
    if not r.stdout.strip():
        # Maybe already committed — check if branch exists
        r2 = run(["git", "rev-parse", "--verify", f"refs/heads/{branch}"])
        if r2.returncode == 0:
            print(f"{DIM}Branch {branch} already exists.{RESET}")
        else:
            print(f"{FAIL} No changes found in {entry_dir}. Stage and commit your entry first,")
            print(f"   or add new files to {entry_dir}/ and re-run this script.")
            return None

    # Ensure we're on main and up to date
    current = run_or_die(["git", "branch", "--show-current"], "Could not determine current branch")

    # Create or switch to entry branch
    r = run(["git", "rev-parse", "--verify", f"refs/heads/{branch}"])
    if r.returncode == 0:
        run_or_die(["git", "checkout", branch], f"Could not switch to branch {branch}")
        # Merge latest main
        run(["git", "merge", "main", "--no-edit"])
    else:
        if current != "main":
            run_or_die(["git", "checkout", "main"], "Could not switch to main")
        run_or_die(["git", "pull", "--ff-only"], "Could not update main")
        run_or_die(["git", "checkout", "-b", branch], f"Could not create branch {branch}")

    # Stage and commit entry files
    run(["git", "add", str(entry_dir)])
    r = run(["git", "diff", "--cached", "--quiet"])
    if r.returncode != 0:
        run_or_die(
            ["git", "commit", "-m", f"Submit entry: {team}"],
            "Could not commit",
        )

    # Push
    print(f"  Pushing branch {BOLD}{branch}{RESET}...")
    run_or_die(
        ["git", "push", "-u", "origin", branch, "--force-with-lease"],
        "Could not push branch",
    )

    # Create PR (or find existing)
    r = run(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"])
    if r.returncode == 0 and r.stdout.strip():
        url = r.stdout.strip()
        print(f"  PR already exists: {url}")
    else:
        url = run_or_die(
            ["gh", "pr", "create",
             "--title", f"Entry: {team}",
             "--body", f"Automated submission of `entries/{team}/`.\n\nCreated by `submit.py`.",
             "--head", branch,
             "--base", "main"],
            "Could not create PR",
        )
        print(f"  PR created: {url}")

    # Switch back to main
    run(["git", "checkout", "main"])
    return url


def wait_for_ci(pr_url: str, timeout: int = 300) -> bool:
    """Poll the PR's CI checks until they complete or timeout."""
    pr_ref = pr_url  # gh pr checks accepts URL
    start = time.time()
    spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0

    while time.time() - start < timeout:
        r = run(["gh", "pr", "checks", pr_ref, "--json",
                 "name,state,conclusion", "-q", "."])
        if r.returncode != 0:
            time.sleep(5)
            continue

        try:
            checks = json.loads(r.stdout)
        except json.JSONDecodeError:
            time.sleep(5)
            continue

        if not checks:
            sys.stdout.write(f"\r  {spinner[i % len(spinner)]} Waiting for checks to start...")
            sys.stdout.flush()
            i += 1
            time.sleep(5)
            continue

        all_done = all(c.get("state") == "COMPLETED" for c in checks)

        if all_done:
            print(f"\r  {'  ' * 30}\r", end="")  # clear spinner
            all_passed = all(
                c.get("conclusion") in ("SUCCESS", "NEUTRAL", "SKIPPED")
                for c in checks
            )
            for c in checks:
                name = c.get("name", "?")
                conclusion = c.get("conclusion", "?")
                icon = PASS if conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED") else FAIL
                print(f"  {icon} {name}: {conclusion.lower()}")
            return all_passed

        # Show progress
        pending = [c["name"] for c in checks if c.get("state") != "COMPLETED"]
        sys.stdout.write(
            f"\r  {spinner[i % len(spinner)]} Waiting for: {', '.join(pending[:3])}"
            f"{'...' if len(pending) > 3 else ''}   "
        )
        sys.stdout.flush()
        i += 1
        time.sleep(10)

    print(f"\n  {WARN} Timed out after {timeout}s. Check the PR manually.")
    return False


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Validate and submit a tc1-leaderboard entry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="If no entry path is given, auto-detects entries/{your-github-username}/.",
    )
    parser.add_argument("entry", nargs="?", help="Path to entry directory (e.g. entries/my-team)")
    parser.add_argument("--no-pr", action="store_true", help="Only validate locally, don't create a PR")
    parser.add_argument("--no-wait", action="store_true", help="Create PR but don't wait for CI")
    parser.add_argument("--timeout", type=int, default=300, help="CI wait timeout in seconds (default: 300)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent

    # Resolve entry directory
    if args.entry:
        entry_dir = Path(args.entry)
        if not entry_dir.is_absolute():
            entry_dir = root / entry_dir
    else:
        user = gh_username()
        if not user:
            print(f"{FAIL} Could not detect GitHub username. Run `gh auth login` or pass entry path explicitly.")
            sys.exit(1)
        entry_dir = root / "entries" / user.lower()
        print(f"{DIM}Auto-detected entry: {entry_dir.relative_to(root)}{RESET}")

    team = entry_dir.name

    if not entry_dir.is_dir():
        print(f"{FAIL} Entry directory not found: {entry_dir}")
        print(f"   Create it with your protein.sto, dna.sto, and provenance.tsv files.")
        sys.exit(1)

    # ── Step 1: Local validation ─────────────────────────────────────────
    print(f"\n{BOLD}=== Local validation ==={RESET}")

    report = validate_locally(entry_dir)
    print_report(report)

    if has_hard_fail(report):
        print(f"\n{FAIL} {BOLD}Entry has hard failures. Fix the issues above before submitting.{RESET}")
        sys.exit(1)

    total = report["scores"]["total"]
    if total == 0:
        print(f"\n{WARN} Entry scored 0. You can still submit, but consider fixing issues first.")
    else:
        print(f"\n{PASS} Local validation passed (score: {total:.1f})")

    if args.no_pr:
        sys.exit(0)

    # ── Step 2: Create PR ────────────────────────────────────────────────
    print(f"\n{BOLD}=== Creating PR ==={RESET}")

    # Check gh is available
    r = run(["gh", "auth", "status"])
    if r.returncode != 0:
        print(f"{FAIL} GitHub CLI not authenticated. Run `gh auth login` first.")
        sys.exit(1)

    pr_url = create_pr(entry_dir, team)
    if not pr_url:
        sys.exit(1)

    if args.no_wait:
        print(f"\n{PASS} PR created. Monitor it at: {pr_url}")
        sys.exit(0)

    # ── Step 3: Wait for CI ──────────────────────────────────────────────
    print(f"\n{BOLD}=== Waiting for CI ==={RESET}")

    passed = wait_for_ci(pr_url, timeout=args.timeout)

    if passed:
        print(f"\n{PASS} {BOLD}All checks passed!{RESET}")
        print(f"   Your PR will be auto-merged if scoped to entries/{team}/.")
        print(f"   PR: {pr_url}")
    else:
        print(f"\n{FAIL} {BOLD}CI checks failed.{RESET}")
        print(f"   Check the logs at: {pr_url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
