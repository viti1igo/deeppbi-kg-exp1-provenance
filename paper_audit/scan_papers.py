#!/usr/bin/env python3
"""Search each audit paper for the strain codes of the DeepPBI-KG hosts paired with its phages.

Input: note/paper_audit.csv, data/derived/strain_synonyms.csv, pair_evidence_levels.csv and full text from
data/raw/papers/<PMCID>.xml (fetch_papers.py) or data/raw/papers/web/<PMID>.txt (text read in a browser).
Output: data/derived/paper_scan.csv, one row per (paper, paired host): mentions of the host's strain codes,
whether any mention is in a host-range-like table, nearby wet-lab keywords, and short snippets for review.
A mention is a lead for a human, not evidence by itself.
"""
from collections import Counter, defaultdict
import csv
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
KEYWORDS = re.compile(r'host[- ]range|spot(ted|ting)?\b|plaque|efficiency of plating|\bEOP\b|lys(is|ed|ate)|susceptib|'
                      r'sensitiv|resistan|propagat|isolated (on|using|with)|indicator|infect', re.I)
TABLE_HINT = re.compile(r'host[- ]range|susceptib|sensitiv|lytic (spectrum|activity)|plating|infectiv|strains? (used|tested)', re.I)


def clean(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()


def segments(pmc, pmid):
    """[(kind, label, text)] from PMC XML, or a single 'web' segment from saved browser text."""
    xml = ROOT / f'data/raw/papers/{pmc}.xml'
    web = ROOT / f'data/raw/papers/web/{pmid}.txt'
    if web.exists():
        return [('web', '', clean(web.read_text(encoding='utf-8')))]
    if not pmc or not xml.exists():
        return []
    root = ET.parse(xml).getroot()
    out = []
    for tw in root.iter('table-wrap'):
        label = clean(''.join(tw.findtext('label') or ''))
        caption = clean(' '.join(tw.find('caption').itertext())) if tw.find('caption') is not None else ''
        out.append(('table', f'{label} {caption[:120]}'.strip(), clean(' '.join(tw.itertext()))))
    body = root.find('.//body')
    if body is not None:
        for p in body.iter('p'):
            out.append(('text', '', clean(' '.join(p.itertext()))))
    for tag in ('abstract',):
        for a in root.iter(tag):
            out.append(('abstract', '', clean(' '.join(a.itertext()))))
    return out


def pattern(designation):
    """'NRRL B-16283' -> NRRL[\\W_]*B[\\W_]*16283 ; None if the code is too short to search safely."""
    d = unicodedata.normalize('NFKC', designation)
    d = re.sub(r'^(personal::|strain |str\. ?)', '', d.strip(), flags=re.I)
    chunks = re.findall(r'[A-Za-z]+|\d+', d)
    joined = ''.join(chunks)
    if len(joined) < 3 or not re.search(r'\d', joined) or (joined.isdigit() and len(joined) < 4):
        return None
    return re.compile(r'(?<![A-Za-z0-9])' + r'[\W_]*'.join(map(re.escape, chunks)) + r'(?![0-9])', re.I)


def main():
    audit = list(csv.DictReader((ROOT / 'note/paper_audit.csv').open(newline='')))
    synonyms = defaultdict(set)
    for r in csv.DictReader((ROOT / 'data/derived/strain_synonyms.csv').open(newline='')):
        synonyms[r['host']].add(r['designation'])
    levels_rows = list(csv.DictReader((ROOT / 'data/derived/pair_evidence_levels.csv').open(newline='')))
    names = {r['host']: r['host_name'] for r in levels_rows}
    links = {r['accession']: r['pubmed'].split(';') for r in csv.DictReader((ROOT / 'data/derived/ncbi_links.csv').open(newline=''))}
    levels = defaultdict(list)   # (pmid, host) -> levels of the pairs whose phage cites this paper
    for r in levels_rows:
        for pmid in links.get(r['phage'].split('.')[0], []):
            levels[pmid, r['host']].append(r['auto_level'].split('_')[0])
    out = []
    for paper in audit:
        segs = segments(paper['pmc'], paper['pmid'])
        hosts = [h.split(' ', 1)[0] for h in paper['paired_hosts_to_look_for'].split(' | ') if h]
        for host in hosts:
            designations = sorted(synonyms.get(host.split('.')[0], set()))
            pats = [(d, pattern(d)) for d in designations]
            searchable = [(d, p) for d, p in pats if p]
            hits, in_table, keys, snippets = 0, set(), set(), []
            for kind, label, text in segs:
                for d, p in searchable:
                    for m in p.finditer(text):
                        hits += 1
                        window = text[max(0, m.start() - 200):m.end() + 200]
                        keys |= {k.lower() for k in KEYWORDS.findall(window) if isinstance(k, str)} | \
                                {m2.group(0).lower() for m2 in KEYWORDS.finditer(window)}
                        if kind == 'table':
                            in_table.add(label[:60] + (' [host-range-like]' if TABLE_HINT.search(label) else ''))
                        if len(snippets) < 3:
                            snippets.append(f'[{kind}{": " + label[:40] if label else ""}] …{window}…')
            out.append({
                'tier': paper['tier'], 'pmid': paper['pmid'], 'pmc': paper['pmc'],
                'text_available': ('full' if any(k in ('text', 'table', 'web') for k, _, _ in segs)
                                   else 'abstract only' if segs else 'no'),
                'host': host, 'host_name': names.get(host, ''),
                'pair_levels': ' '.join(f'{lv}x{n}' for lv, n in sorted(Counter(levels[paper['pmid'], host]).items())),
                'designations_searched': '; '.join(d for d, _ in searchable),
                'designations_too_short': '; '.join(d for d, p in pats if not p),
                'mentions': hits, 'in_tables': ' | '.join(sorted(in_table)),
                'keywords_near': '; '.join(sorted(keys)), 'snippets': ' || '.join(snippets)})
    with (ROOT / 'data/derived/paper_scan.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print('rows', len(out), '| text available', Counter(r['text_available'] for r in out),
          '| hosts mentioned', sum(r['mentions'] > 0 for r in out), '| in a table', sum(bool(r['in_tables']) for r in out),
          '| no searchable code', sum(not r['designations_searched'] for r in out))


if __name__ == '__main__':
    main()
