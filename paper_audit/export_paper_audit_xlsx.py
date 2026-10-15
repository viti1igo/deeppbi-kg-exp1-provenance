#!/usr/bin/env python3
"""Export note/paper_audit.csv to a formatted workbook note/paper_audit.xlsx (stdlib only).

Sheets: Papers (one row per audited paper; tier and verdict colours, clickable PMC/PubMed links, frozen
header, filters), Summary (live counts), Legend (result codes). Rows already signed by a person in an
existing paper_audit.xlsx (checked_by not "Claude ..."/"auto ...") are kept. Refuses to write while the
workbook is open in Excel. apply_paper_audit.py reads the workbook when it exists.
"""
import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'note/paper_audit.csv'
OUT = ROOT / 'note/paper_audit.xlsx'
FILL = ['result_per_paired_host', 'strains_used_in_paper', 'isolation_host_in_paper', 'host_range_table',
        'checked_by', 'checked_on', 'notes']
# (key, header, width, style); styles from export_xlsx: 2 wrap, 3 link, 5 plain, 7..11 level fills
COLUMNS = [('tier', 'Tier', 11, 5), ('pmid', 'PMID', 10, 5), ('result_per_paired_host', 'Result per paired host (edit)', 46, 5),
           ('checked_by', 'Checked by', 16, 5), ('checked_on', 'Checked on', 11, 5),
           ('pairs', 'Pairs', 7, 5), ('E2', 'E2', 5, 5), ('E1', 'E1', 5, 5), ('E0', 'E0', 6, 5), ('U', 'U', 4, 5),
           ('open_pmc', 'PMC', 7, 3), ('open_pubmed', 'PubMed', 9, 3),
           ('title', 'Title', 48, 5), ('journal', 'Journal', 20, 5), ('year', 'Year', 6, 5),
           ('paired_hosts_to_look_for', 'Paired hosts to look for (pairs)', 48, 5),
           ('isolation_host_in_paper', 'Isolation host in paper', 24, 5), ('host_range_table', 'Host-range table', 18, 5),
           ('strains_used_in_paper', 'Strains used in paper', 24, 5), ('notes', 'Notes / evidence', 70, 2)]
TIER_STYLE = {'1': 10, '2': 9, '3': 11}          # mixed = orange, coverage = yellow, random = grey
DECIDE = ('+?', 'check', 'unsearched')


def load(name):
    path = ROOT / f'scripts/{name}.py'   # shared helpers (export_xlsx, audit) live in the repo's scripts/
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ex = load('export_xlsx')


def read_workbook(path=OUT):
    """Rows of the Papers sheet as dicts keyed like the CSV (empty list if the workbook is absent)."""
    if not path.exists():
        return []
    audit = load('audit')
    rows = list(audit.id_rows(path, 'Papers'))
    if not rows:
        return []
    by_header = {h: key for key, h, _, _ in COLUMNS}
    letter = {by_header[v]: k for k, v in rows[0].items() if k != '_excel_row' and v in by_header}
    return [{key: r.get(col, '') for key, col in letter.items()} for r in rows[1:]]


def result_style(text):
    codes = [item.rpartition(':')[2].strip() for item in text.split(';') if item.strip()]
    if any(c in ('+', '-') for c in codes):
        return 8          # green: lab test found
    if any(c in DECIDE for c in codes):
        return 9          # yellow: needs a person's decision
    return 5


def main():
    lock = OUT.with_name('~$' + OUT.name)
    if lock.exists():
        raise SystemExit(f'{OUT.name} is open in Excel (lock file {lock.name}); close it and run again.')
    with SRC.open(newline='') as stream:
        records = list(csv.DictReader(stream))
    kept = {r['pmid']: r for r in read_workbook()
            if r.get('checked_by') and not r['checked_by'].startswith(('Claude', 'auto'))}
    for r in records:
        if r['pmid'] in kept:
            for f in FILL:
                r[f] = kept[r['pmid']].get(f, r[f])

    rows = [[(h, 1) for _, h, _, _ in COLUMNS]]
    for r in records:
        row = []
        for key, _, _, style in COLUMNS:
            value = r.get(key, '')
            if key == 'tier':
                style = TIER_STYLE.get(value[:1], style)
            elif key == 'result_per_paired_host':
                style = result_style(value)
            elif key in ('pairs', 'E2', 'E1', 'E0', 'U', 'pmid') and value.isdigit():
                value = int(value)
            elif key in ('open_pmc', 'open_pubmed') and value:
                label = 'PMC' if key == 'open_pmc' else 'PubMed'
                value = (f'=HYPERLINK("{value}","{label}")', label)
            row.append((value, style))
        rows.append(row)
    n, last = len(records), ex.col_letter(len(COLUMNS) - 1)
    views = '<pane xSplit="3" ySplit="1" topLeftCell="D2" activePane="bottomRight" state="frozen"/>'
    papers = ex.sheet(rows, [w for _, _, w, _ in COLUMNS], f'<autoFilter ref="A1:{last}{n + 1}"/>', views)

    col = {key: ex.col_letter(i) for i, (key, _, _, _) in enumerate(COLUMNS)}
    rng = lambda key: f'Papers!{col[key]}2:{col[key]}{n + 1}'
    summary_rows = [[('', 1), ('Papers', 1), ('Pairs covered', 1), ('Signed by a person', 1)]]
    for tier, label in (('1', '1 mixed'), ('2', '2 coverage'), ('3', '3 random')):
        summary_rows.append([(label, TIER_STYLE[tier]), (f'=COUNTIF({rng("tier")},"{label}")', 5),
                             (f'=SUMIF({rng("tier")},"{label}",{rng("pairs")})', 5),
                             (f'=COUNTIFS({rng("tier")},"{label}",{rng("checked_by")},"<>Claude*",{rng("checked_by")},"<>")', 5)])
    summary_rows += [[('Total', 6), ('=SUM(B2:B4)', 6), ('=SUM(C2:C4)', 6), ('=SUM(D2:D4)', 6)], [('', 0)] * 4,
                     [('Rows with a lab test (+ or -)', 6), (f'=COUNTIF({rng("result_per_paired_host")},"*:+*")'
                                                               f'+COUNTIF({rng("result_per_paired_host")},"*:-*")', 5), ('', 0), ('', 0)],
                     [('Rows needing a decision', 6), (f'=COUNTIF({rng("result_per_paired_host")},"*:check*")'
                                                       f'+COUNTIF({rng("result_per_paired_host")},"*+?*")'
                                                       f'+COUNTIF({rng("result_per_paired_host")},"*unsearched*")', 5), ('', 0),
                      ('may double-count a row with several codes', 2)]]
    summary = ex.sheet(summary_rows, [30, 14, 16, 22])

    legend_rows = [[('Code', 1), ('Meaning', 1), ('Pair level after apply_paper_audit.py', 1)],
                   [('HOST:+', 7), ('Paper tests this phage on this host strain and it infects (spot/plaque/host-range table)', 2), ('E3_hostrange', 5)],
                   [('HOST:-', 7), ('Tested, does NOT infect: contradicts the positive label; say so in Notes', 2), ('E3_hostrange + TESTED NEGATIVE', 5)],
                   [('HOST:iso', 8), ('Phage isolated or propagated on this strain; no host-range test', 2), ('at least E2', 5)],
                   [('HOST:prophage', 9), ("Phage is a prophage in this strain's genome", 2), ('at least E1', 5)],
                   [('HOST:nt', 10), ('Strain not tested / not mentioned in the paper', 2), ('unchanged', 5)],
                   [('check, +?, unsearched', 9), ('Needs a person: confirm the reading, a strain synonym, or search a short strain code by hand', 2),
                    ('unchanged until decided', 5)],
                   [('', 0)] * 3,
                   [('How to confirm', 6), ('Open PMC/PubMed, find the paired strain code (and synonyms in data/derived/strain_synonyms.csv), '
                                           'edit the result codes, put your name in Checked by, save. Then run '
                                           'python3 scripts/apply_paper_audit.py', 2), ('', 0)],
                   [('Colours', 6), ('Tier: orange = mixed, yellow = coverage, grey = random. Result: green = lab test found, '
                                     'yellow = needs a decision (colours are set at export).', 2), ('', 0)]]
    legend = ex.sheet(legend_rows, [22, 80, 34])
    ex.write_workbook(OUT, [('Papers', papers), ('Summary', summary), ('Legend', legend)], f"'Papers'!$A$1:${last}${n + 1}")
    print(f'{n} papers -> {OUT} ({len(kept)} signed rows kept from the previous workbook)')


if __name__ == '__main__':
    main()
