#!/usr/bin/env python3
"""Step 1: one row per Experiment 1 host and phage accession -> data/derived/entities.csv.

Reads the author pair tables (already parsed by the earlier project into pair_evidence.csv) and
host_phylum_info.csv (the 395 hosts of Figure 1A). Counts are unique pairs, not table rows.
"""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT  # stage-1 audit outputs and caches live in this repo too
PAIRS = OLD / 'data/derived/pair_evidence.csv'
HOST_PHYLUM = ROOT / 'data/raw/DeepPBI-KG_data_process/Figure1 A/host_phylum_info.csv'
EXTERNAL = ('external_PHI_final.xlsx', 'external_key_gene_PHI_new.xlsx')


def table_name(table):
    return table.split('/')[-1].split('#')[0]


def experiment1_rows():
    with PAIRS.open(newline='') as stream:
        return [r for r in csv.DictReader(stream) if r['experiment'] == '1']


def build(rows, phylum):
    tables, names, labels = defaultdict(set), defaultdict(Counter), defaultdict(dict)
    for r in rows:
        t = table_name(r['table'])
        for kind, acc, name in (('phage', r['phage'], r['phage_name']), ('host', r['host'], r['host_name'])):
            tables[kind, acc].add(t)
            if name:
                names[kind, acc][name] += 1
        if r['label'] in ('0', '1'):
            for kind, acc in (('phage', r['phage']), ('host', r['host'])):
                labels[kind, acc].setdefault((r['phage'], r['host']), set()).add(r['label'])
    out = []
    for (kind, acc), ts in sorted(tables.items()):
        pairs = labels[kind, acc]
        split = ('both' if any(t in EXTERNAL for t in ts) and any(t not in EXTERNAL for t in ts)
                 else 'external' if all(t in EXTERNAL for t in ts) else 'train_test')
        out.append({
            'kind': kind, 'accession': acc,
            'name': names[kind, acc].most_common(1)[0][0] if names[kind, acc] else '',
            'split': split, 'tables': ';'.join(sorted(ts)),
            'positive_pairs': sum('1' in v for v in pairs.values()),
            'negative_pairs': sum('0' in v for v in pairs.values()),
            'in_host_phylum_info': ('yes' if acc in phylum else 'no') if kind == 'host' else '',
            'phylum': phylum.get(acc, '') if kind == 'host' else ''})
    return out


def main():
    with HOST_PHYLUM.open(newline='', encoding='utf-8-sig') as stream:
        phylum = {r['host']: r['phylum'] for r in csv.DictReader(stream)}
    entities = build(experiment1_rows(), phylum)
    out = ROOT / 'data/derived/entities.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(entities[0]))
        writer.writeheader()
        writer.writerows(entities)
    hosts = [e for e in entities if e['kind'] == 'host']
    summary = {
        'phages': sum(e['kind'] == 'phage' for e in entities), 'hosts': len(hosts),
        'host_phylum_info_rows': len(phylum),
        'host_phylum_info_not_in_tables': sorted(set(phylum) - {e['accession'] for e in hosts}),
        'hosts_by_split': dict(Counter(e['split'] for e in hosts)),
        'hosts_in_phylum_file_by_split': dict(Counter(e['split'] for e in hosts if e['in_host_phylum_info'] == 'yes')),
        'hosts_with_positive_pairs': sum(e['positive_pairs'] > 0 for e in hosts),
        'phages_with_positive_pairs': sum(e['positive_pairs'] > 0 for e in entities if e['kind'] == 'phage'),
        'phylum_names': dict(Counter(phylum.values()).most_common())}
    (ROOT / 'data/derived/entities_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
