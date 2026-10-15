#!/usr/bin/env python3
"""Fetch PMC full-text XML for the audit papers (note/paper_audit.csv) via NCBI E-utilities.

One file per paper in data/raw/papers/<PMCID>.xml with a .receipt.json (URL, SHA-256, size, time).
Some publishers only allow metadata through the API ("does not allow downloading of the full text");
those are listed as web_only in data/derived/paper_fetch.csv and must be read on the PMC web page.
Cached: papers already on disk are not fetched again.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/papers'
EFETCH = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&tool=deeppbi-provenance-audit&id='


def fetch(pmcid):
    path = RAW / f'{pmcid}.xml'
    if not path.exists():
        url = EFETCH + pmcid
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={'User-Agent': 'DeepPBI-provenance-audit/1.0'}), timeout=120) as r:
                    body = r.read()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        path.write_bytes(body)
        Path(str(path) + '.receipt.json').write_text(json.dumps({
            'source': 'PMC', 'path': str(path.relative_to(ROOT)), 'url': url, 'kind': 'xml',
            'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'status': 'downloaded',
            'retrieved_at': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n')
        time.sleep(0.4)  # NCBI: 3 requests/s without an API key
    text = path.read_text(encoding='utf-8', errors='replace')
    return {'body': '<body' in text, 'tables': text.count('<table-wrap'), 'bytes': path.stat().st_size}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'note/paper_audit.csv').open(newline='') as stream:
        audit = list(csv.DictReader(stream))
    out = []
    for r in audit:
        row = {'tier': r['tier'], 'pmid': r['pmid'], 'pmc': r['pmc'], 'title': r['title'][:90]}
        if not r['pmc']:
            row.update(access='paywalled', tables='', bytes='')
        else:
            info = fetch(r['pmc'])
            row.update(access='full_text_xml' if info['body'] else 'web_only', tables=info['tables'], bytes=info['bytes'])
        out.append(row)
    with (ROOT / 'data/derived/paper_fetch.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    from collections import Counter
    print(dict(Counter(r['access'] for r in out)))


if __name__ == '__main__':
    main()
