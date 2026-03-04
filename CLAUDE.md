# CLAUDE.md — tc1-leaderboard

## Project context

This repository hosts a competitive leaderboard for curated seed datasets of IS630/Tc1/mariner (ITm) transposable elements. It is the first stage of a larger project to train a DNA language model on the ITm superfamily.

The goal of this stage is to assemble a high-quality, well-annotated, phylogenetically diverse seed collection of autonomous ITm transposons with strong evidence of functionality. Teams submit entries by pushing a subdirectory into the `entries/` folder. A CI pipeline validates each submission and assigns a score. Scores are committed to a parallel `scores/` directory.

This seed dataset will later be used to query genomic databases at scale (the "big data" stage, scored via a separate leaderboard against an S3 bucket). The validation logic written here should be designed for reuse in that context.

## Repository layout

```
tc1-leaderboard/
├── CLAUDE.md                  # This file
├── README.md                  # Public-facing description
├── entries/
│   ├── team-alpha/            # One subdirectory per submission
│   │   ├── protein.sto        # Protein alignment (Stockholm)
│   │   ├── dna.sto            # DNA sequences (multi-Stockholm)
│   │   ├── provenance.tsv     # Provenance table
│   │   ├── 3HOT.pdb           # Optional: PDB structures
│   │   └── ...
│   └── team-beta/
│       └── ...
├── scores/
│   ├── team-alpha.json         # Validation results + score
│   └── team-beta.json
├── leaderboard.json            # Aggregated ranked leaderboard
├── ci/
│   ├── validate.py             # Main validation + scoring script
│   ├── checks/                 # Modular validation checks
│   │   ├── stockholm.py        # Stockholm format parsing and validation
│   │   ├── annotation.py       # Annotation line checks
│   │   ├── protein.py          # Protein-level checks (ORF, triad, domains)
│   │   ├── dna.py              # DNA-level checks (TIRs, length, composition)
│   │   ├── cross_reference.py  # ID consistency across files
│   │   ├── provenance.py       # Provenance metadata checks
│   │   ├── structures.py       # PDB file validation
│   │   └── scoring.py          # Score computation
│   ├── requirements.txt
│   └── conftest.py
└── .github/
    └── workflows/
        └── validate.yml        # CI workflow
```

## Entry format specification

### Directory structure

Each entry is a subdirectory of `entries/` named after the team or contributor (lowercase, alphanumeric + hyphens only). The directory must contain at minimum `protein.sto`, `dna.sto`, and `provenance.tsv`. It may optionally contain PDB files.

### `protein.sto` — Protein alignment

A single Stockholm-format multiple sequence alignment of all transposase protein sequences in the entry. All sequences in the alignment must have IDs that match between this file and `dna.sto`.

Required features:

- **Format:** Stockholm 1.0, single alignment block (may be interleaved).
- **Sequences:** Amino acid sequences of translated transposases, aligned. Standard one-letter codes. Gaps as `.` or `-`.
- **`#=GC catalytic_triad` annotation line:** A per-column annotation marking the catalytic residues. Use `D` for the first aspartate, `d` for the second aspartate (or second D in DDD motifs), and `E` for the glutamate (or `D` for families with a third aspartate, e.g. DDD motifs). All other columns marked `.`. This line must have exactly 2–3 marked positions depending on the triad type.

Example (abbreviated):

```
# STOCKHOLM 1.0
#=GF ID DD34D_mariner_seed
#=GF DE Curated mariner transposase alignment

Mos1_Dmaur/1-345     MKQRK...FLHDNA...PTCWDE...LKGLKP
Himar1_Hirr/1-340    MKKRK...FLHDNA...PTCWDE...LKGLKP
Hsmar1_Hsap/1-343    MKRRK...FLHDNA...PTCWDE...LKGLKP
#=GC catalytic_triad ...........1.........23.........
//
```

The `#=GF` lines are optional but encouraged for documenting the family and any curation notes.

### `dna.sto` — DNA sequences (multi-Stockholm)

A concatenation of Stockholm-format blocks, one block per element. Each block contains exactly one DNA sequence and one per-column annotation line (`#=GC element_structure`). Blocks are separated by `//`.

Each DNA sequence represents a single transposon instance extracted from a genome, oriented so the transposon is on the forward (coding) strand. Include 100–200 bp of flanking genomic sequence on each side.

**Sequence ID** must match the corresponding protein ID in `protein.sto`. If a single protein entry corresponds to multiple genomic copies (paralogs), use the ID for the "best" copy (highest quality, most intact) and list the others in `provenance.tsv`.

**`#=GC element_structure` annotation line:** A per-column character string annotating every position. Characters:

| Character | Meaning |
|-----------|---------|
| `5` | 5′ flanking genomic sequence |
| `3` | 3′ flanking genomic sequence |
| `<` | Left (5′) TIR |
| `>` | Right (3′) TIR |
| `A` | TA target site duplication, 5′ side (the T and A flanking the left TIR) |
| `B` | TA target site duplication, 3′ side (the T and A flanking the right TIR) |
| `0` | First codon position in transposase ORF |
| `1` | Second codon position in transposase ORF |
| `2` | Third codon position in transposase ORF |
| `n` | Intron (within the transposase gene) |
| `t` | Transposon interior, non-coding (between TIR and ORF, UTR-like) |
| `.` | Gap (if any padding is needed; should be rare in single-sequence blocks) |

The annotation must be consistent: the region marked `012012...` must translate (after splicing out `n` regions) to the protein in `protein.sto`. The `<` region must be the reverse complement of the `>` region (approximately — imperfect TIRs are acceptable but should be close). `A` and `B` annotations should each span exactly 2 columns (the TA dinucleotide).

Example (abbreviated):

```
# STOCKHOLM 1.0
#=GF ID Mos1_Dmaur

Mos1_Dmaur             ACGTACGT TA CAGTGGTTAC GTAAA ATG...AAA...tga GTTAG GTAACCACTG TA TGCATGCA
#=GC element_structure 55555555 AA <<<<<<<<<< ttttt 012...012...012 ttttt >>>>>>>>>> BB 33333333
//
```

(The above is schematic. In practice, the sequence is a single unwrapped or interleaved string with no internal spaces or periods; periods shown here only for visual clarity.)

### `provenance.tsv` — Provenance metadata

Tab-separated file with one row per element. Required columns:

| Column | Description |
|--------|-------------|
| `id` | Sequence ID, matching `protein.sto` and `dna.sto` |
| `family` | Family classification (e.g. `DD34D_mariner`, `DD34E_Tc1`, `DDxD_pogo`, `IS630`) |
| `host_species` | Binomial species name |
| `host_taxid` | NCBI Taxonomy ID |
| `assembly` | Genome assembly accession (e.g. `GCF_000001405.40`) |
| `chrom` | Chromosome or scaffold name |
| `start` | 1-based start coordinate (of the flanking region included) |
| `end` | End coordinate |
| `strand` | `+` or `-` (original strand in the assembly; the sequence in `dna.sto` is always oriented forward) |
| `source` | How this element was identified (e.g. `Dfam`, `RepeatMasker`, `literature`, `BLASTp`, `manual`) |
| `reference` | Publication DOI or database accession, if applicable |

Optional columns (scored as bonuses):

| Column | Description |
|--------|-------------|
| `paralog_hits` | Semicolon-separated list of other genomic loci with strong protein hits to this transposase (miniprot or tBLASTn). Format: `chrom:start-end:identity`. Evidence of recent transpositional activity. |
| `max_paralog_identity` | Maximum nucleotide identity among paralog hits (float, 0–1). Values > 0.99 are strong evidence of recent activity. |
| `copy_number` | Estimated copy count of this family in this genome |
| `pdb_file` | Filename of a PDB structure in this directory, if available |
| `pdb_source` | `experimental`, `alphafold`, `esmfold`, or `colabfold` |
| `confidence_tier` | 1–4 or `MITE`, per the project tier definitions |
| `notes` | Free text |

### PDB files (optional)

Experimental or predicted 3D structures of the transposase, named to match the sequence ID (e.g. `Mos1_Dmaur.pdb`). Cross-referenced via the `pdb_file` column in `provenance.tsv`. Multiple structures per entry are allowed (e.g. monomer and dimer predictions). Use suffixes like `Mos1_Dmaur_dimer.pdb` as needed.

PDB files are validated for:
- Parseable as PDB or mmCIF format
- Chain length roughly consistent with the protein sequence length in `protein.sto`
- If source is `alphafold` or `esmfold`, presence of B-factor column repurposed as pLDDT

## CI validation pipeline

On every push that modifies anything under `entries/`, the CI workflow runs `ci/validate.py` on each modified entry directory. The script:

1. **Parses and validates format** of `protein.sto`, `dna.sto`, and `provenance.tsv`.
2. **Checks annotation consistency** (see below).
3. **Computes a score** (see below).
4. **Writes results** to `scores/{team}.json` and updates `leaderboard.json`.
5. **Commits score files** back to the repo (or posts as a PR comment, TBD).

### Validation checks

All checks produce a pass/fail/warn status and a message. An entry with any hard failure gets a score of 0.

#### Format checks (hard fail if violated)

- `protein.sto` is valid Stockholm 1.0 with a `#=GC catalytic_triad` line.
- `dna.sto` is valid multi-Stockholm with one sequence per block and a `#=GC element_structure` line per block.
- `provenance.tsv` is valid TSV with all required columns present.
- All IDs in `protein.sto` have a corresponding block in `dna.sto` and a row in `provenance.tsv`, and vice versa.
- At least 3 entries in the submission (a single-element submission is not useful as a seed).

#### Annotation consistency checks (hard fail)

- The `catalytic_triad` annotation in `protein.sto` marks exactly 2 or 3 positions, and those positions are D, D, and E (or D/D/D for DDD-triad families) in every aligned sequence (allowing conservative substitutions in degraded copies, but the majority must match, and we don't want degraded copies in the seed set anyway, so that would be heavily dinged for score).
- The `element_structure` annotation in each `dna.sto` block:
  - Uses only the characters defined above.
  - Has `5` and `3` regions flanking the element.
  - Has `A` (exactly 2 columns) immediately before `<` region, and `B` (exactly 2 columns) immediately after `>` region.
  - The `A` columns spell `TA` and the `B` columns spell `TA` in the sequence.
  - The `<` and `>` regions are approximate reverse complements of each other (Hamming distance on reverse complement < 30% of TIR length).
  - The `012` region, when extracted and introns (`n`) spliced out, has length divisible by 3.
  - The `012` region translates to a protein that aligns to the corresponding sequence in `protein.sto` with ≥ 90% identity (allowing for minor annotation errors).

#### Protein-level checks (scored, not hard fail)

- Transposase length is in the expected range for the declared family (roughly 250–450 aa for most ITm families; IS630 may be shorter).
- The catalytic triad spacing matches the declared family (e.g. DD34D has 34 residues between the second D and the E, counted in the ungapped protein).
- Conserved domain check: if Pfam/InterPro annotations are computable in CI, confirm DDE_Tnp_IS630 or DDE_Tnp_1 hit. (May be deferred to a heavier validation pass if HMMER is too slow for CI.)

#### DNA-level checks (scored, not hard fail)

- Total element length (excluding flanking) is in expected range for the declared family.
- TIR length is in expected range (typically 15–200 bp).
- GC content of the ORF is within a plausible range (15–75%).
- No ambiguous bases (`N`) in the ORF region (flanking may have them).

#### Provenance checks (scored)

- `host_taxid` is a valid NCBI Taxonomy ID (check against a bundled taxonomy dump or API).
- `assembly` is a plausible accession format.
- Coordinates are internally consistent (`start` < `end`, `strand` is `+` or `-`).

### Scoring

The score for an entry is a weighted combination of factors designed to reward phylogenetically diverse, well-annotated, high-confidence collections. The total score is normalized to 0–100.

#### Components

**1. Sequence diversity (40% weight)**

Goal: span the phylogenetic space of the ITm superfamily, not pile up near-identical sequences.

- Compute all-vs-all pairwise protein identity from the alignment.
- Diversity score = mean pairwise distance (1 − identity). Higher is better.
- Bonus for covering multiple families (catalytic triad types). Each distinct family represented adds a multiplier.
- Penalty if any pair of sequences has > 95% protein identity (redundancy).

**2. Annotation completeness and correctness (25% weight)**

- Full marks if all annotation consistency checks pass.
- Partial credit for minor issues (e.g. TIR reverse-complement match is imperfect but within tolerance).
- Bonus for optional metadata: `paralog_hits` present (+), `max_paralog_identity` > 0.99 for at least some entries (+), `confidence_tier` assigned (+), PDB structures present (+).

**3. Evidence of functionality (20% weight)**

- Entries with `max_paralog_identity` > 0.99 (near-identical copies in the same genome) receive a strong bonus per such element.
- Entries with experimental PDB structures score higher than predicted structures.
- Entries sourced from literature with experimental validation references score a bonus.
- Entries classified as Tier 1 confidence score highest; Tier 2 less; Tier 3/4 progressively less.

**4. Collection size (15% weight)**

- Logarithmic scaling: score = min(1, log2(N) / log2(target)), where `target` is a configurable parameter (e.g. 64 sequences).
- This rewards having enough sequences to be useful as a seed dataset, but saturates — 200 sequences is not much better than 64 for a seed. The point is to span space, not to be exhaustive.
- Hard penalty if N < 3 (entry is rejected).

#### Score normalization

Each component is scaled to [0, 1], then combined with the weights above to produce a total in [0, 100]. Ties are broken by annotation completeness, then by diversity.

### Score output format

`scores/{team}.json`:

```json
{
  "team": "team-alpha",
  "timestamp": "2026-03-04T12:00:00Z",
  "commit": "abc1234",
  "n_sequences": 42,
  "n_families": 3,
  "checks": {
    "format": {"status": "pass", "messages": []},
    "annotation": {"status": "pass", "messages": []},
    "protein": {"status": "pass", "messages": ["1 sequence outside expected length range"]},
    "dna": {"status": "pass", "messages": []},
    "provenance": {"status": "warn", "messages": ["2 entries missing paralog_hits"]},
    "structures": {"status": "pass", "messages": ["3 PDB files validated"]}
  },
  "scores": {
    "diversity": 0.72,
    "annotation": 0.95,
    "functionality": 0.60,
    "size": 0.88,
    "total": 78.3
  },
  "per_sequence_issues": {
    "Mos1_Dmaur": [],
    "Tc1_Cele": ["TIR reverse-complement match: 82% (below 85% warning threshold)"]
  }
}
```

`leaderboard.json`:

```json
{
  "updated": "2026-03-04T12:00:00Z",
  "entries": [
    {"team": "team-alpha", "score": 78.3, "n_sequences": 42, "n_families": 3, "commit": "abc1234"},
    {"team": "team-beta", "score": 65.1, "n_sequences": 28, "n_families": 2, "commit": "def5678"}
  ]
}
```

## CI workflow

The GitHub Actions workflow (`.github/workflows/validate.yml`) triggers on pushes to `main` that modify files under `entries/`. It:

1. Checks out the repo.
2. Sets up Python with dependencies from `ci/requirements.txt`.
3. Identifies which entry directories were modified.
4. Runs `ci/validate.py --entry entries/{team}` for each modified entry.
5. Commits updated `scores/{team}.json` and `leaderboard.json` back to the repo.

Entries that fail hard validation checks (format errors, missing required files, ID mismatches) receive a score of 0 and a descriptive error in their score file.

## Updating an entry

To update an entry, simply push a new commit modifying files in your `entries/{team}/` directory. The CI will re-run validation and overwrite the previous score. The leaderboard always reflects the latest commit for each team.

## Reuse plan

The validation logic in `ci/checks/` is designed as a library that can be imported and reused. The "big data" leaderboard (Stage 2) will validate entries stored in S3 using the same annotation format and similar checks, extended with:

- Homology index checks (MMseqs2 clustering statistics)
- Scale-appropriate diversity metrics (cannot do all-vs-all at millions of sequences)
- Automated confidence tier assignment (rather than self-reported)
- Cross-entry deduplication (elements submitted by multiple teams)

The core Stockholm parsing, annotation validation, and protein/DNA consistency checks will be shared between both stages.

## Conventions

- **Python 3.11+**. Dependencies in `ci/requirements.txt`. Key libraries: Biopython (Stockholm parsing, sequence manipulation, translation), NumPy (pairwise identity computation).
- **No heavy dependencies in CI.** HMMER, MMseqs2, miniprot, etc. are not run in CI for the seed leaderboard (too slow, too many system dependencies). These are the submitter's responsibility to run before submission. The CI checks *results*, not *re-derives* them.
- **Stockholm parsing** should use Biopython's `Bio.AlignIO` for `protein.sto` and a custom multi-block parser for `dna.sto` (Biopython reads single Stockholm blocks; we need to iterate over `//`-delimited blocks).
- **Sequence IDs** must be alphanumeric plus underscores and hyphens. No spaces, no slashes. Max 80 characters. The portion before the first `/` is the ID proper; anything after `/` is a coordinate range (Stockholm convention) and is optional.
- **Filenames** are case-sensitive. `protein.sto`, `dna.sto`, `provenance.tsv` exactly.

## ITm biology reference (for validation logic)

When implementing or modifying validation checks, keep in mind:

- **Catalytic triad:** The DDD/E motif consists of two aspartates and a glutamate (or third aspartate) that coordinate metal ions in the active site. The naming convention (e.g. DD34D) gives the number of amino acids between the second and third catalytic residue. The first two D residues are typically ~100 residues apart. All three are absolutely conserved in functional transposases.
- **TIRs:** Terminal inverted repeats are recognized by the transposase. They are approximate reverse complements of each other. Length varies by family: mariner ~20–30 bp, Tc1 ~50–60 bp (may have an IR-DR structure with internal direct repeats), pogo variable. Imperfect TIRs are common and biologically real.
- **TA target site duplication:** ITm elements insert at TA dinucleotides, duplicating the TA on both sides of the insertion. This is a hallmark of the superfamily.
- **Introns:** Some ITm transposases contain introns (e.g. C. elegans Tc1 has a single intron). These must be spliced out before translation. The annotation uses `n` for intron positions.
- **Element length:** Autonomous elements typically 1,200–2,500 bp. MITEs (non-autonomous) are 50–800 bp but are not the focus of this leaderboard.
- **Transposase size:** Typically 250–450 amino acids for eukaryotic families. Bacterial IS630 transposases may be shorter (~200–300 aa).
- **Near-identical paralogs:** Multiple copies of the same element at > 99% nucleotide identity within a single genome is strong evidence that the element has transposed recently and is (or very recently was) functional. This is one of the most powerful bioinformatic signals of functionality.

## What Claude should do in this repo

When asked to work on this project, Claude should:

1. **Respect the entry format specification exactly.** The annotation characters, file names, and column definitions are a contract. Do not deviate.
2. **Write validation code that is strict on format, informative on failure.** Error messages should tell the submitter exactly what is wrong and where (sequence ID, column number, expected vs. actual).
3. **Keep scoring logic in `ci/checks/scoring.py` as a standalone module** with clear, documented weight parameters that can be tuned.
4. **Write tests.** The `ci/` directory should include test fixtures (minimal valid and invalid entries) and pytest-based tests for every check.
5. **Design for reuse.** The Stockholm parser, annotation validator, and protein/DNA consistency checks will be reused for the big data leaderboard. Keep them modular and dependency-light.
6. **Do not over-engineer.** This is a research tool, not a production service. Clarity and correctness over abstraction.