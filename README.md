# DeepPBI-KG Experiment 1 — provenance and wet-lab evidence audit

[DeepPBI-KG](https://academic.oup.com/bib/article/25/6/bbae484/7791000) (Wei *et al.*, *Briefings in Bioinformatics* 2024, bbae484)
trains phage–bacteria interaction models on pairs pooled from five public sources: PredPHI, PhageHosts, NCBI, MVP and PHISDetector.
This repository traces those **Experiment 1** pairs back to their sources and asks, for every positive pair:

1. Which source does it come from?
2. Where did that source get it?
3. Is there a real lab result (spot test, plaque assay, host-range test) for **this phage on this exact host strain**?

Experiment 2 (the authors' in vitro *K. pneumoniae* data on NGDC) is out of scope here.

## Main findings (4,912 unique positive pairs; 4,875 in the paper's counted sets)

| Evidence level | Meaning | Pairs | % |
|---|---|---:|---:|
| `E3_hostrange` | Lab host-range test of this phage on the exact paired strain | 0 | 0.0 |
| `E2_isolation_strain` | Phage isolated / propagated on the exact strain (or a proven synonym) | 303 | 6.2 |
| `E1_annotation_strain` | A record names the exact strain, no method (incl. prophage in its genome) | 47 | 1.0 |
| `E0_annotation_coarse` | Species/genus only, or a **different** strain | 4,479 | 91.2 |
| `U_unresolved` | No host information | 83 | 1.7 |

- None of the five source papers built its pairs from a lab experiment: positives come from database host fields (GenBank/RefSeq/PhagesDB) or predictions (MVP); all negatives are artificially sampled.
- 2,571 positives pair a phage with a different strain than its own record names. The largest case: all **1,337** pairs with *Mycolicibacterium smegmatis* **MKD8** use phages isolated on strain **mc²155** (36.7% of the 3,647 training/test positives).
- Levels are computed from database fields only; papers are not read automatically, so `E3 = 0` is a lower bound. Hand checking is supported by an Excel worksheet (below).
- The [paper-level audit](#paper-level-audit-paper_audit) (59 papers, 641 pairs) found that papers name the strain they actually used, almost never the
  other strains DeepPBI-KG pairs with. Draft result: only **4** positives reach `E3`; 0 of 76 `E0` pairs changed in 30 random papers.

## Requirements

- Python 3.11+ standard library only (no packages). Downloaded code and models are never executed.
- About 4 GB of disk and network access to GitHub, NCBI E-utilities, PhagesDB and the PHISDetector site.

## Run

```bash
python3 scripts/download.py --all --jobs 4   # source repos, tables, papers (manifest.json, with receipts)
python3 scripts/audit.py                     # parse the authors' pair tables -> data/derived/pair_evidence.csv
python3 scripts/ncbi_trace.py                # NCBI GenBank headers of every positive pair (cached)
python3 scripts/keyword_scan.py              # wet-lab keywords in the five source papers
python3 scripts/inventory.py                 # step 1: one row per host and phage
python3 scripts/source_membership.py         # step 2: which source lists each pair
python3 scripts/phagesdb.py                  # step 3: PhagesDB dump (isolation hosts, host range)
python3 scripts/ncbi_links.py                # step 3b: BioSample / BioProject / PubMed / PMC links
python3 scripts/strain_synonyms.py           # step 3: strain synonyms (run after ncbi_links)
python3 scripts/manual_sheet.py              # 36-pair sample worksheet -> note/manual_check.csv
python3 scripts/evidence_levels.py           # step 4: evidence level for every positive pair
python3 scripts/export_xlsx.py               # formatted worksheet -> note/manual_check_all.xlsx
python3 -m unittest discover -s tests
```

Every network response is cached under `data/raw/`, so reruns make no new requests and give identical outputs.
NCBI is queried at ≤3 requests/s; PhagesDB needs a browser User-Agent (set in the script).

## Outputs (`data/derived/`, not in Git)

| File | Content |
|---|---|
| `pair_evidence.csv` | Every row of every author pair table, with sequence identifiers |
| `ncbi_pair_trace.csv` | NCBI `/host`, `/lab_host` and host strain per positive pair |
| `keyword_scan.csv` | Wet-lab keyword hits in the five source papers, with context |
| `entities.csv` | One row per host and phage (split, positive/negative counts, phylum) |
| `source_membership_{entities,pairs}.csv` | Presence in PredPHI, PhageHosts, PHISDetector, NCBI |
| `phagesdb_phages.csv` | PhagesDB isolation hosts and verified hosts |
| `strain_synonyms.csv` | Culture-collection synonyms per host (NCBI Taxonomy type material, host record, BioSample) with source URLs |
| `ncbi_links.csv` | BioSample attributes, BioProject, PubMed and PMC ids per accession |
| `pair_evidence_levels.csv` | Evidence level, basis and flags for every positive pair (+ `_summary.json` with distributions) |

## Checking pairs by hand

`note/manual_check_all.xlsx` has one row per positive pair with the automatic level as a draft verdict, a verdict drop-down
(coloured E3 → U), clickable links to NCBI, PhagesDB and papers, a live **Summary** sheet and a **Legend**.
Put your name in **Checked by** for rows you have checked: re-running `export_xlsx.py` keeps those rows.
Close the workbook in Excel before re-running. Guide and keywords: [docs/MANUAL_CHECK.md](docs/MANUAL_CHECK.md).

## Paper-level audit (`paper_audit/`)

2,273 positives have a phage that cites a paper, but they cite only 980 papers, so one paper settles many pairs. The audit reads
**papers, not pairs**, and lets code apply each paper's answer to all of its pairs. Method and decision rules:
[paper_audit/AUDIT_PLAN.md](paper_audit/AUDIT_PLAN.md).

| Tier | Papers | Pairs | Purpose |
|---|---:|---:|---|
| 1 mixed | 19 | 330 | Papers whose pairs got both E2/E1 and E0: did the paper also test the other strains? |
| 2 coverage | 10 | 235 | Largest remaining papers |
| 3 random | 30 | 76 | Random free-PMC papers with E0 pairs (seed 20261011): estimate for unread papers |
| 4 code check | — | 20 | Pairs with no paper: confirm the database reading |

Each paper is searched for the **strain codes (and synonyms)** of the hosts paired with its phages; each paired host gets a code:
`+` / `-` (tested, infects / does not → E3), `iso` (isolation or propagation host → E2), `prophage` (→ E1), `nt` (not tested → unchanged),
or `check` / `+?` / `unsearched` (pending a person).

```bash
python3 paper_audit/paper_audit.py               # papers per pair, tiers and samples -> note/paper_audit.csv
python3 paper_audit/fetch_papers.py              # PMC full-text XML for the audit papers (cached, with receipts)
python3 paper_audit/scan_papers.py               # strain-code search in each paper -> data/derived/paper_scan.csv
python3 paper_audit/export_paper_audit_xlsx.py   # formatted workbook -> note/paper_audit.xlsx (keeps signed rows)
python3 paper_audit/apply_paper_audit.py         # apply paper results to pair levels (reads the workbook when present)
python3 -m unittest discover -s paper_audit/tests
```

Papers whose publisher blocks API download were searched in a browser on the PMC page (no full text stored); paywalled papers were
read through a university library proxy. Their findings are recorded in `paper_audit/results/paper_scan_web.json`.

### Results (drafts, 2026-10-11; not yet confirmed by hand)

- All 59 audit papers searched: 32 PMC full-text XML, 24 PMC web pages, 3 paywalled (library); plus 2 paywalled papers from the hand-check sample.
- **Mixed papers:** the E2/E1 host is the strain the paper used (isolation host or prophage host); the E0 hosts are not mentioned
  (96 paired-host entries `nt`). Example: PMID 22282335 isolates all 138 phages on *M. smegmatis* mc²155 and never mentions MKD8.
- **11 pairs change level:** E0 → E3 1 (phiTMA × *T. thermophilus* HB8, plaques, PMID 22164349); E1 → E3 3 (phiYS40 × HB8; MP22 × *P. aeruginosa*
  PA14, PMID 17768233; RDJLΦ1 × *R. denitrificans* OCh114, susceptibility table, PMID 19139231); E1 → E2 7.
- **Random tier:** 0 of 76 E0 pairs upgraded in 30 papers → per-paper upgrade rate below 10% (95%, rule of three).
- No tested negatives found. The 12 *C. difficile* hosts paired with phiCD6356 appear in its paper only as BLAST hits of phage genes.
- Pending: RDJLΦ1 × NZ_CP027408 (is FDAARGOS_309 = ATCC 33942 = OCh114?), DSS3Φ2 × DSS-3, 14 hosts with strain codes too short to search
  (*Cellulophaga* "18": host range is in Holmfeldt et al. 2007, not yet read).

| File (`paper_audit/results/`) | Content |
|---|---|
| `paper_audit.csv` | One row per audited paper: tier, pairs, links, `result_per_paired_host`, evidence notes (drafts) |
| `papers.csv` | All 980 cited papers with pair counts per evidence level |
| `paper_scan.csv` | Strain-code mentions per (paper, paired host) in PMC full text (excerpt column removed) |
| `paper_scan_web.json` | Findings for papers read in a browser or through the library |
| `paper_fetch.csv` | How each audit paper was obtained (full text / web only / paywalled) |
| `pair_levels_after_audit.csv`, `_summary.json` | Pair levels before and after applying the paper results |
| `code_check_pairs.csv` | The 20 no-paper pairs for the code check (not done yet) |

## Evidence rules

- A pair counts as `E2`/`E3` only when a source names the **same phage and the same host strain** (or a synonym with a URL) and a lab method.
- Strain codes are compared exactly after normalisation (`NRRL:B:24152` = `NRRL B-24152`); a letters-only collection prefix
  (`JI 1326` = `1326`) is accepted but flagged for checking. Renamed genera are handled (*Mycobacterium* → *Mycolicibacterium*).
- Database annotations, sampled negatives and keyword matches are never promoted to wet-lab evidence.

## Known limitations

- Per-pair source is not published by the authors; membership is reconstructed (97.7% of positives found in ≥1 source at species level).
- MVP's website is unavailable (HTTP 520) and the full PHISDetector database (102 GB) is not downloaded; their benchmark pair lists are used.
- Strain synonyms are only known for type strains (86 of 549 hosts); other synonyms may be missed.
- The paper's training/test split (1,211 / 2,436) matches the whole-genome model outputs; the published key-gene tables hold 1,092 / 2,385.
  The external set exists in three versions (1,230 / 1,267 / 1,570 positives); only the first two have pair identifiers.

## Layout

```
scripts/   download, audit and evidence scripts (stdlib)
tests/     unit tests (python3 -m unittest discover -s tests)
paper_audit/   paper-level audit: scripts, tests, AUDIT_PLAN.md and results/ (drafts)
docs/      PAIR_SOURCE_CHECKS.csv (curated input for audit.py), MANUAL_CHECK.md (hand-check guide)
manifest.json   every download with URL, pinned commit where applicable, and unavailable endpoints
data/, logs/, note/   created by the scripts; excluded from Git
```

## Citation

If you use this audit, cite the original work: Wei T. *et al.* DeepPBI-KG: a deep learning method for the prediction of
phage-bacteria interactions based on key genes. *Briefings in Bioinformatics* 25(6), bbae484 (2024).
