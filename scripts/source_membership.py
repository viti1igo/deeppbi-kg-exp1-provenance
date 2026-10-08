#!/usr/bin/env python3
"""Step 2: which source each Experiment 1 host, phage and pair can be found in.

Writes data/derived/source_membership_entities.csv (one row per host/phage, = per-host table for
anh Minh), source_membership_pairs.csv (one row per labelled unique pair) and a summary.
Values: yes / no / not_checkable (the source has no field to check against) / not_fetched.
Presence in a source is not evidence of a lab result; it only says where the record could come from.
"""
from collections import Counter, defaultdict
import csv
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT  # stage-1 audit outputs and caches live in this repo too


def load(name):
    spec = importlib.util.spec_from_file_location(name, OLD / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load('audit')          # id_rows (XLSX reader), accession_base
ncbi = load('ncbi_trace')      # split_name, compare (handles renamed genera)
base = audit.accession_base

PREDPHI = OLD / 'data/raw/PredPHI/repository.zip'  # tables are read from the archive, never extracted
PHAGEHOSTS = OLD / 'data/raw/PhageHosts/data/phage_with_host.tsv'
VHM = OLD / 'data/raw/PHISDetector/bin/virhostmatcher/Supplemental_table_virus_and_host_genomes.xlsx'
PHIS_PAIRS = ROOT / 'data/raw/PHISDetector/phage-bacteria-pairs.txt'
NCBI_HEADERS = OLD / 'data/raw/NCBI/genbank_headers'


def wgs_prefix(accession):
    """QUAI01000001 / NZ_FNLM01000034 -> QUAI01 / FNLM01 (WGS project); '' otherwise."""
    a = base(accession).removeprefix('NZ_')
    return a[:6] if len(a) >= 12 and a[:4].isalpha() and a[4:].isdigit() else ''


def same_species(name_a, name_b):
    if not name_a or not name_b:
        return ''
    return 'yes' if ncbi.compare(name_a, {'organism': name_b, 'quals': {}}) in (
        'same_strain', 'same_species', 'same_species_other_strain') else 'no'


def read_predphi():
    phages, hosts, pairs = set(), set(), defaultdict(set)
    with zipfile.ZipFile(PREDPHI) as archive:
        members = {m.rsplit('/', 1)[-1]: m for m in archive.namelist() if '/data/' in m}
        for name in ('training_set.csv', 'test_set.csv', 'test_random.csv', 'test-test.csv'):
            for r in audit.csv_rows(archive.read(members[name])):
                p, h = base(r['phage']), base(r['host'])
                phages.add(p)
                hosts.add(h)
                pairs[p, h].add(r['class'])
    return phages, hosts, pairs


def read_phagehosts():
    with PHAGEHOSTS.open(newline='') as stream:
        return {base(r[0]): r[2] for r in csv.reader(stream, delimiter='\t') if len(r) >= 3}


def read_phisdetector():
    phage_host = defaultdict(set)   # phage -> host names (benchmark pairs + VirHostMatcher viruses)
    flags = defaultdict(set)
    with PHIS_PAIRS.open(newline='') as stream:
        for r in csv.DictReader(stream, delimiter='\t'):
            phage_host[base(r['phage_id'])].add(r['host'])
            flags[base(r['phage_id'])].add(r['flag'])
    for r in audit.id_rows(VHM, 'Viruses'):
        if r['_excel_row'] > 11 and r.get('B'):
            phage_host[base(r['B'])].add(r.get('C', ''))
            flags[base(r['B'])].add('virhostmatcher')
    host_ids = set()
    for r in audit.id_rows(VHM, 'Hosts'):
        if r['_excel_row'] > 3 and r.get('A'):
            host_ids |= {base(x.strip()) for x in r['A'].split(',')}
    return phage_host, flags, host_ids


def read_ncbi():
    found = set()
    for path in NCBI_HEADERS.glob('batch_*.xml'):
        found |= {s.findtext('GBSeq_primary-accession') for s in ET.parse(path).getroot()}
    return found


def main():
    entities = list(csv.DictReader((ROOT / 'data/derived/entities.csv').open(newline='')))
    names = {(e['kind'], e['accession']): e['name'] for e in entities}
    pp_phages, pp_hosts, pp_pairs = read_predphi()
    ph = read_phagehosts()
    phis_host, phis_flags, vhm_hosts = read_phisdetector()
    ncbi_found = read_ncbi()

    ent_rows = []
    for e in entities:
        a, kind = base(e['accession']), e['kind']
        row = dict(e)
        row['predphi'] = 'yes' if a in (pp_phages if kind == 'phage' else pp_hosts) else 'no'
        if kind == 'phage':
            row['phagehosts'] = 'yes' if a in ph else 'no'
            row['phisdetector'] = 'yes' if a in phis_host else 'no'
            row['phisdetector_sets'] = ';'.join(sorted(phis_flags.get(a, ())))
        else:  # PhageHosts lists host species only; PHISDetector/VirHostMatcher lists host genomes
            row['phagehosts'] = 'not_checkable'
            row['phisdetector'] = 'yes' if a in vhm_hosts or wgs_prefix(a) in vhm_hosts else 'no'
            row['phisdetector_sets'] = ''
        row['ncbi_header'] = ('yes' if a in ncbi_found else 'no') if int(e['positive_pairs']) else 'not_fetched'
        row['mvp'] = 'not_available'
        ent_rows.append(row)

    labels = defaultdict(set)
    with (OLD / 'data/derived/pair_evidence.csv').open(newline='') as stream:
        for r in csv.DictReader(stream):
            if r['experiment'] == '1' and r['label'] in ('0', '1'):
                labels[r['phage'], r['host']].add(r['label'])
    pair_rows = []
    for (phage, host), ls in sorted(labels.items()):
        p, h = base(phage), base(host)
        host_name = names.get(('host', host), '')
        upstream = pp_pairs.get((p, h), set())
        pair_rows.append({
            'phage': phage, 'host': host, 'label': '/'.join(sorted(ls)),
            'predphi_pair': '/'.join(sorted(upstream)) if upstream else 'absent',
            'phagehosts_phage': 'yes' if p in ph else 'no',
            'phagehosts_host_species': ph.get(p, ''),
            'phagehosts_same_species': same_species(ph.get(p, ''), host_name),
            'phisdetector_phage': 'yes' if p in phis_host else 'no',
            'phisdetector_host_names': ';'.join(sorted(phis_host.get(p, ()))),
            'phisdetector_same_species': ('yes' if any(same_species(x, host_name) == 'yes' for x in phis_host[p])
                                          else 'no') if p in phis_host else '',
            'phisdetector_sets': ';'.join(sorted(phis_flags.get(p, ()))),
            'mvp': 'not_available'})

    derived = ROOT / 'data/derived'
    for path, rows in ((derived / 'source_membership_entities.csv', ent_rows),
                       (derived / 'source_membership_pairs.csv', pair_rows)):
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def tally(rows, keys):
        return {k: dict(Counter(r[k] for r in rows)) for k in keys}
    positives = [r for r in pair_rows if '1' in r['label'].split('/')]
    found_any = lambda r: (r['predphi_pair'] != 'absent' or r['phagehosts_same_species'] == 'yes'
                           or r['phisdetector_same_species'] == 'yes')
    summary = {
        'phages': tally([r for r in ent_rows if r['kind'] == 'phage'], ['predphi', 'phagehosts', 'phisdetector', 'ncbi_header']),
        'hosts': tally([r for r in ent_rows if r['kind'] == 'host'], ['predphi', 'phisdetector', 'ncbi_header']),
        'hosts_in_host_phylum_info': tally([r for r in ent_rows if r['in_host_phylum_info'] == 'yes'], ['predphi', 'phisdetector']),
        'positive_pairs': len(positives),
        'positive_pairs_by_source': tally(positives, ['predphi_pair', 'phagehosts_same_species', 'phisdetector_same_species']),
        'positive_pairs_found_in_some_source': sum(found_any(r) for r in positives),
        'positive_pairs_in_no_checkable_source': sum(not found_any(r) for r in positives),
        'negative_pairs': len(pair_rows) - len(positives),
        'negative_pairs_by_predphi': dict(Counter(r['predphi_pair'] for r in pair_rows if r['label'] == '0')),
        'not_available': {'MVP': 'mvp.medgenius.info returns HTTP 520 (2026-10-07); no public pair export',
                          'PHISDetector_full_db': '102 GB tarball not downloaded; benchmark pair list and VirHostMatcher table used'}}
    (derived / 'source_membership_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
