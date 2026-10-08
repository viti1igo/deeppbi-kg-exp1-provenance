#!/usr/bin/env python3
"""Grade what NCBI itself says about each Experiment 1 positive pair.

Every Experiment 1 pair uses NCBI accessions, whichever of the five sources it came from.
Step 1 fetches the GenBank header of each phage and host record (source feature and
references, sequence trimmed to 1 bp) into data/raw/NCBI/genbank_headers/, once.
Step 2 compares the phage record's /host and /lab_host with the paired host record and writes
data/derived/ncbi_pair_trace.csv plus a summary. Nothing here is promoted to wet-lab evidence:
/host and /lab_host name one isolation or propagation host, not a tested host range.
"""
import csv
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/NCBI/genbank_headers'
EFETCH = ('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&rettype=gb&retmode=xml'
          '&seq_start=1&seq_stop=1&tool=deeppbi-provenance-audit&id=')
BATCH = 100


def positive_pairs():
    pairs = {}
    with (ROOT / 'data/derived/pair_evidence.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['experiment'] == '1' and row['label'] == '1':
                pairs.setdefault((row['phage'], row['host']), row['upstream_exact_match'])
    return pairs


def get(chunk):
    request = Request(EFETCH + ','.join(chunk), headers={'User-Agent': 'DeepPBI-provenance-audit/1.0'})
    with urlopen(request, timeout=120) as response:
        body = response.read()
    ET.fromstring(body)
    time.sleep(0.4)  # NCBI allows 3 requests/s without an API key
    return body


def fetch(accessions):
    """Download missing header batches; a batch file is written only after it parses.

    A batch NCBI cannot serve is split in half until the failing accession is isolated;
    those are listed in unfetchable.txt rather than stopping the run.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    have = set()
    for path in RAW.glob('batch_*.xml'):
        have |= {s.findtext('GBSeq_primary-accession') for s in ET.parse(path).getroot()}
    failed_path = RAW / 'unfetchable.txt'
    failed = set(failed_path.read_text().split()) if failed_path.exists() else set()
    todo = sorted(a for a in accessions if a.split('.')[0] not in have and a not in failed)
    queue = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    number = len(list(RAW.glob('batch_*.xml')))
    while queue:
        chunk = queue.pop(0)
        try:
            body = get(chunk)
        except Exception:
            if len(chunk) == 1:
                failed.add(chunk[0])
                failed_path.write_text('\n'.join(sorted(failed)) + '\n')
            else:
                queue[:0] = [chunk[:len(chunk) // 2], chunk[len(chunk) // 2:]]
            continue
        (RAW / f'batch_{number:03d}.xml').write_bytes(body)
        number += 1
    return len(todo)


def load_records():
    records = {}
    for path in sorted(RAW.glob('batch_*.xml')):
        for seq in ET.parse(path).getroot():
            quals = {}
            for feature in seq.findall('GBSeq_feature-table/GBFeature'):
                if feature.findtext('GBFeature_key') == 'source':
                    for q in feature.findall('GBFeature_quals/GBQualifier'):
                        quals.setdefault(q.findtext('GBQualifier_name'), q.findtext('GBQualifier_value') or '')
            papers = []
            for ref in seq.findall('GBSeq_references/GBReference'):
                journal = ref.findtext('GBReference_journal') or ''
                if ref.findtext('GBReference_pubmed') or not journal.startswith(('Submitted', 'Unpublished')):
                    papers.append(ref.findtext('GBReference_pubmed') or journal[:80])
            records[seq.findtext('GBSeq_primary-accession')] = {
                'version': seq.findtext('GBSeq_accession-version'), 'definition': seq.findtext('GBSeq_definition'),
                'organism': seq.findtext('GBSeq_organism') or '', 'quals': quals, 'papers': papers}
    return records


def words(text):
    return re.sub(r'[^a-z0-9 ]', ' ', text.lower()).split()


RANK_WORDS = {'subsp', 'serovar', 'sv', 'pv', 'pathovar', 'biovar', 'bv', 'var'}


def split_name(text):
    """(genus, species epithet, strain words); rank labels such as serovar are skipped with their value."""
    w = words(text)
    genus, epithet = (w + ['', ''])[:2]
    rest, skip = [], False
    for x in w[2:]:
        if skip:
            skip = False
        elif x in RANK_WORDS:
            skip = True
        elif x not in ('strain', 'str'):
            rest.append(x)
    return genus, epithet, rest


def host_level(value):
    """Taxonomic depth of a /host or /lab_host string."""
    genus, epithet, rest = split_name(value)
    if not genus:
        return 'none'
    if not epithet or epithet in ('sp', 'spp'):
        return 'genus'
    return 'strain' if rest else 'species'


def compare(phage_host, host_record):
    """Deepest rank at which the phage record's host agrees with the paired host record.

    A differing genus with the same epithet counts as the same species (renamed genera such as
    Mycobacterium -> Mycolicibacterium smegmatis); a one-letter genus is read as an abbreviation.
    """
    if not phage_host or not host_record:
        return 'not_comparable'
    g1, e1, rest = split_name(phage_host)
    g2, e2, _ = split_name(host_record['organism'])
    same_genus = g1 == g2 or (len(g1) == 1 and g2.startswith(g1))
    same_species = bool(e1) and e1 == e2 and e1 not in ('sp', 'spp')
    if not (same_genus or same_species):
        return 'different_genus'
    if not same_species:
        return 'same_genus'
    strain = ''.join(words(host_record['quals'].get('strain', '')))
    claimed = ''.join(rest)
    if strain and claimed and (strain in claimed or claimed in strain):
        return 'same_strain'
    return 'same_species_other_strain' if claimed else 'same_species'


def main():
    pairs = positive_pairs()
    needed = {p for p, _ in pairs} | {h for _, h in pairs}
    print('fetched batches for', fetch(needed), 'new accessions')
    records = load_records()
    rows = []
    for (phage, host), upstream in sorted(pairs.items()):
        p, h = records.get(phage.split('.')[0]), records.get(host.split('.')[0])
        quals = p['quals'] if p else {}
        field = 'host' if quals.get('host') else 'lab_host' if quals.get('lab_host') else ''
        value = quals.get(field, '')
        rows.append({
            'phage': phage, 'host': host, 'upstream_exact_match': upstream,
            'phage_record': p['version'] if p else 'missing', 'phage_definition': p['definition'] if p else '',
            'host_record': h['version'] if h else 'missing', 'host_organism': h['organism'] if h else '',
            'host_strain': h['quals'].get('strain', '') if h else '',
            'phage_host_field': field, 'phage_host_value': value,
            'phage_lab_host': quals.get('lab_host', ''),
            'phage_host_level': host_level(value) if p else 'missing',
            'agreement': compare(value, h) if p else 'missing',
            'phage_papers': ';'.join(p['papers']) if p else ''})
    out = ROOT / 'data/derived/ncbi_pair_trace.csv'
    with out.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {'positive_pairs': len(rows), 'records_found': len(records)}
    for key in ('phage_host_field', 'phage_host_level', 'agreement'):
        summary[key] = {}
        for row in rows:
            summary[key][row[key] or 'none'] = summary[key].get(row[key] or 'none', 0) + 1
    summary['with_paper'] = sum(bool(r['phage_papers']) for r in rows)
    summary['same_strain_with_paper'] = sum(r['agreement'] == 'same_strain' and bool(r['phage_papers']) for r in rows)
    (ROOT / 'data/derived/ncbi_pair_trace_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
