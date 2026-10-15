# Audit plan — checking the evidence levels by reading papers

Goal: verify the automatic evidence levels (E3 … U) for the 4,912 positive pairs without reading every paper,
and handle papers whose pairs got **both E2 and E0** (the paper supports one host strain, DeepPBI-KG also pairs its phages with others).

## Why audit papers, not pairs

- 2,273 positives (46%) have a phage that cites a paper; they cite **980 distinct papers**. One paper often backs many pairs
  (the largest, PMID 22282335, backs 182). Reading a paper once settles all of its pairs.
- 2,639 positives (54%) cite **no paper**. Reading cannot change them; their level comes only from database fields, so they only need
  a small check that the code read those fields correctly (tier 4).
- 589 of the 980 papers are free in PMC.

## The four tiers (files: `note/paper_audit.csv`, `note/code_check_pairs.csv`; built by `scripts/paper_audit.py`)

| Tier | What | Papers | Pairs covered | Why |
|---|---|---:|---:|---|
| 1 mixed | Papers whose pairs got both E2/E1 **and** E0 | 19 (17 PMC) | 330 | Directly tests the scenario: did the paper test the *other* strains too? |
| 2 coverage | 10 largest remaining papers | 10 (9 PMC) | 235 | Most pairs per hour of reading |
| 3 random | 30 papers drawn at random (seed 20261011) from the 539 free-PMC papers with E0 pairs | 30 | 76 | Unbiased estimate for the ~950 papers nobody reads |
| 4 code check | 20 random pairs with **no** paper | — | 20 | Confirms the database reading; no paper to read |

Tiers 1–3 together cover **641 pairs** with 59 papers.

## What to record for each paper (one row in `note/paper_audit.csv`)

The row already lists the DeepPBI-KG hosts paired with the paper's phages (`paired_hosts_to_look_for`, with pair counts). Fill in:

1. `strains_used_in_paper` — from Methods ("Bacterial strains", "Strains used in this study" table).
2. `isolation_host_in_paper` — strain used to isolate/propagate each phage.
3. `host_range_table` — yes/no, and where (e.g. "Table 2", "Fig. 3").
4. `result_per_paired_host` — for **each** paired host accession: `ACCESSION:+` (tested, infects), `ACCESSION:-` (tested, no infection),
   `ACCESSION:iso` (isolation/propagation host only), `ACCESSION:nt` (not tested / not mentioned). Example:
   `CP027541:nt; NC_008596:iso`.
5. `checked_by`, `checked_on`, `notes` (page/table, short quote).

Search tips: search the **strain code** of each paired host (and its synonyms in `data/derived/strain_synonyms.csv`), then the
keywords *host range, spot, plaque, EOP, lysis, susceptible, propagated, isolated on*.

## How a paper result turns into pair levels

| `result_per_paired_host` | Pair level |
|---|---|
| `+` | E3_hostrange |
| `-` | E3_hostrange **and** "TESTED NEGATIVE" (contradicts DeepPBI-KG's positive label) |
| `iso` | E2_isolation_strain |
| `nt` | unchanged (E0 confirmed as not supported by this paper) |
| `prophage` | at least E1_annotation_strain (phage is a prophage in this host's genome) |
| `check`, `+?`, `unsearched` | unchanged, counted as pending until a person decides |

`python3 scripts/apply_paper_audit.py` applies these to all pairs of each paper → `data/derived/pair_levels_after_audit.csv` and a summary, both for all results and for rows confirmed by a person only.

## Reading the mixed papers (tier 1)

Possible outcomes for a mixed paper such as PMID 22282335 (phages isolated on *M. smegmatis* mc²155; pairs with mc²155 = E2, with MKD8 = E0):

- Paper tests MKD8 too → those E0 pairs become E3 (+ or −).
- Paper never mentions MKD8 → the MKD8 pairs are **extrapolated** by DeepPBI-KG; E0 confirmed, and the finding can be stated for all 135 pairs at once.
- Paper names a different isolation strain than NCBI → record it; the E2 pairs may need to drop.

## Estimating the unread papers (tier 3)

- Unit: paper (cluster). For each tier-3 paper count how many of its E0 pairs changed level.
- Report the share of tier-3 E0 pairs that upgraded, with a confidence interval over papers (bootstrap over the 30 papers).
- If **no** tier-3 paper upgrades any pair: the per-paper upgrade rate is below about 10% (rule of three: 3/30) with 95% confidence;
  report that bound for the ~509 unread free-PMC papers.
- If one or more papers upgrade pairs: draw 30 more papers (same seed, next draws) before reporting, to tighten the interval.

## Code check (tier 4)

For each of the 20 pairs in `note/code_check_pairs.csv`, open the phage and host NCBI pages (and PhagesDB if listed) and confirm that
`auto_level` follows from what the pages show. Mark `code_reading_correct` yes/no. Any "no" means a bug: stop and report it before using the totals.

## Effort and a minimum track

- Full plan: 59 papers × about 15 min + 20 pairs × 2 min ≈ **16 hours**.
- Minimum track (about 6 hours): tier 1 top 6 papers (289 of the 330 mixed pairs), tier 2 top 5, tier 3 first 15, tier 4 all 20.
  With 15 random papers and no upgrades the bound widens to about 20% (3/15).
- Paywalled papers (2 in tier 1, 1 in tier 2): use the VinUni library or ask the authors; skip them in the minimum track.

## What the final report will say

- Levels after reading for the 641 audited pairs, and the estimated (with interval) effect on the remaining 1,632 paper-linked pairs.
- That the 2,639 pairs without a paper rest on database fields only (code check result).
- For each mixed paper: whether DeepPBI-KG's extra pairs were tested or extrapolated.
