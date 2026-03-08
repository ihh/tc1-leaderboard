#!/usr/bin/env python3
"""Main validation and scoring script for ITm seed leaderboard entries.

Usage:
    python ci/validate.py --entry entries/team-name [--commit SHA]

Validates the entry, computes a score, and writes results to
scores/{team}.json and updates leaderboard.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure ci/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import CheckResult
from checks.stockholm import parse_protein_sto, iter_dna_blocks
from checks.cross_reference import parse_provenance, check_cross_references
from checks.annotation import check_catalytic_triad, check_element_structure
from checks.protein import check_protein
from checks.dna import check_dna
from checks.provenance import check_provenance
from checks.structures import check_structures
from checks.scoring import compute_total_score


def validate_entry(entry_dir: Path, commit: str = "") -> dict:
    """Validate a single entry directory and return the score report.

    Returns a dict suitable for writing as scores/{team}.json.
    """
    team = entry_dir.name
    results: dict[str, CheckResult] = {
        "format": CheckResult(),
        "annotation": CheckResult(),
        "protein": CheckResult(),
        "dna": CheckResult(),
        "provenance": CheckResult(),
        "structures": CheckResult(),
    }
    per_seq_issues: dict[str, list[str]] = {}

    # ── Check required files exist ───────────────────────────────────────
    protein_path = entry_dir / "protein.sto"
    dna_path = entry_dir / "dna.sto"
    prov_path = entry_dir / "provenance.tsv"

    for p in [protein_path, dna_path, prov_path]:
        if not p.exists():
            results["format"].fail(f"Missing required file: {p.name}")

    if not results["format"].passed:
        return _build_report(team, commit, results, per_seq_issues, 0, set())

    # ── Parse files ──────────────────────────────────────────────────────
    protein_block = parse_protein_sto(protein_path, results["format"])
    provenance_rows = parse_provenance(prov_path, results["format"])

    # Parse dna.sto blocks
    dna_blocks: dict[str, object] = {}
    if results["format"].passed:
        for block in iter_dna_blocks(dna_path, results["format"]):
            sid = block.seq_ids[0]
            dna_blocks[sid] = block

    if protein_block is None or provenance_rows is None:
        return _build_report(team, commit, results, per_seq_issues, 0, set())

    # ── Cross-reference checks ───────────────────────────────────────────
    protein_ids = protein_block.seq_ids
    dna_ids = list(dna_blocks.keys())
    check_cross_references(protein_ids, dna_ids, provenance_rows, results["format"])

    n_sequences = len(protein_ids)

    if not results["format"].passed:
        return _build_report(team, commit, results, per_seq_issues, n_sequences, set())

    # ── Build lookup tables ──────────────────────────────────────────────
    families_by_id = {row["id"]: row.get("family", "") for row in provenance_rows}
    families_set = {row.get("family", "") for row in provenance_rows} - {""}

    # ── Annotation checks ────────────────────────────────────────────────
    triad_columns = check_catalytic_triad(protein_block, results["annotation"])

    for sid in protein_ids:
        per_seq_issues.setdefault(sid, [])
        dna_block = dna_blocks.get(sid)
        if dna_block is None:
            continue
        # Get ungapped protein sequence for this ID
        prot_seq = protein_block.sequences.get(sid, "")
        check_element_structure(
            dna_block, prot_seq, results["annotation"], per_seq_issues[sid]
        )

    # ── Protein-level checks ─────────────────────────────────────────────
    check_protein(
        protein_block, triad_columns, families_by_id,
        results["protein"], per_seq_issues,
    )

    # ── DNA-level checks ─────────────────────────────────────────────────
    for sid in protein_ids:
        dna_block = dna_blocks.get(sid)
        if dna_block is None:
            continue
        family = families_by_id.get(sid, "")
        check_dna(dna_block, family, results["dna"], per_seq_issues.setdefault(sid, []))

    # ── Provenance checks ────────────────────────────────────────────────
    check_provenance(provenance_rows, results["provenance"], per_seq_issues)

    # ── Structure checks ─────────────────────────────────────────────────
    protein_lengths = {
        sid: len(seq.replace("-", "").replace(".", ""))
        for sid, seq in protein_block.sequences.items()
    }
    check_structures(entry_dir, provenance_rows, protein_lengths, results["structures"])

    # ── Scoring ──────────────────────────────────────────────────────────
    return _build_report(
        team, commit, results, per_seq_issues,
        n_sequences, families_set,
        protein_block=protein_block,
        provenance_rows=provenance_rows,
    )


def _build_report(
    team: str,
    commit: str,
    results: dict[str, CheckResult],
    per_seq_issues: dict[str, list[str]],
    n_sequences: int,
    families_set: set[str],
    protein_block=None,
    provenance_rows=None,
) -> dict:
    """Assemble the score report dict."""
    if protein_block is not None and provenance_rows is not None:
        scores = compute_total_score(
            protein_block, families_set, results,
            provenance_rows, n_sequences,
        )
    else:
        scores = {
            "diversity": 0.0, "annotation": 0.0,
            "functionality": 0.0, "size": 0.0, "total": 0.0,
        }

    # Embed alignment data for the web viewer
    alignment = None
    if protein_block is not None:
        alignment = {
            "sequences": {
                sid: seq for sid, seq in protein_block.sequences.items()
            },
            "catalytic_triad": protein_block.gc.get("catalytic_triad", ""),
        }

    report = {
        "team": team,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "n_sequences": n_sequences,
        "n_families": len(families_set),
        "checks": {k: v.to_dict() for k, v in results.items()},
        "scores": scores,
        "per_sequence_issues": per_seq_issues,
    }
    if alignment:
        report["alignment"] = alignment
    return report


def update_leaderboard(scores_dir: Path, output_path: Path) -> None:
    """Read all score files and produce a ranked leaderboard.json."""
    entries = []
    for score_file in sorted(scores_dir.glob("*.json")):
        try:
            data = json.loads(score_file.read_text())
            entries.append({
                "team": data["team"],
                "score": data["scores"]["total"],
                "n_sequences": data.get("n_sequences", 0),
                "n_families": data.get("n_families", 0),
                "commit": data.get("commit", ""),
                "scores": data.get("scores", {}),
            })
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: cannot read {score_file}: {e}", file=sys.stderr)

    # Sort by total score descending, then by annotation, then diversity
    entries.sort(
        key=lambda e: (
            e["score"],
            e.get("scores", {}).get("annotation", 0),
            e.get("scores", {}).get("diversity", 0),
        ),
        reverse=True,
    )

    leaderboard = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    output_path.write_text(json.dumps(leaderboard, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Validate an ITm leaderboard entry")
    parser.add_argument("--entry", required=True, help="Path to entry directory")
    parser.add_argument("--commit", default="", help="Git commit SHA")
    parser.add_argument(
        "--scores-dir", default="scores",
        help="Directory for score output files (default: scores/)",
    )
    parser.add_argument(
        "--leaderboard", default="leaderboard.json",
        help="Path for leaderboard output (default: leaderboard.json)",
    )
    args = parser.parse_args()

    entry_dir = Path(args.entry)
    scores_dir = Path(args.scores_dir)
    leaderboard_path = Path(args.leaderboard)
    team = entry_dir.name

    # If the entry directory was deleted, remove its score and rebuild
    if not entry_dir.is_dir():
        score_path = scores_dir / f"{team}.json"
        if score_path.exists():
            score_path.unlink()
            print(f"Removed {score_path} (entry was deleted)")
            update_leaderboard(scores_dir, leaderboard_path)
            print(f"Updated {leaderboard_path}")
        else:
            print(f"Nothing to do: {entry_dir} does not exist and has no score file")
        sys.exit(0)

    report = validate_entry(entry_dir, commit=args.commit)

    # Write score file
    scores_dir.mkdir(parents=True, exist_ok=True)
    score_path = scores_dir / f"{team}.json"
    score_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {score_path}")

    # Update leaderboard
    update_leaderboard(scores_dir, leaderboard_path)
    print(f"Updated {leaderboard_path}")

    # Print summary
    total = report["scores"]["total"]
    status = "PASS" if total > 0 else "FAIL"
    print(f"\n{team}: {status} (score: {total})")

    # Print any failures
    for cat, check in report["checks"].items():
        if check["status"] == "fail":
            for msg in check["messages"]:
                print(f"  FAIL [{cat}]: {msg}")

    # Exit with error if hard fail
    has_hard_fail = any(
        report["checks"][cat]["status"] == "fail"
        for cat in ["format", "annotation"]
    )
    if has_hard_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
