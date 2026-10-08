#!/usr/bin/env python3
"""Step 3b: follow each dataset accession's GenBank links to BioSample, BioProject, PubMed and PMC.

Link ids come from the cached GenBank headers (DBLINK xrefs and reference PubMed ids), so no
elink calls are needed. Linked records are fetched once with NCBI E-utilities and cached in
data/raw/NCBI/{biosample,bioproject,pubmed,pmc}/. Writes data/derived/ncbi_links.csv (one row per
accession) and ncbi_links_summary.json. BioSample /host, /lab_host and culture_collection are
annotations entered by submitters: they feed strain synonyms and host comparison, not wet-lab evidence.
"""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT  # stage-1 audit outputs and caches live in this repo too
HEADERS = OLD / 'data/raw/NCBI/genbank_headers'
RAW = ROOT / 'data/raw/NCBI'
EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
IDCONV = 'https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/'  # GET only; old /pmc/utils URL redirects
UA = {'User-Agent': 'DeepPBI-provenance-audit/1.0'}
BIOSAMPLE_FIELDS = ('host', 'lab_host', 'strain', 'culture_collection', 'isolation_source', 'isolate')


def post(url, params, attempts=3, get=False):
    """POST so long id lists fit (GET when the service requires it); NCBI allows 3 requests/s without a key."""
    query = urlencode({**params, 'tool': 'deeppbi-provenance-audit'})
    request = Request(f'{url}?{query}', headers=UA) if get else Request(url, data=query.encode(), headers=UA)
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=180) as response:
                body = response.read()
            time.sleep(0.4)
            return body
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(5 * (attempt + 1))


def cached_batches(folder, ids, fetch, size, parse):
    """Fetch ids not yet cached in folder/batch_NNN.*; return parse(all cached bodies)."""
    folder.mkdir(parents=True, exist_ok=True)
    done_path = folder / 'requested.txt'
    done = set(done_path.read_text().split()) if done_path.exists() else set()
    todo = sorted(set(ids) - done)
    number = len(list(folder.glob('batch_*')))
    for i in range(0, len(todo), size):
        chunk = todo[i:i + size]
        body, suffix = fetch(chunk)
        (folder / f'batch_{number:03d}.{suffix}').write_bytes(body)
        number += 1
        done |= set(chunk)
        done_path.write_text('\n'.join(sorted(done)) + '\n')
    return parse(sorted(folder.glob('batch_*')))


def header_links():
    links = {}
    for path in sorted(HEADERS.glob('batch_*.xml')):
        for seq in ET.parse(path).getroot():
            xrefs = defaultdict(list)
            for x in seq.findall('GBSeq_xrefs/GBXref'):
                xrefs[x.findtext('GBXref_dbname')].append(x.findtext('GBXref_id'))
            pubmed = [r.findtext('GBReference_pubmed') for r in seq.findall('GBSeq_references/GBReference')
                      if r.findtext('GBReference_pubmed')]
            links[seq.findtext('GBSeq_primary-accession')] = {
                'bioproject': xrefs['BioProject'], 'biosample': xrefs['BioSample'], 'pubmed': list(dict.fromkeys(pubmed))}
    return links


def parse_biosamples(paths):
    out = {}
    for path in paths:
        for sample in ET.parse(path).getroot().findall('BioSample'):
            attrs = defaultdict(list)
            for a in sample.findall('Attributes/Attribute'):
                attrs[a.attrib.get('harmonized_name') or a.attrib.get('attribute_name', '')].append(a.text or '')
            out[sample.attrib.get('accession')] = {k: ';'.join(attrs[k]) for k in BIOSAMPLE_FIELDS}
    return out


def parse_bioprojects(paths):
    out = {}
    for path in paths:
        result = json.loads(path.read_text()).get('result', {})
        for uid in result.get('uids', []):
            r = result[uid]
            out[r.get('project_acc')] = {'title': r.get('project_title', ''), 'data_type': r.get('project_data_type', '')}
    return out


def parse_pubmed(paths):
    out = {}
    for path in paths:
        result = json.loads(path.read_text()).get('result', {})
        for uid in result.get('uids', []):
            r = result[uid]
            out[uid] = {'title': r.get('title', ''), 'journal': r.get('source', ''), 'year': r.get('pubdate', '')[:4]}
    return out


def parse_pmc(paths):
    out = {}
    for path in paths:
        for r in json.loads(path.read_text()).get('records', []):
            if r.get('pmcid'):
                out[str(r.get('pmid'))] = r['pmcid']
    return out


def bioproject_uids(accessions):
    """esearch the project accessions; returns the numeric uids esummary needs."""
    term = ' OR '.join(f'{a}[Project Accession]' for a in accessions)
    body = post(EUTILS + 'esearch.fcgi', {'db': 'bioproject', 'term': term, 'retmax': 1000, 'retmode': 'json'})
    return json.loads(body)['esearchresult']['idlist']


def main():
    entities = list(csv.DictReader((ROOT / 'data/derived/entities.csv').open(newline='')))
    kinds = {e['accession'].split('.')[0]: e['kind'] for e in entities}
    links = {a: l for a, l in header_links().items() if a in kinds}
    all_ids = lambda key: {x for l in links.values() for x in l[key]}

    biosamples = cached_batches(
        RAW / 'biosample', all_ids('biosample'),
        lambda chunk: (post(EUTILS + 'efetch.fcgi', {'db': 'biosample', 'id': ','.join(chunk)}), 'xml'),
        200, parse_biosamples)
    bioprojects = cached_batches(
        RAW / 'bioproject', all_ids('bioproject'),
        lambda chunk: (post(EUTILS + 'esummary.fcgi', {'db': 'bioproject', 'retmode': 'json',
                                                       'id': ','.join(bioproject_uids(chunk))}), 'json'),
        100, parse_bioprojects)
    pubmed = cached_batches(
        RAW / 'pubmed', all_ids('pubmed'),
        lambda chunk: (post(EUTILS + 'esummary.fcgi', {'db': 'pubmed', 'retmode': 'json', 'id': ','.join(chunk)}), 'json'),
        200, parse_pubmed)
    pmc = cached_batches(
        RAW / 'pmc', all_ids('pubmed'),
        lambda chunk: (post(IDCONV, {'ids': ','.join(chunk), 'idtype': 'pmid', 'format': 'json'}, get=True), 'json'),
        200, parse_pmc)

    rows = []
    for acc, l in sorted(links.items()):
        sample = next((biosamples[s] for s in l['biosample'] if s in biosamples), {})
        rows.append({
            'kind': kinds[acc], 'accession': acc,
            'bioproject': ';'.join(l['bioproject']),
            'bioproject_title': ' | '.join(bioprojects.get(p, {}).get('title', '') for p in l['bioproject']),
            'biosample': ';'.join(l['biosample']),
            **{f'biosample_{k}': sample.get(k, '') for k in BIOSAMPLE_FIELDS},
            'pubmed': ';'.join(l['pubmed']),
            'pubmed_titles': ' | '.join(pubmed.get(p, {}).get('title', '') for p in l['pubmed']),
            'pmc': ';'.join(pmc[p] for p in l['pubmed'] if p in pmc)})
    with (ROOT / 'data/derived/ncbi_links.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for kind in ('phage', 'host'):
        k = [r for r in rows if r['kind'] == kind]
        summary[kind] = {'records': len(k), **{f'with_{c}': sum(bool(r[c]) for r in k) for c in (
            'bioproject', 'biosample', 'pubmed', 'pmc', *(f'biosample_{f}' for f in BIOSAMPLE_FIELDS))}}
    summary['fetched'] = {'biosample': len(biosamples), 'bioproject': len(bioprojects),
                          'pubmed': len(pubmed), 'pmc_ids': len(pmc)}
    summary['top_phage_bioprojects'] = Counter(r['bioproject_title'] for r in rows
                                               if r['kind'] == 'phage' and r['bioproject_title']).most_common(5)
    (ROOT / 'data/derived/ncbi_links_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
