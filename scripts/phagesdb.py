#!/usr/bin/env python3
"""Step 3a: dump PhagesDB (Actinobacteriophage Database) and match it to the dataset phages.

Pages through https://phagesdb.org/api/phages/ (documented JSON API) and /api/host_strains/,
caching each page in data/raw/PhagesDB/ so reruns make no requests. Writes
data/derived/phagesdb_phages.csv (one row per PhagesDB phage with an accession) and
phagesdb_summary.json (coverage against the dataset phages).
PhagesDB `isolation_host` = the strain the phage was isolated on (plaque isolation, one strain);
`verified_hosts` / `verified_non_hosts` = host-range results, when recorded.
"""
import csv
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/PhagesDB'
API = 'https://phagesdb.org/api/'
UA = {'User-Agent': 'Mozilla/5.0 (DeepPBI-provenance-audit)'}  # default Python UA gets HTTP 403
PAGE_SIZE = 500


def get_json(url, attempts=3):
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=UA), timeout=180) as response:
                return json.load(response)
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(10 * (attempt + 1))


def fetch_pages():
    """Cache every page; a page file is written only after it parses."""
    RAW.mkdir(parents=True, exist_ok=True)
    page = 1
    while True:
        path = RAW / f'phages_p{page:03d}.json'
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = get_json(f'{API}phages/?page={page}&page_size={PAGE_SIZE}')
            path.write_text(json.dumps(data))
            time.sleep(1)
        if not data.get('next'):
            break
        page += 1
    strains = RAW / 'host_strains.json'
    if not strains.exists():
        strains.write_text(json.dumps(get_json(f'{API}host_strains/')))


def strain_text(host):
    return ' '.join(x for x in (host.get('genus'), host.get('species'), host.get('strain_name')) if x) if host else ''


def resolve_strain(ref):
    """verified_hosts holds links like https://phagesdb.org/api/host_strains/101/; fetch each once (cached)."""
    if isinstance(ref, dict):
        return ref
    path = RAW / f"host_strain_{ref.rstrip('/').rsplit('/', 1)[-1]}.json"
    if not path.exists():
        path.write_text(json.dumps(get_json(ref)))
        time.sleep(1)
    return json.loads(path.read_text())


def records():
    for path in sorted(RAW.glob('phages_p*.json')):
        yield from json.loads(path.read_text())['results']


def base(accession):
    return (accession or '').strip().split('.')[0]


def main():
    fetch_pages()
    rows = []
    for r in records():
        iso = r.get('isolation_host') or {}
        rows.append({
            'phage_name': r['phage_name'],
            'genbank_accession': base(r.get('genbank_accession')),
            'refseq_accession': base(r.get('refseq_accession')),
            'isolation_host': strain_text(iso),
            'isolation_host_genbank': iso.get('genbank_accession', ''),
            'verified_hosts': ';'.join(strain_text(resolve_strain(h)) for h in r.get('verified_hosts') or []),
            'verified_non_hosts': ';'.join(strain_text(resolve_strain(h)) for h in r.get('verified_non_hosts') or []),
            'discovery_notes': (r.get('discovery_notes') or '').replace('\n', ' ')[:300],
            'url': f"https://phagesdb.org/phages/{r['phage_name']}/"})
    out = ROOT / 'data/derived/phagesdb_phages.csv'
    with out.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    dataset = {base(e['accession']) for e in csv.DictReader((ROOT / 'data/derived/entities.csv').open())
               if e['kind'] == 'phage'}
    by_acc = {}
    for r in rows:
        for a in (r['genbank_accession'], r['refseq_accession']):
            if a:
                by_acc[a] = r
    matched = [by_acc[a] for a in dataset if a in by_acc]
    summary = {
        'phagesdb_phages': len(rows),
        'phagesdb_with_accession': sum(bool(r['genbank_accession'] or r['refseq_accession']) for r in rows),
        'phagesdb_with_verified_hosts': sum(bool(r['verified_hosts']) for r in rows),
        'phagesdb_with_verified_non_hosts': sum(bool(r['verified_non_hosts']) for r in rows),
        'dataset_phages': len(dataset),
        'dataset_phages_in_phagesdb': len(matched),
        'matched_with_isolation_host': sum(bool(r['isolation_host']) for r in matched),
        'matched_with_verified_hosts': sum(bool(r['verified_hosts']) for r in matched),
        'matched_with_verified_non_hosts': sum(bool(r['verified_non_hosts']) for r in matched)}
    (ROOT / 'data/derived/phagesdb_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
