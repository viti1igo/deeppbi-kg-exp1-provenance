#!/usr/bin/env python3
"""Apply paper-level audit results (note/paper_audit.xlsx, else note/paper_audit.csv) to the pair evidence levels.

`result_per_paired_host` holds `HOST:code` items; codes:
  +  tested, infects          -> E3_hostrange
  -  tested, does not infect  -> E3_hostrange, flagged TESTED NEGATIVE (contradicts the positive label)
  iso  isolation/propagation host only -> at least E2_isolation_strain
  prophage  prophage in this host's genome -> at least E1_annotation_strain
  nt  not tested / not mentioned -> unchanged
  anything else (check, +?, unsearched, blank) -> unchanged, counted as pending
A pair whose phage cites several audited papers takes the strongest result. Writes
data/derived/pair_levels_after_audit.csv and _summary.json, separately for all results and for rows
confirmed by a person (checked_by not starting with "Claude" or "auto").
"""
from collections import Counter, defaultdict
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ['U_unresolved', 'E0_annotation_coarse', 'E1_annotation_strain', 'E2_isolation_strain', 'E3_hostrange']
FLOOR = {'+': 'E3_hostrange', '-': 'E3_hostrange', 'iso': 'E2_isolation_strain', 'prophage': 'E1_annotation_strain'}


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def parse(field):
    out = {}
    for item in filter(None, (x.strip() for x in field.split(';'))):
        host, _, code = item.rpartition(':')
        if host:
            out[host.split('.')[0]] = code.strip()
    return out


def apply(pairs, papers, links, confirmed_only=False):
    """-> list of (pair, new_level, codes) ; papers: rows of paper_audit.csv."""
    results = defaultdict(list)   # (phage, host) -> [(pmid, code, tier)]
    by_pmid = {p['pmid']: p for p in papers}
    for pair in pairs:
        for pmid in links.get(pair['phage'].split('.')[0], []):
            paper = by_pmid.get(pmid)
            if not paper or (confirmed_only and paper['checked_by'].startswith(('Claude', 'auto'))):
                continue
            code = parse(paper['result_per_paired_host']).get(pair['host'].split('.')[0])
            if code is not None:
                results[pair['phage'], pair['host']].append((pmid, code, paper['tier']))
    out = []
    for pair in pairs:
        level = pair['auto_level']
        codes = results.get((pair['phage'], pair['host']), [])
        for _, code, _ in codes:
            floor = FLOOR.get(code)
            if floor and LEVELS.index(floor) > LEVELS.index(level):
                level = floor
        out.append((pair, level, codes))
    return out


def summarise(applied):
    audited = [(p, lvl, c) for p, lvl, c in applied if c]
    changed = [(p, lvl, c) for p, lvl, c in audited if lvl != p['auto_level']]
    tier3 = [(p, lvl, c) for p, lvl, c in audited if any(t.startswith('3') for _, _, t in c) and p['auto_level'].startswith('E0')]
    return {
        'pairs_audited': len(audited),
        'pairs_changed': len(changed),
        'changes': dict(Counter(f"{p['auto_level'].split('_')[0]}->{lvl.split('_')[0]}" for p, lvl, _ in changed)),
        'tested_negative_pairs': sum(any(code == '-' for _, code, _ in c) for _, _, c in audited),
        'pending_pairs': sum(any(code not in FLOOR and code != 'nt' for _, code, _ in c) for _, _, c in audited),
        'distribution_after': dict(Counter(lvl for _, lvl, _ in applied)),
        'tier3_E0_pairs': len(tier3),
        'tier3_E0_upgraded': sum(lvl != p['auto_level'] for p, lvl, _ in tier3),
        'tier3_papers_with_any_upgrade': len({pm for p, lvl, c in tier3 if lvl != p['auto_level'] for pm, _, t in c if t.startswith('3')})}


def load_papers():
    """Paper rows from note/paper_audit.xlsx (where people edit) when present, else the CSV drafts."""
    spec = importlib.util.spec_from_file_location('export_paper_audit_xlsx', Path(__file__).resolve().parent / 'export_paper_audit_xlsx.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_workbook() or rows(ROOT / 'note/paper_audit.csv')


def main():
    pairs = rows(ROOT / 'data/derived/pair_evidence_levels.csv')
    papers = load_papers()
    links = {r['accession']: [x for x in r['pubmed'].split(';') if x] for r in rows(ROOT / 'data/derived/ncbi_links.csv')}
    applied = apply(pairs, papers, links)
    with (ROOT / 'data/derived/pair_levels_after_audit.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['phage', 'phage_name', 'host', 'host_name', 'auto_level', 'level_after_audit',
                                                    'audit_results'])
        writer.writeheader()
        for p, lvl, codes in applied:
            writer.writerow({'phage': p['phage'], 'phage_name': p['phage_name'], 'host': p['host'], 'host_name': p['host_name'],
                             'auto_level': p['auto_level'], 'level_after_audit': lvl,
                             'audit_results': '; '.join(f'PMID {pm} tier {t[:1]}: {code}' for pm, code, t in codes)})
    tier3_papers = sum(p['tier'].startswith('3') for p in papers)
    summary = {'all_results_including_drafts': summarise(applied),
               'confirmed_by_person_only': summarise(apply(pairs, papers, links, confirmed_only=True)),
               'tier3_papers': tier3_papers,
               'rule_of_three_upper_bound_if_no_tier3_upgrade': round(3 / tier3_papers, 3) if tier3_papers else None}
    (ROOT / 'data/derived/pair_levels_after_audit_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
