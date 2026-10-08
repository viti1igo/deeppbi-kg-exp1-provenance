#!/usr/bin/env python3
"""Count wet-lab keywords in each source paper (bibliography removed); write data/derived/keyword_scan.csv.

A hit only means the word appears. Read the context column: background text about lab methods
is not evidence that the paper's own dataset came from a lab.
"""
import csv
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
KEYWORDS = {
    'wet-lab': r'wet[- ]?lab\w*',
    'spot test/assay': r'spot(ting)?[- ](test|assay)s?',
    'plaque': r'plaque\w*',
    'in vitro': r'in[- ]vitro',
    'experimentally verified': r'experimental(ly)?\s+(verif|valid|confirm)\w*',
    'host range': r'host[- ]range',
}
PAPERS = {'DeepPBI-KG': 'PMC11440089', 'PredPHI': 'PMC8703204', 'PhageHosts': 'PMC5831537',
          'MVP': 'PMC5753265', 'PHISDetector': 'PMC9801046'}


def plain_text(xml):
    xml = re.sub(r'<ref-list.*?</ref-list>', '', xml, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', xml))


def scan(text):
    for keyword, pattern in KEYWORDS.items():
        for match in re.finditer(pattern, text, re.I):
            yield keyword, text[max(0, match.start() - 200):match.end() + 200]


def main():
    rows = []
    for source, pmc in PAPERS.items():
        text = plain_text((ROOT / f'data/raw/{pmc}.xml').read_text(encoding='utf-8'))
        rows += [{'source': source, 'pmc': pmc, 'keyword': k, 'context': c} for k, c in scan(text)]
    out = ROOT / 'data/derived/keyword_scan.csv'
    with out.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['source', 'pmc', 'keyword', 'context'])
        writer.writeheader()
        writer.writerows(rows)
    for source in PAPERS:
        counts = {k: sum(r['source'] == source and r['keyword'] == k for r in rows) for k in KEYWORDS}
        print(source, counts)


if __name__ == '__main__':
    main()
