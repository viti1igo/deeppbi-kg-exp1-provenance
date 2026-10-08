#!/usr/bin/env python3
"""Step 4 (automatic draft): evidence level for every Experiment 1 positive pair, from existing data only.

Claims about a phage's host, strongest first (level given when the claim names the paired host's
exact strain or a known synonym of it, from data/derived/strain_synonyms.csv):
  E3_hostrange         PhagesDB verified_hosts
  E2_isolation_strain  PhagesDB isolation_host, NCBI /lab_host, phage BioSample lab_host
  E1_annotation_strain NCBI /host, phage BioSample host
A pair whose claims name a host but not that strain is E0_annotation_coarse; a pair with no host
claim at all (or missing records) is U_unresolved. No papers are read here, so E3 from the
literature can only come from hand checking. Writes data/derived/pair_evidence_levels.csv,
note/manual_check_all.csv (full worksheet, hand-checked rows from note/manual_check.csv kept) and
data/derived/pair_evidence_levels_summary.json.
"""
from collections import Counter, defaultdict
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT  # stage-1 audit outputs and caches live in this repo too
DERIVED = ROOT / 'data/derived'
LEVELS = ['U_unresolved', 'E0_annotation_coarse', 'E1_annotation_strain', 'E2_isolation_strain', 'E3_hostrange']
RELATION_ORDER = ['same_strain', 'same_strain_prefix', 'same_species_other_strain', 'same_species', 'same_genus', 'different_genus']
EXTERNAL = ('external_PHI_final.xlsx', 'external_key_gene_PHI_new.xlsx')
NON_PROKARYOTE = {'Craniata', 'Arthropoda', 'Chlorophyta', 'Haptophyta', 'Discosea'}  # phyla in host_phylum_info.csv


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ncbi = load(OLD / 'scripts/ncbi_trace.py', 'ncbi_trace')
syn = load(ROOT / 'scripts/strain_synonyms.py', 'strain_synonyms')
manual = load(ROOT / 'scripts/manual_sheet.py', 'manual_sheet')


def base(accession):
    return accession.split('.')[0]


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def relation(claim, host_organism, host, synonyms):
    """How a host string relates to the paired host: same_strain ... different_genus.

    Species/genus from ncbi_trace.compare (handles renamed genera); strain only by exact match of the
    normalized strain code against the host's designations and synonyms. compare's own strain test
    uses substrings and gives false matches ('Vi' in 'Levine 1', '1' in 'FDAARGOS_14').
    """
    r = ncbi.compare(claim, {'organism': host_organism, 'quals': {}})
    if r not in ('same_species', 'same_species_other_strain'):
        return r
    if syn.strain_matches(claim, host, synonyms, ncbi.split_name):
        return 'same_strain'
    code = syn.norm(''.join(ncbi.split_name(claim)[2]))
    if any(prefix_match(code, d) for d in synonyms.get(host, ())):
        return 'same_strain_prefix'
    return r


def prefix_match(a, b):
    """'JI1326' ~ '1326': equal after dropping a letters-only collection prefix; codes >=3 chars with a digit.

    Flagged for hand checking: the prefix could in principle name a different collection.
    """
    short, long_ = sorted((a, b), key=len)
    return (len(short) >= 3 and any(c.isdigit() for c in short) and short != long_
            and long_.endswith(short) and long_[:-len(short)].isalpha())


def grade(claims, host_organism, host, synonyms):
    """claims: [(level_if_same_strain, source, text)] -> (level, basis, best_relation)."""
    best, basis, rels = 'U_unresolved', '', []
    for level, source, text in claims:
        if not text:
            continue
        rel = relation(text, host_organism, host, synonyms)
        rels.append(rel)
        if rel in ('same_strain', 'same_strain_prefix') and LEVELS.index(level) > LEVELS.index(best):
            best, basis = level, f'{source}: {text}' + (' [strain code matched after a collection prefix: check]'
                                                          if rel == 'same_strain_prefix' else '')
    if best == 'U_unresolved' and rels:
        best = 'E0_annotation_coarse'
        rel = min(rels, key=RELATION_ORDER.index)
        basis = {'same_species_other_strain': 'host named at another strain', 'same_species': 'host named at species level only',
                 'same_genus': 'host named at genus level only', 'different_genus': 'host named in a different genus'}.get(rel, rel)
    return best, basis, (min(rels, key=RELATION_ORDER.index) if rels else 'none')


def main():
    pairs = [r for r in rows(DERIVED / 'source_membership_pairs.csv') if '1' in r['label'].split('/')]
    trace = {(r['phage'], r['host']): r for r in rows(OLD / 'data/derived/ncbi_pair_trace.csv')}
    links = {r['accession']: r for r in rows(DERIVED / 'ncbi_links.csv')}
    entities = rows(DERIVED / 'entities.csv')
    names = {(r['kind'], r['accession']): r['name'] for r in entities}
    phylum = {r['accession']: r['phylum'] for r in entities if r['kind'] == 'host'}
    phagesdb = {}
    for r in rows(DERIVED / 'phagesdb_phages.csv'):
        for a in (r['genbank_accession'], r['refseq_accession']):
            if a:
                phagesdb[a] = r
    synonyms = defaultdict(set)
    for r in rows(DERIVED / 'strain_synonyms.csv'):
        if r['normalized']:
            synonyms[r['host']].add(r['normalized'])
    split = defaultdict(set)
    for r in rows(OLD / 'data/derived/pair_evidence.csv'):
        if r['experiment'] == '1' and r['label'] == '1':
            split[r['phage'], r['host']].add('external' if r['table'].split('/')[-1].split('#')[0] in EXTERNAL else 'train_test')

    out = []
    for m in pairs:
        p, h = m['phage'], m['host']
        t, pdb, lk = trace.get((p, h), {}), phagesdb.get(base(p), {}), links.get(base(p), {})
        ncbi_host = t.get('phage_host_value', '') if t.get('phage_host_field') == 'host' else ''
        claims = [('E3_hostrange', 'PhagesDB verified host', v) for v in pdb.get('verified_hosts', '').split(';')]
        claims += [('E2_isolation_strain', 'PhagesDB isolation host', pdb.get('isolation_host', '')),
                   ('E2_isolation_strain', 'NCBI /lab_host', t.get('phage_lab_host', '')),
                   ('E2_isolation_strain', 'BioSample lab_host', lk.get('biosample_lab_host', '')),
                   ('E1_annotation_strain', 'NCBI /host', ncbi_host),
                   ('E1_annotation_strain', 'BioSample host', lk.get('biosample_host', ''))]
        level, basis, rel = grade(claims, t.get('host_organism', ''), base(h), synonyms)
        flags = []
        if pdb.get('verified_hosts') and level != 'E3_hostrange':
            flags.append('PhagesDB verified host is not the paired strain')
        if rel == 'different_genus':
            flags.append('host claims in a different genus: possible label error')
        if phylum.get(h) in NON_PROKARYOTE:
            flags.append(f'host is not a bacterium or archaeon ({phylum[h]})')
        if not t or t.get('phage_record') == 'missing' or t.get('host_record') == 'missing':
            flags.append('NCBI record missing')
        out.append({
            'phage': p, 'host': h, 'phage_name': names.get(('phage', p), ''), 'host_name': names.get(('host', h), ''),
            'split': '+'.join(sorted(split.get((p, h), {'unknown'}))), 'sources_listing_pair': manual.group(m),
            'auto_level': level, 'auto_basis': basis, 'best_relation': rel, 'flags': '; '.join(flags),
            'ncbi_host': ncbi_host, 'ncbi_lab_host': t.get('phage_lab_host', ''), 'host_strain': t.get('host_strain', ''),
            'phagesdb_isolation_host': pdb.get('isolation_host', ''), 'phagesdb_verified_hosts': pdb.get('verified_hosts', ''),
            'biosample_host': lk.get('biosample_host', ''), 'biosample_lab_host': lk.get('biosample_lab_host', ''),
            'open_phage_ncbi': f'https://www.ncbi.nlm.nih.gov/nuccore/{p}', 'open_host_ncbi': f'https://www.ncbi.nlm.nih.gov/nuccore/{h}',
            'open_phagesdb': pdb.get('url', ''),
            'open_papers': ' '.join([f'https://pubmed.ncbi.nlm.nih.gov/{x}/' for x in lk.get('pubmed', '').split(';') if x]
                                    + [f'https://pmc.ncbi.nlm.nih.gov/articles/{x}/' for x in lk.get('pmc', '').split(';') if x])})
    with (DERIVED / 'pair_evidence_levels.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)

    # Full worksheet: auto level as the draft verdict; rows already in the 36-row sheet keep their hand/draft values.
    hand = {(r['phage'], r['host']): r for r in rows(ROOT / 'note/manual_check.csv')}
    sheet = []
    for i, r in enumerate(out, 1):
        row = {'id': i, **{k: r[k] for k in ('phage', 'phage_name', 'host', 'host_name', 'split', 'sources_listing_pair',
                                              'auto_level', 'auto_basis', 'flags', 'ncbi_host', 'ncbi_lab_host',
                                              'phagesdb_isolation_host', 'phagesdb_verified_hosts', 'open_phage_ncbi',
                                              'open_host_ncbi', 'open_phagesdb', 'open_papers')},
               'checked_by': 'auto (to confirm)', 'checked_on': '', 'verdict': r['auto_level'],
               **{f: '' for f in ('method_seen', 'host_strain_seen', 'evidence_url', 'evidence_quote', 'notes')}}
        h = hand.get((r['phage'], r['host']))
        if h and h.get('verdict'):
            for f in manual.FILL:
                row[f] = h[f]
            row['notes'] = f"[sample row {h['id']}] " + h['notes']
        sheet.append(row)
    with (ROOT / 'note/manual_check_all.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sheet[0]))
        writer.writeheader()
        writer.writerows(sheet)

    def dist(items):
        c = Counter(x['auto_level'] for x in items)
        return {lvl: c[lvl] for lvl in LEVELS}
    summary = {
        'positive_pairs': len(out), 'overall': dist(out),
        'by_split': {s: dist([r for r in out if r['split'] == s]) for s in sorted({r['split'] for r in out})},
        'by_source_group': {g: dist([r for r in out if r['sources_listing_pair'] == g])
                            for g in sorted({r['sources_listing_pair'] for r in out})},
        'E0_basis': dict(Counter(r['auto_basis'] for r in out if r['auto_level'] == 'E0_annotation_coarse').most_common()),
        'level_basis_source': dict(Counter(r['auto_basis'].split(':')[0] for r in out
                                           if r['auto_level'] in LEVELS[2:]).most_common()),
        'flags': dict(Counter(f for r in out for f in r['flags'].split('; ') if f).most_common()),
        'agreement_with_hand_drafts': {
            'rows': sum((r['phage'], r['host']) in hand and bool(hand[r['phage'], r['host']]['verdict']) for r in out),
            'same': sum((r['phage'], r['host']) in hand and hand[r['phage'], r['host']]['verdict'] == r['auto_level'] for r in out),
            'differ': [(r['phage'], r['host'], hand[r['phage'], r['host']]['verdict'], r['auto_level']) for r in out
                       if (r['phage'], r['host']) in hand and hand[r['phage'], r['host']]['verdict']
                       and hand[r['phage'], r['host']]['verdict'] != r['auto_level']]}}
    (DERIVED / 'pair_evidence_levels_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
