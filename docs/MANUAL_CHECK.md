# Hand verification of phage–host pairs

Worksheets: `note/manual_check_all.xlsx` (all positive pairs, formatted; built by `scripts/export_xlsx.py`) and the 36-pair sample `note/manual_check.csv` (built by `scripts/manual_sheet.py`). One row per positive pair DeepPBI-KG labels "interacts". Rebuilding keeps rows you already filled in.

## For each row

1. Read what is already known: `sources_listing_pair` (which public datasets list this pair), `ncbi_phage_host_field` (host written in the phage's NCBI record), `phagesdb_isolation_host`, `phagesdb_verified_hosts`.
2. Open the links:
   - `open_phage_ncbi`: look at `/host` or `/lab_host`, and the REFERENCE papers.
   - `open_host_ncbi`: note the exact host strain (`/strain`, `/culture_collection`).
   - `open_phagesdb` (Actinobacteriophages only): isolation host, "Host range" / verified hosts.
   - `open_papers`: search the paper for the host strain name and the keywords **wet lab, spot test, plaque assay, in vitro, host range, efficiency of plating**.
3. Fill in the blank columns:
   - `verdict` — one of the codes below.
   - `method_seen` — e.g. "plaque isolation", "spot test", "host-range table", "none".
   - `host_strain_seen` — the strain the source actually used.
   - `evidence_url` and `evidence_quote` — where you saw it (page, table or figure number) and a short quote.
   - `checked_by`, `checked_on`, `notes`.

## Verdict codes

| Code | Use when |
|---|---|
| `E3_hostrange` | A paper or database reports a lab test (spot test, plaque assay, host-range table) of **this phage on this host strain** |
| `E2_isolation_strain` | The phage was isolated or grown on **this strain** (or a proven synonym, e.g. NRRL B-24152 = DSM 44215), but no host-range test is shown |
| `E1_annotation_strain` | A record names this exact strain as host, with no method |
| `E0_annotation_coarse` | Only species/genus, or a **different strain** than the one DeepPBI-KG pairs |
| `U_unresolved` | Nothing found |

Strain synonyms already found are in `data/derived/strain_synonyms.csv` (NCBI Taxonomy type strains): check there before calling two culture-collection numbers different.

## Rows to start with

- 1 — Petra × *G. westfalica* DSM 44215 (anh Minh's example): isolated on NRRL B-24152, which NCBI Taxonomy lists as the same type strain.
- 2 — Minerva × *M. smegmatis* MKD8: isolated on mc²155, a different strain.
- 3–4 — RGL3, RER2: the only dataset phages with PhagesDB verified hosts, both on another species than the paired host.
- 5 — phiCD6356 × one of 12 *C. difficile* strains: NCBI gives only the species.
