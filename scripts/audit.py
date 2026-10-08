#!/usr/bin/env python3
"""Read-only raw-data audit: pair quality, source matches and diagnostic sampling."""
import csv
import hashlib
import json
import re
import io
from itertools import combinations
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def id_rows(path, sheet_name="ID"):
    """Yield cells with their actual Excel row number, preserving sparse rows."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as stream:
                for _, e in ET.iterparse(stream, events=['end']):
                    if e.tag.endswith('}si'):
                        shared.append(''.join(e.itertext()))
                        e.clear()
        workbook = ET.fromstring(z.read('xl/workbook.xml'))
        sheet = next((s for s in workbook.findall('s:sheets/s:sheet', NS)
                      if s.attrib['name'] == sheet_name), None)
        if sheet is None:
            return
        relid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        relations = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target = next(r.attrib['Target'] for r in relations if r.attrib['Id'] == relid)
        member = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        with z.open(member) as stream:
            for _, e in ET.iterparse(stream, events=['end']):
                if not e.tag.endswith('}row'):
                    continue
                row = {}
                for c in e.findall('s:c', NS):
                    value = c.findtext('s:v', '', NS)
                    if c.attrib.get('t') == 's':
                        value = shared[int(value)]
                    elif c.attrib.get('t') == 'inlineStr':
                        value = ''.join(c.find('s:is', NS).itertext())
                    column = ''.join(x for x in c.attrib['r'] if x.isalpha())
                    row[column] = value
                row["_excel_row"] = int(e.attrib["r"])
                yield row
                e.clear()


def accession_base(value):
    # Only accession-shaped strings, never isolate names such as KP.1.
    return re.sub(r"\.\d+$", "", value) if re.fullmatch(r"(?:[A-Z]{1,4}_[A-Z]{0,6}|[A-Z]{1,6})\d{5,}(?:\.\d+)?", value) else value


def pair(row, normalized=False):
    key = (row['phage'], row['host'])
    return tuple(map(accession_base, key)) if normalized else key


def quality(rows, normalized=False):
    groups = defaultdict(list)
    for r in rows:
        if r['phage'] and r['host']:
            groups[pair(r, normalized)].append(r)
    conflicts = []
    for k, values in sorted(groups.items()):
        labels = sorted({r['label'] for r in values if r['label'] in ('0', '1')})
        if len(labels) > 1:
            conflicts.append(dict(phage=k[0], host=k[1], labels=labels,
                                  references=[r['table']+':'+str(r['excel_row']) for r in values]))
    return dict(rows=len(rows), unique_pairs=len(groups),
                duplicate_pairs=sum(len(v)>1 for v in groups.values()),
                duplicate_excess_rows=sum(len(v)-1 for v in groups.values()),
                missing_identifiers=sum(not r['phage'] or not r['host'] for r in rows),
                invalid_or_missing_labels=sum(r['label'] not in ('0','1') for r in rows),
                conflicting_pairs=len(conflicts), conflicts=conflicts)


def csv_rows(body):
    text = body.decode('utf-8-sig')
    header = text.splitlines()[0] if text else ''
    delimiter = '\t' if '\t' in header else ','
    return csv.DictReader(io.StringIO(text), delimiter=delimiter)


def canonical(row, table, index, experiment):
    def get(*names):
        return next((row[n] or '' for n in names if n in row), '')
    return dict(table=table, excel_row=index, experiment=experiment,
                phage=get('phage','phage_id'), host=get('host','host_id'),
                label=get('label','class'), phage_name=get('phage_name','phage_def'),
                host_name=get('host_name','host_species'))


def is_pair_header(headers):
    return bool({'phage','phage_id'} & set(headers)) and bool({'host','host_id'} & set(headers))


def write_csv(path, rows, columns):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def json_out(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def evidence_category(row):
    # No automatic path to direct_wetlab: that requires a curated exact assay trace.
    if row['experiment'] == '2':
        return 'dataset_assay_described_pair_unverified'
    return {'0':'sampled_negative_not_wetlab', '1':'positive_assay_source_unresolved'}.get(row['label'],'unknown')


def shared_pairs(rows_a, rows_b, normalized=False):
    return len({pair(r,normalized) for r in rows_a if all(pair(r))} &
               {pair(r,normalized) for r in rows_b if all(pair(r))})


def collect_tables():
    """Inventory local tables/archive members; pair data have explicit ID columns."""
    inventory, rows, upstream = [], [], []
    sequences = defaultdict(list)
    for path in sorted((ROOT/'data/raw').rglob('*')):
        if not path.is_file() or path.name.startswith('._') or 'extracted' in path.parts:
            continue
        relative = str(path.relative_to(ROOT))
        if path.suffix.lower() not in ('.csv','.tsv','.xlsx'):
            continue
        source = path.relative_to(ROOT/'data/raw').parts[0]
        experiment = '2' if 'Table2' in path.parts else '1'
        if path.suffix.lower() == '.xlsx':
            with zipfile.ZipFile(path) as z:
                sheets = [s.attrib['name'] for s in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS)]
            for sheet in sheets:
                iterator = id_rows(path, sheet)
                first = next(iterator, {})
                headers = {v:k for k,v in first.items() if k != '_excel_row'}
                recognized = is_pair_header(headers)
                entry = dict(path=relative, sheet=sheet, headers=list(headers),
                             classification='pair_table' if recognized else 'non_pair_sheet',
                             schema_gap='' if sheet == 'ID' else 'no_ID_sheet' if 'ID' not in sheets else '',
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                if source == 'PHISDetector':
                    entry['classification'] = 'host_name_or_genome_catalog_no_exact_pair_key'
                    entry['schema_gap'] = 'Viruses header at row 11; host names only, no host accession per virus'
                if recognized:
                    data = [canonical({h:r.get(c,'') for h,c in headers.items()}, relative+'#'+sheet,
                                      r['_excel_row'], experiment) for r in iterator]
                    rows.extend(data)
                    entry['rows'] = len(data)
                    if not {'label','class'} & set(headers):
                        entry['schema_gap'] = ';'.join(filter(None,[entry['schema_gap'],'missing_label_header']))
                inventory.append(entry)
        else:
            body = path.read_bytes()
            reader = csv_rows(body)
            headers = reader.fieldnames or []
            recognized = is_pair_header(headers)
            entry = dict(path=relative, headers=headers[:15], sha256=hashlib.sha256(body).hexdigest(),
                         classification='pair_table' if recognized else 'non_pair_features_or_summary')
            if {'label','pred','prob'} <= set(headers):
                entry['classification'] = 'prediction_scores_no_pair_identifiers'
            if source == 'PhageHosts':
                entry['classification'] = 'host_species_annotation_no_host_accession'
                entry['headers'] = ['phage_accession','phage_name','host_genus_species (headerless)']
            if recognized:
                data = [canonical(r,relative,i,experiment) for i,r in enumerate(reader,2)]
                rows.extend(data)
                entry['rows'] = len(data)
            inventory.append(entry)
    for archive in sorted((ROOT/'data/raw').glob('*/repository.zip')):
        source = archive.parent.name
        with zipfile.ZipFile(archive) as z:
            for member in sorted(z.namelist()):
                if member.endswith('/'):
                    continue
                with z.open(member) as f:
                    sha = hashlib.file_digest(f,'sha256').hexdigest()
                entry = dict(path=str(archive.relative_to(ROOT))+'!'+member, sha256=sha,
                             classification='non_pair_archive_member')
                if Path(member).suffix.lower() in ('.fa','.fna','.fasta'):
                    sequences[accession_base(Path(member).stem)].append(entry['path'])
                if member.endswith(('.csv','.tsv')):
                    reader = csv_rows(z.read(member))
                    headers = reader.fieldnames or []
                    if is_pair_header(headers):
                        data = [canonical(r,entry['path'],i,'1') for i,r in enumerate(reader,2)]
                        entry.update(classification='pair_table', rows=len(data), headers=headers,
                                     schema_gap='' if {'label','class'} & set(headers) else 'missing_label_header')
                        if source == 'PredPHI':
                            for r in data: r['source'] = source
                            upstream.extend(data)
                        else:
                            rows.extend(data)
                    else:
                        entry['classification'] = 'non_pair_features_or_summary'
                inventory.append(entry)
    return inventory, rows, upstream, sequences


def sample_pairs(rows, upstream, curated):
    """Diagnostic, not prevalence sampling: five per source, five unknown, ten flags."""
    by_pair, matches, names = defaultdict(list), defaultdict(list), defaultdict(set)
    for r in rows:
        if r['experiment']=='1' and all(pair(r)):
            by_pair[pair(r)].append(r)
            if r['host_name']: names[r['host']].add(r['host_name'])
    for r in upstream:
        matches[pair(r)].append(r)
        if r['host_name']: names[r['host']].add(r['host_name'])
    versions = defaultdict(set)
    for k in by_pair: versions[tuple(map(accession_base,k))].add(k)
    flags = defaultdict(set)
    for k, values in by_pair.items():
        labels = {r['label'] for r in values+matches[k] if r['label'] in ('0','1')}
        if len(labels)>1: flags[k].add('label_conflict')
        if len(names[k[1]])>1: flags[k].add('host_name_variation_candidate')
        if len(versions[tuple(map(accession_base,k))])>1: flags[k].add('accession_version_candidate')
    for r in curated:
        k = (r['phage_accession'],r['host_accession'])
        if k in by_pair and r['relation_to_deeppbi_pair']=='different_host_strain':
            flags[k].add('curated_strain_mismatch')
    chosen = defaultdict(set)
    positives = sorted(k for k,v in by_pair.items() if any(r['label']=='1' for r in v))
    sources = sorted({r['source'] for r in upstream})
    for source in sources:
        for k in [k for k in positives if any(r['source']==source for r in matches[k])][:5]:
            chosen[k].add('positive_match_'+source)
    for k in [k for k in positives if not matches[k]][:5]: chosen[k].add('positive_unknown_origin')
    def priority(k):
        return (0 if 'label_conflict' in flags[k] else 1 if flags[k] & {'host_name_variation_candidate','curated_strain_mismatch'} else 2,k)
    for k in sorted(flags,key=priority)[:10]: chosen[k].update(flags[k])
    return [dict(phage=k[0],host=k[1],reasons=';'.join(sorted(v)),
                 phage_names=';'.join(sorted({r['phage_name'] for r in by_pair[k] if r['phage_name']})),
                 host_names=';'.join(sorted({r['host_name'] for r in by_pair[k] if r['host_name']})),
                 references=json.dumps([r['table']+':'+str(r['excel_row']) for r in by_pair[k]]),
                 upstream_references=json.dumps([r['table']+':'+str(r['excel_row']) for r in matches[k]]))
            for k,v in sorted(chosen.items())], [dict(phage=k[0],host=k[1],flags=sorted(v),
            host_names=sorted(names[k[1]])) for k,v in sorted(flags.items())]


def main():
    out = ROOT/'data/derived'
    out.mkdir(exist_ok=True)
    inventory, rows, upstream, sequences = collect_tables()
    for asset in json.loads((ROOT/'manifest.json').read_text()):
        path = ROOT/asset['path']
        if not path.is_file():
            continue
        if asset.get('source') == 'NGDC' and asset.get('kind') == 'gzip_fasta':
            folder = Path(urlparse(asset['url']).path).parent.name
            strain = folder.removeprefix('Klebsiella_pneumoniae_').split('_GWH')[0]
            strain = strain.removesuffix('_assembly').replace('_', '-')
            sequences.setdefault(strain, []).append(asset['path'])
        elif asset.get('source') == 'GenBase' and asset.get('kind') == 'fasta':
            with path.open() as stream:
                header = stream.readline()
            match = re.search(r'phage strain (\S+)', header, re.IGNORECASE)
            if match:
                name = re.sub(r'_\d+$', '', match.group(1))
                sequences.setdefault(name, []).append(asset['path'])
        elif asset.get('source') == 'NCBI' and asset.get('kind') == 'fasta':
            sequences.setdefault(asset['accession'], []).append(asset['path'])
    upstream_index = defaultdict(list)
    for r in upstream: upstream_index[pair(r)].append(r)
    matched = []
    for r in rows:
        matches = upstream_index[pair(r)] if all(pair(r)) else []
        r['upstream_exact_match'] = ';'.join(sorted({m['source'] for m in matches}))
        r['evidence'] = evidence_category(r)
        r['assay_reference'] = 'https://doi.org/10.1093/bib/bbae484' if r['experiment']=='2' else ''
        r['phage_sequence'] = ';'.join(sequences.get(accession_base(r['phage']),[]))
        r['host_sequence'] = ';'.join(sequences.get(accession_base(r['host']),[]))
        for m in matches:
            matched.append(dict(table=r['table'],excel_row=r['excel_row'],phage=r['phage'],host=r['host'],
                                label=r['label'],source=m['source'],upstream_table=m['table'],
                                upstream_row=m['excel_row'],upstream_label=m['label'],
                                label_relation='unknown' if r['label'] not in ('0','1') or m['label'] not in ('0','1') else
                                'agree' if r['label']==m['label'] else 'disagree'))
    columns = list(rows[0])
    write_csv(out/'pair_evidence.csv',rows,columns)
    write_csv(out/'upstream_matches.csv',matched,['table','excel_row','phage','host','label','source','upstream_table','upstream_row','upstream_label','label_relation'])
    tables = defaultdict(list)
    for r in rows: tables[r['table']].append(r)
    summary = [dict(table=t,experiment=v[0]['experiment'],labels=dict(Counter(r['label'] for r in v)),
                    exact=quality(v),version_normalized_diagnostic=quality(v,True),
                    both_sequence_ids_matched=sum(bool(r['phage_sequence'] and r['host_sequence']) for r in v),
                    upstream_matched_rows=sum(bool(r['upstream_exact_match']) for r in v),
                    pair_level_assays_verified=0) for t,v in sorted(tables.items())]
    json_out(out/'table_summary.json',summary)
    json_out(out/'table_inventory.json',inventory)
    curated = list(csv.DictReader((ROOT/'docs/PAIR_SOURCE_CHECKS.csv').open()))
    sample, flags = sample_pairs(rows,upstream,curated)
    write_csv(out/'diagnostic_sample.csv',sample,['phage','host','reasons','phage_names','host_names','references','upstream_references'])
    q = {e:dict(exact=quality([r for r in rows if r['experiment']==e]),
                version_normalized_diagnostic=quality([r for r in rows if r['experiment']==e],True)) for e in ('1','2')}
    q['flags'] = flags
    q['upstream_label_disagreements'] = [r for r in matched if r['label_relation']=='disagree']
    q['upstream_coverage'] = dict(PredPHI=dict(pair_rows=len(upstream),tables=sorted({r['table'] for r in upstream})),
        PhageHosts='host species annotation only; exact host accession mapping unavailable',
        PHISDetector='virus host-name catalog and separate genome list; exact pair mapping unavailable',
        MVP='no local pair table',NCBI='sequence records; no independent exact pair label table')
    json_out(out/'pair_quality.json',q)
    overlaps = []
    def role(t):
        return 'filename_provisional_train' if 'train' in t else 'filename_provisional_test' if 'test' in t else 'filename_provisional_external' if 'external' in t else 'reference_or_unspecified'
    for a,b in combinations(sorted(tables),2):
        for normalized in (False,True):
            ka = {pair(r,normalized) for r in tables[a] if all(pair(r))}
            kb = {pair(r,normalized) for r in tables[b] if all(pair(r))}
            overlaps.append(dict(table_a=a,table_b=b,key='version_normalized_diagnostic' if normalized else 'exact',
                                 unique_a=len(ka),unique_b=len(kb),shared_pairs=shared_pairs(tables[a],tables[b],normalized),
                                 role_a=role(a),role_b=role(b),role_evidence='filename only; not proof of leakage'))
    write_csv(out/'split_overlaps.csv',overlaps,['table_a','table_b','key','unique_a','unique_b','shared_pairs','role_a','role_b','role_evidence'])
    print(json.dumps(dict(tables=len(tables),rows=len(rows),experiment1=q['1']['exact'],experiment2=q['2']['exact'],sample_pairs=len(sample)),indent=2))


if __name__ == '__main__':
    main()
