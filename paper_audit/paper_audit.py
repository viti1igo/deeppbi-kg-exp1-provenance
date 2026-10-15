#!/usr/bin/env python3
"""Paper-level audit list: one row per paper cited by a phage in a positive pair (existing data only).

Reading one paper settles every pair whose phage cites it, so the human audits papers, not pairs.
Tiers (see note/AUDIT_PLAN.md):
  1 mixed      papers whose pairs got both E2/E1 and E0 (same paper, matching and non-matching strains)
  2 coverage   the 10 largest remaining papers by number of pairs
  3 random     30 papers drawn at random (fixed seed) from the remaining free-PMC papers with E0 pairs,
               used to estimate how many E0 pairs a paper would upgrade (cluster sample)
Pairs whose phage cites no paper cannot be changed by reading; 20 of them are drawn for a code check.
Writes data/derived/papers.csv (all papers) and note/paper_audit.csv (tiers 1-3, with blank columns to fill)
and note/code_check_pairs.csv (tier 4).
"""
from collections import Counter, defaultdict
import csv
import glob
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / 'data/derived'
SEED = 20261011
TIER2, TIER3, TIER4 = 10, 30, 20
FILL = ['strains_used_in_paper', 'isolation_host_in_paper', 'host_range_table', 'result_per_paired_host',
        'checked_by', 'checked_on', 'notes']


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def pubmed_meta():
    meta, pmc = {}, {}
    for path in glob.glob(str(ROOT / 'data/raw/NCBI/pubmed/batch_*')):
        result = json.loads(Path(path).read_text()).get('result', {})
        for uid in result.get('uids', []):
            meta[uid] = result[uid]
    for path in glob.glob(str(ROOT / 'data/raw/NCBI/pmc/batch_*')):
        for r in json.loads(Path(path).read_text()).get('records', []):
            if r.get('pmcid'):
                pmc[str(r['pmid'])] = r['pmcid']
    return meta, pmc


def build():
    pairs = rows(DERIVED / 'pair_evidence_levels.csv')
    links = {r['accession']: r for r in rows(DERIVED / 'ncbi_links.csv')}
    meta, pmc = pubmed_meta()
    by_paper, no_paper = defaultdict(list), []
    for p in pairs:
        ids = [x for x in links.get(p['phage'].split('.')[0], {}).get('pubmed', '').split(';') if x]
        for i in ids:
            by_paper[i].append(p)
        if not ids:
            no_paper.append(p)
    papers = []
    for pmid, ps in by_paper.items():
        lv = Counter(p['auto_level'].split('_')[0] for p in ps)
        hosts = Counter(f"{p['host']} {p['host_name'][:50]}" for p in ps)
        m = meta.get(pmid, {})
        papers.append({
            'pmid': pmid, 'pmc': pmc.get(pmid, ''), 'year': m.get('pubdate', '')[:4], 'journal': m.get('source', ''),
            'title': m.get('title', ''), 'pairs': len(ps), 'phages': len({p['phage'] for p in ps}),
            'E2': lv['E2'], 'E1': lv['E1'], 'E0': lv['E0'], 'U': lv['U'],
            'mixed': 'yes' if (lv['E2'] or lv['E1']) and lv['E0'] else 'no',
            'paired_hosts_to_look_for': ' | '.join(f'{h} ({n})' for h, n in hosts.most_common()),
            'open_pubmed': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
            'open_pmc': f'https://pmc.ncbi.nlm.nih.gov/articles/{pmc[pmid]}/' if pmid in pmc else ''})
    papers.sort(key=lambda r: (-r['pairs'], r['pmid']))
    return pairs, papers, no_paper


def select(papers, no_paper):
    rng = random.Random(SEED)
    tier = {}
    for r in papers:
        if r['mixed'] == 'yes':
            tier[r['pmid']] = '1 mixed'
    rest = [r for r in papers if r['pmid'] not in tier]
    for r in rest[:TIER2]:
        tier[r['pmid']] = '2 coverage'
    pool = sorted((r for r in papers if r['pmid'] not in tier and r['pmc'] and r['E0']), key=lambda r: r['pmid'])
    for r in rng.sample(pool, min(TIER3, len(pool))):
        tier[r['pmid']] = '3 random'
    code_check = rng.sample(sorted(no_paper, key=lambda p: (p['phage'], p['host'])), min(TIER4, len(no_paper)))
    return tier, pool, code_check


def write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main():
    pairs, papers, no_paper = build()
    write(DERIVED / 'papers.csv', papers)
    tier, pool, code_check = select(papers, no_paper)
    sheet = [{'tier': tier[r['pmid']], **r, **{f: '' for f in FILL}} for r in papers if r['pmid'] in tier]
    sheet.sort(key=lambda r: (r['tier'], -r['pairs']))
    old = {}
    if (ROOT / 'note/paper_audit.csv').exists():   # keep anything already filled in
        old = {r['pmid']: r for r in rows(ROOT / 'note/paper_audit.csv')}
    for r in sheet:
        for f in FILL:
            r[f] = old.get(r['pmid'], {}).get(f, '') or r[f]
    write(ROOT / 'note/paper_audit.csv', sheet)
    write(ROOT / 'note/code_check_pairs.csv', [
        {k: p[k] for k in ('phage', 'phage_name', 'host', 'host_name', 'auto_level', 'auto_basis', 'ncbi_host',
                           'ncbi_lab_host', 'phagesdb_isolation_host', 'open_phage_ncbi', 'open_host_ncbi', 'open_phagesdb')}
        | {'code_reading_correct': '', 'checked_by': '', 'notes': ''} for p in code_check])
    linked = defaultdict(set)
    links = {r['accession']: r for r in rows(DERIVED / 'ncbi_links.csv')}
    for p in pairs:
        for i in links.get(p['phage'].split('.')[0], {}).get('pubmed', '').split(';'):
            if i:
                linked[i].add((p['phage'], p['host']))
    summary = {
        'positive_pairs': len(pairs), 'pairs_with_paper': len(pairs) - len(no_paper), 'pairs_without_paper': len(no_paper),
        'papers': len(papers), 'papers_free_pmc': sum(bool(r['pmc']) for r in papers),
        'mixed_papers': sum(r['mixed'] == 'yes' for r in papers),
        'tier_papers': dict(Counter(tier.values())),
        'tier_pairs_covered': {t: len(set().union(*(linked[p] for p, tt in tier.items() if tt == t))) for t in set(tier.values())},
        'all_tiers_pairs_covered': len(set().union(*(linked[p] for p in tier))),
        'tier3_sampling_frame_papers': len(pool),
        'code_check_pairs': len(code_check), 'seed': SEED}
    (DERIVED / 'paper_audit_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
