#!/usr/bin/env python3
"""Step 3b: strain synonyms for every dataset host, so 'NRRL B-24152' can equal 'DSM 44215'.

Sources, each kept with its URL:
1. The host's own GenBank record and its linked BioSample (step 3b, data/derived/ncbi_links.csv):
   /strain and /culture_collection name one strain.
2. NCBI Taxonomy "type material" of the host's species: all culture-collection numbers of the
   species' type strain. Merged with (1) only when they share a designation.
Writes data/derived/strain_synonyms.csv and strain_synonyms_summary.json, and re-checks the
earlier NCBI trace (other-strain pairs that become same-strain through a synonym).
"""
from collections import Counter, defaultdict
import csv
import importlib.util
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT  # stage-1 audit outputs and caches live in this repo too
HEADERS = OLD / 'data/raw/NCBI/genbank_headers'
TAXRAW = ROOT / 'data/raw/NCBI/taxonomy'
EFETCH = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=taxonomy&retmode=xml&tool=deeppbi-provenance-audit&id='


def load(name):
    spec = importlib.util.spec_from_file_location(name, OLD / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def norm(designation):
    """'NRRL:B:24152', 'NRRL B-24152' -> 'NRRLB24152'; 'mc²155' -> 'MC2155'."""
    text = unicodedata.normalize('NFKC', designation).upper()
    text = re.sub(r'^(PERSONAL::|STRAIN |STR\. ?)', '', text.strip())
    return re.sub(r'[^A-Z0-9]', '', text)


def host_records(accessions):
    out = {}
    for path in sorted(HEADERS.glob('batch_*.xml')):
        for seq in ET.parse(path).getroot():
            acc = seq.findtext('GBSeq_primary-accession')
            if acc not in accessions:
                continue
            quals = defaultdict(list)
            for feature in seq.findall('GBSeq_feature-table/GBFeature'):
                if feature.findtext('GBFeature_key') == 'source':
                    for q in feature.findall('GBFeature_quals/GBQualifier'):
                        quals[q.findtext('GBQualifier_name')].append(q.findtext('GBQualifier_value') or '')
            taxon = next((x.split(':', 1)[1] for x in quals['db_xref'] if x.startswith('taxon:')), '')
            out[acc] = {'organism': seq.findtext('GBSeq_organism') or '', 'taxid': taxon,
                        'designations': quals['strain'] + quals['culture_collection']}
    return out


def fetch_taxa(taxids):
    """efetch taxonomy XML in batches of 200, cached per batch; returns taxid -> Taxon element."""
    TAXRAW.mkdir(parents=True, exist_ok=True)
    taxa = {}
    for path in TAXRAW.glob('taxa_*.xml'):
        for taxon in ET.parse(path).getroot().findall('Taxon'):
            taxa[taxon.findtext('TaxId')] = taxon
    todo = sorted(t for t in taxids if t and t not in taxa)
    number = len(list(TAXRAW.glob('taxa_*.xml')))
    for i in range(0, len(todo), 200):
        request = Request(EFETCH + ','.join(todo[i:i + 200]), headers={'User-Agent': 'DeepPBI-provenance-audit/1.0'})
        with urlopen(request, timeout=120) as response:
            body = response.read()
        root = ET.fromstring(body)
        (TAXRAW / f'taxa_{number:03d}.xml').write_bytes(body)
        number += 1
        for taxon in root.findall('Taxon'):
            taxa[taxon.findtext('TaxId')] = taxon
        time.sleep(0.4)
    return taxa


def biosample_designations():
    """host accession -> (BioSample id, strain and culture-collection values); empty if step 3b not run."""
    path = ROOT / 'data/derived/ncbi_links.csv'
    if not path.exists():
        return {}
    out = {}
    for r in csv.DictReader(path.open(newline='')):
        if r['kind'] == 'host' and r['biosample']:
            values = [v.strip() for f in ('biosample_strain', 'biosample_culture_collection')
                      for v in re.split(r'[;,]', r[f]) if v.strip()]
            out[r['accession']] = (r['biosample'].split(';')[0], values)
    return out


def species_of(taxon):
    if taxon.findtext('Rank') == 'species':
        return taxon.findtext('TaxId'), taxon.findtext('ScientificName')
    for t in taxon.findall('LineageEx/Taxon'):
        if t.findtext('Rank') == 'species':
            return t.findtext('TaxId'), t.findtext('ScientificName')
    return '', ''


def type_material(taxon):
    return [n.findtext('DispName') for n in taxon.iter('Name') if n.findtext('ClassCDE') == 'type material']


def build():
    entities = list(csv.DictReader((ROOT / 'data/derived/entities.csv').open(newline='')))
    hosts = {e['accession'].split('.')[0] for e in entities if e['kind'] == 'host'}
    records = host_records(hosts)
    biosample = biosample_designations()
    taxa = fetch_taxa({r['taxid'] for r in records.values()})
    species = {acc: species_of(taxa[r['taxid']]) if r['taxid'] in taxa else ('', '') for acc, r in records.items()}
    species_taxa = fetch_taxa({sid for sid, _ in species.values()})

    rows, synonyms = [], {}
    for acc, r in sorted(records.items()):
        sid, sname = species[acc]
        own = {norm(d) for d in r['designations'] if norm(d)}
        for d in r['designations']:
            rows.append({'host': acc, 'species_taxid': sid, 'species': sname, 'designation': d, 'normalized': norm(d),
                         'source': 'host GenBank record', 'url': f'https://www.ncbi.nlm.nih.gov/nuccore/{acc}'})
        sample, values = biosample.get(acc, ('', []))
        for d in values:
            if norm(d) and norm(d) not in own:
                own.add(norm(d))
                rows.append({'host': acc, 'species_taxid': sid, 'species': sname, 'designation': d, 'normalized': norm(d),
                             'source': 'host BioSample', 'url': f'https://www.ncbi.nlm.nih.gov/biosample/{sample}'})
        group = set(own)
        types = type_material(species_taxa[sid]) if sid in species_taxa else []
        if own & {norm(t) for t in types}:   # this host is the type strain: add its other designations
            for t in types:
                if norm(t) and norm(t) not in group:
                    group.add(norm(t))
                    rows.append({'host': acc, 'species_taxid': sid, 'species': sname, 'designation': t,
                                 'normalized': norm(t), 'source': 'NCBI Taxonomy type material',
                                 'url': f'https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={sid}'})
        synonyms[acc] = group
    return records, rows, synonyms


def strain_matches(claimed, host, synonyms, split_name):
    """True when the strain part of a host string is a known designation of this host strain."""
    rest = norm(''.join(split_name(claimed)[2]))
    return bool(rest) and rest in synonyms.get(host.split('.')[0], set())


def main():
    records, rows, synonyms = build()
    with (ROOT / 'data/derived/strain_synonyms.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    split_name = load('ncbi_trace').split_name
    trace = list(csv.DictReader((OLD / 'data/derived/ncbi_pair_trace.csv').open(newline='')))
    other = [t for t in trace if t['agreement'] == 'same_species_other_strain']
    rescued = [t for t in other if strain_matches(t['phage_host_value'], t['host'], synonyms, split_name)]
    summary = {
        'hosts_with_record': len(records),
        'hosts_with_designation': len({x['host'] for x in rows if x['source'] != 'NCBI Taxonomy type material'}),
        'designations_by_source': dict(Counter(x['source'] for x in rows)),
        'hosts_matching_type_strain': sum(any(x['source'] == 'NCBI Taxonomy type material' and x['host'] == a
                                              for x in rows) for a in records),
        'ncbi_trace_other_strain_pairs': len(other),
        'other_strain_pairs_same_strain_by_synonym': len(rescued),
        'rescued_examples': [(t['phage'], t['host'], t['phage_host_value'], t['host_organism'], t['host_strain'])
                             for t in rescued[:10]]}
    (ROOT / 'data/derived/strain_synonyms_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
