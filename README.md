# ITm Seed Dataset Leaderboard

A competitive leaderboard for curated seed datasets of **IS630/Tc1/mariner (ITm)** transposable elements.

## What is this?

This is Stage 1 of a project to train a DNA language model on the ITm transposon superfamily. The goal is to assemble a high-quality, phylogenetically diverse, well-annotated seed collection of autonomous ITm transposons with strong evidence of functionality.

Teams submit curated entries. A CI pipeline validates each submission and assigns a score. The leaderboard ranks all submissions.

## Quick start

The easiest way to submit is with the included `submit.py` script, which validates locally, creates a PR, and monitors CI:

```bash
# Install dependencies
pip install -r ci/requirements.txt

# Validate and submit (auto-detects entries/{your-github-username}/)
python submit.py

# Or specify your entry explicitly
python submit.py entries/my-team
```

The script will:
1. Run all validation checks locally and show a detailed score report
2. Create a branch and PR for your entry
3. Wait for CI checks to pass and report the result

Additional options:
```bash
python submit.py --no-pr       # Validate locally only, don't create a PR
python submit.py --no-wait     # Create PR but don't wait for CI
python submit.py --timeout 600 # Wait up to 10 minutes for CI (default: 5 min)
```

## How to submit (manual)

If you prefer to submit manually:

1. **Fork this repo.**
2. Create a directory `entries/{your-github-username}/` containing:
   - `protein.sto` — Stockholm protein alignment with catalytic triad annotation
   - `dna.sto` — Multi-Stockholm DNA sequences with element structure annotation
   - `provenance.tsv` — Tab-separated metadata table
   - (Optional) PDB structure files
3. **Open a pull request** to `main`.
4. CI runs validation on your entry and reports pass/fail on the PR.
5. If the **only** files you changed are inside `entries/{your-github-username}/`, the PR is **automatically approved and merged**. No maintainer action needed.
6. After merge, the leaderboard updates with your score.

> **Important:** Your entry directory name must match your GitHub username (lowercase). PRs that modify files outside your own entry directory require manual review.

To **update** your entry, push a new PR modifying files in your directory. To **withdraw**, open a PR that deletes your entry directory.

See [CLAUDE.md](CLAUDE.md) for the full format specification and [POLICY.md](POLICY.md) for scoring details.

## Scoring

Entries are scored on a 0–100 scale based on four components:

| Component | Weight | What it rewards |
|-----------|--------|-----------------|
| Sequence diversity | 40% | Phylogenetic breadth across ITm families |
| Annotation quality | 25% | Correct and complete annotations |
| Evidence of functionality | 20% | Near-identical paralogs, structures, literature |
| Collection size | 15% | Enough sequences to seed a model |

Hard-fail checks (format errors, annotation inconsistencies) result in a score of 0.

## Leaderboard

**[View the live leaderboard](https://ihh.github.io/tc1-leaderboard/)**

Scores are also available as JSON:
- `leaderboard.json` — ranked summary
- `scores/{team}.json` — detailed per-team results

## Entry format summary

- **`protein.sto`**: Stockholm 1.0 alignment with `#=GC catalytic_triad` marking D, d, E (or D) positions.
- **`dna.sto`**: One Stockholm block per element. Each block has one sequence and a `#=GC element_structure` line using characters: `5 3 < > A B 0 1 2 n t .`
- **`provenance.tsv`**: Required columns: `id`, `family`, `host_species`, `host_taxid`, `assembly`, `chrom`, `start`, `end`, `strand`, `source`, `reference`.

See [CLAUDE.md](CLAUDE.md) for the complete specification.
