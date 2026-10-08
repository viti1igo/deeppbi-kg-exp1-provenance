#!/usr/bin/env python3
"""Build the hand-verification worksheet note/manual_check.csv from existing tables (no downloads).

One row per selected positive pair: what each source claims, the links to open, and blank columns
to fill by hand. Selection: the named examples first, then a fixed-seed sample per source group so
every kind of pair is represented. Rerunning keeps rows already filled in.
"""
import csv
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT  # stage-1 audit outputs and caches live in this repo too
SHEET = ROOT / 'note/manual_check.csv'
EXAMPLES = [('MH153808', 'NZ_FNLM01000034'),   # Petra x G. westfalica (anh Minh's example)
            ('NC_026584', 'CP027541'),         # Minerva x M. smegmatis MKD8
            ('NC_016650', None), ('NC_016653', None),   # PhagesDB verified-host phages
            ('NC_015262', None)]               # phiCD6356 x 12 C. difficile strains
PER_GROUP = 5
FILL = ['checked_by', 'checked_on', 'verdict', 'method_seen', 'host_strain_seen', 'evidence_url', 'evidence_quote', 'notes']


def table(path, key):
    with path.open(newline='') as stream:
        return {key(r): r for r in csv.DictReader(stream)}


def base(accession):
    return accession.split('.')[0]


def group(m):
    names = [s for s, hit in (('PredPHI', m['predphi_pair'] != 'absent'),
                              ('PhageHosts', m['phagehosts_same_species'] == 'yes'),
                              ('PHISDetector', m['phisdetector_same_species'] == 'yes')) if hit]
    return '+'.join(names) or 'none'


def main():
    pairs = [r for r in csv.DictReader((ROOT / 'data/derived/source_membership_pairs.csv').open(newline=''))
             if '1' in r['label'].split('/')]
    names = table(ROOT / 'data/derived/entities.csv', lambda r: (r['kind'], r['accession']))
    trace = table(OLD / 'data/derived/ncbi_pair_trace.csv', lambda r: (r['phage'], r['host']))
    links = table(ROOT / 'data/derived/ncbi_links.csv', lambda r: r['accession'])
    phagesdb = {}
    for r in csv.DictReader((ROOT / 'data/derived/phagesdb_phages.csv').open(newline='')):
        for a in (r['genbank_accession'], r['refseq_accession']):
            if a:
                phagesdb[a] = r

    chosen, seen = [], set()
    def take(r, why):
        if (r['phage'], r['host']) not in seen:
            seen.add((r['phage'], r['host']))
            chosen.append((r, why))
    for phage, host in EXAMPLES:
        for r in pairs:
            if r['phage'] == phage and host in (None, r['host']):
                take(r, 'named example')
                break
    rng = random.Random(20261007)
    by_group = {}
    for r in pairs:
        by_group.setdefault(group(r), []).append(r)
    for g, rows in sorted(by_group.items()):
        for r in rng.sample(rows, min(PER_GROUP, len(rows))):
            take(r, f'sample: {g}')

    old = {}
    if SHEET.exists():
        old = {(r['phage'], r['host']): r for r in csv.DictReader(SHEET.open(newline=''))}
    out = []
    for i, (r, why) in enumerate(chosen, 1):
        p, h = r['phage'], r['host']
        t = trace.get((p, h), {})
        pdb = phagesdb.get(base(p), {})
        lk = links.get(base(p), {})
        row = {
            'id': i, 'why_selected': why, 'phage': p, 'phage_name': names.get(('phage', p), {}).get('name', ''),
            'host': h, 'host_name': names.get(('host', h), {}).get('name', ''),
            'sources_listing_pair': group(r),
            'ncbi_phage_host_field': f"{t.get('phage_host_field', '')}: {t.get('phage_host_value', '')}".strip(': '),
            'ncbi_auto_agreement': t.get('agreement', ''),
            'phagesdb_isolation_host': pdb.get('isolation_host', ''),
            'phagesdb_verified_hosts': pdb.get('verified_hosts', ''),
            'open_phage_ncbi': f'https://www.ncbi.nlm.nih.gov/nuccore/{p}',
            'open_host_ncbi': f'https://www.ncbi.nlm.nih.gov/nuccore/{h}',
            'open_phagesdb': pdb.get('url', ''),
            'open_papers': ' '.join([f'https://pubmed.ncbi.nlm.nih.gov/{x}/' for x in lk.get('pubmed', '').split(';') if x]
                                    + [f'https://pmc.ncbi.nlm.nih.gov/articles/{x}/' for x in lk.get('pmc', '').split(';') if x]),
            **{f: '' for f in FILL}}
        for f in FILL:   # keep anything already filled in by hand
            if old.get((p, h), {}).get(f):
                row[f] = old[(p, h)][f]
        out.append(row)
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with SHEET.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(len(out), 'pairs ->', SHEET)


if __name__ == '__main__':
    main()
