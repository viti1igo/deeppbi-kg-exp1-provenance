#!/usr/bin/env python3
"""Export note/manual_check_all.csv to a formatted Excel workbook note/manual_check_all.xlsx (stdlib only).

Sheets: Pairs (frozen header and id columns, filters, coloured verdicts, verdict drop-down, clickable
links), Summary (live COUNTIF counts), Legend (levels and keywords). Rows already checked by hand in an
existing manual_check_all.xlsx (checked_by not "auto ..." or "Claude ...") are kept on re-export.
"""
import csv
import importlib.util
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'note/manual_check_all.csv'
OUT = ROOT / 'note/manual_check_all.xlsx'
LEVELS = ['E3_hostrange', 'E2_isolation_strain', 'E1_annotation_strain', 'E0_annotation_coarse', 'U_unresolved']
LEVEL_COLOURS = ['FF1E8449', 'FF82C785', 'FFFFE08A', 'FFF5B7A0', 'FFD9D9D9']   # E3 .. U
HAND = ['checked_by', 'checked_on', 'verdict', 'method_seen', 'host_strain_seen', 'evidence_url', 'evidence_quote', 'notes']
LINKS = [('open_phage_ncbi', 'Phage NCBI'), ('open_host_ncbi', 'Host NCBI'), ('open_phagesdb', 'PhagesDB'), ('first_paper', 'Paper')]
# (column, header, width, style) in display order; style: 2 wrap, 3 link, 4 verdict, 5 plain
COLUMNS = [('id', 'ID', 7, 5), ('verdict', 'Verdict (choose)', 22, 4), ('checked_by', 'Checked by', 16, 5),
           ('checked_on', 'Checked on', 12, 5), ('auto_level', 'Auto level', 20, 5), ('auto_basis', 'Auto basis', 40, 5),
           ('flags', 'Flags', 28, 5), ('phage', 'Phage', 13, 5), ('phage_name', 'Phage name', 34, 5),
           ('host', 'Host', 17, 5), ('host_name', 'Host name', 38, 5), ('split', 'Set', 11, 5),
           ('sources_listing_pair', 'Sources listing pair', 22, 5), ('ncbi_host', 'NCBI /host', 28, 5),
           ('ncbi_lab_host', 'NCBI /lab_host', 28, 5), ('phagesdb_isolation_host', 'PhagesDB isolation host', 28, 5),
           ('phagesdb_verified_hosts', 'PhagesDB verified hosts', 22, 5),
           ('open_phage_ncbi', 'Phage NCBI', 11, 3), ('open_host_ncbi', 'Host NCBI', 11, 3),
           ('open_phagesdb', 'PhagesDB', 11, 3), ('first_paper', 'Paper', 9, 3), ('open_papers', 'All paper links', 30, 5),
           ('method_seen', 'Method seen', 26, 5), ('host_strain_seen', 'Host strain seen', 26, 5),
           ('evidence_url', 'Evidence URL', 30, 5), ('evidence_quote', 'Evidence quote', 40, 2), ('notes', 'Notes', 45, 2)]

STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="{nfills}"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
{level_fills}</fills>
<borders count="2"><border/><border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right>
<top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="{nxfs}"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>
{level_xfs}</cellXfs>
<dxfs count="{nlevels}">{dxfs}</dxfs>
</styleSheet>'''


def styles():
    fills = ''.join(f'<fill><patternFill patternType="solid"><fgColor rgb="{c}"/><bgColor indexed="64"/></patternFill></fill>'
                    for c in LEVEL_COLOURS)
    xfs = ''.join(f'<xf numFmtId="0" fontId="3" fillId="{3 + i}" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
                  for i in range(len(LEVELS)))
    dxfs = ''.join(f'<dxf><font><b/></font><fill><patternFill patternType="solid"><bgColor rgb="{c}"/></patternFill></fill></dxf>'
                   for c in LEVEL_COLOURS)
    return STYLES.format(nfills=3 + len(LEVELS), level_fills=fills, nxfs=7 + len(LEVELS),
                         level_xfs=xfs, nlevels=len(LEVELS), dxfs=dxfs)


def col_letter(index):
    letters = ''
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def cell(ref, value, style):
    if value is None or value == '':
        return f'<c r="{ref}" s="{style}"/>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    if isinstance(value, tuple):   # (formula, cached text) so viewers that do not recalculate still show the label
        return f'<c r="{ref}" t="str" s="{style}"><f>{escape(value[0][1:])}</f><v>{escape(value[1])}</v></c>'
    if isinstance(value, str) and value.startswith('='):
        return f'<c r="{ref}" s="{style}"><f>{escape(value[1:])}</f></c>'
    return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


def sheet(rows, widths, extra='', views=''):
    cols = ''.join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    body = ''.join(f'<row r="{r + 1}">' + ''.join(cell(f'{col_letter(c)}{r + 1}', v, s) for c, (v, s) in enumerate(row))
                   + '</row>' for r, row in enumerate(rows))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheetViews><sheetView workbookViewId="0">{views}</sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{body}</sheetData>{extra}</worksheet>')


def previous_hand_rows():
    """Rows the user already checked in an existing workbook, keyed by (phage, host)."""
    if not OUT.exists():
        return {}
    spec = importlib.util.spec_from_file_location('audit', ROOT / 'scripts/audit.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    rows = list(audit.id_rows(OUT, 'Pairs'))
    letter = {v: k for k, v in rows[0].items() if k != '_excel_row'}
    header = {h: key for key, h, _, _ in COLUMNS}
    kept = {}
    for r in rows[1:]:
        rec = {header[h]: r.get(letter[h], '') for h in letter if h in header}
        if rec.get('checked_by') and not rec['checked_by'].startswith(('auto', 'Claude')):
            kept[rec['phage'], rec['host']] = rec
    return kept


def main():
    with SRC.open(newline='') as stream:
        records = list(csv.DictReader(stream))
    kept = previous_hand_rows()
    for r in records:
        if (r['phage'], r['host']) in kept:
            for f in HAND:
                r[f] = kept[r['phage'], r['host']].get(f, r[f])
        papers = r['open_papers'].split()
        r['first_paper'] = papers[0] if papers else ''

    level_style = {lvl: 7 + i for i, lvl in enumerate(LEVELS)}
    n = len(records)
    rows = [[(h, 1) for _, h, _, _ in COLUMNS]]
    for r in records:
        row = []
        for key, _, _, style in COLUMNS:
            value = r.get(key, '')
            if key == 'id':
                value = int(value)
            elif key in dict(LINKS) and value:
                value = (f'=HYPERLINK("{value}","{dict(LINKS)[key]}")', dict(LINKS)[key])
            elif key == 'auto_level':
                style = level_style.get(value, style)
            row.append((value, style))
        rows.append(row)
    last = col_letter(len(COLUMNS) - 1)
    vcol = col_letter([c[0] for c in COLUMNS].index('verdict'))
    rules = ''.join(f'<cfRule type="containsText" dxfId="{i}" priority="{i + 1}" operator="containsText" text="{lvl[:2]}">'
                    f'<formula>NOT(ISERROR(SEARCH("{lvl[:2]}",{vcol}2)))</formula></cfRule>' for i, lvl in enumerate(LEVELS))
    extra = (f'<autoFilter ref="A1:{last}{n + 1}"/>'
             f'<conditionalFormatting sqref="{vcol}2:{vcol}{n + 1}">{rules}</conditionalFormatting>'
             f'<dataValidations count="1"><dataValidation type="list" allowBlank="1" showErrorMessage="1" '
             f'errorTitle="Verdict" error="Choose a level from the list." sqref="{vcol}2:{vcol}{n + 1}">'
             f'<formula1>"{",".join(LEVELS)}"</formula1></dataValidation></dataValidations>')
    views = '<pane xSplit="2" ySplit="1" topLeftCell="C2" activePane="bottomRight" state="frozen"/>'
    pairs = sheet(rows, [w for _, _, w, _ in COLUMNS], extra, views)

    rng = lambda col: f'Pairs!{col}2:{col}{n + 1}'
    acol = col_letter([c[0] for c in COLUMNS].index('auto_level'))
    ccol = col_letter([c[0] for c in COLUMNS].index('checked_by'))
    summary_rows = [[('Level', 1), ('Current verdict (live)', 1), ('Auto level (fixed)', 1), ('Meaning', 1)]]
    meanings = ['Lab host-range test on the exact strain', 'Isolated / propagated on the exact strain',
                'Exact strain named, no method', 'Species/genus only, or another strain', 'No host information']
    for i, lvl in enumerate(LEVELS):
        summary_rows.append([(lvl, 7 + i), (f'=COUNTIF({rng(vcol)},"{lvl}")', 5),
                             (f'=COUNTIF({rng(acol)},"{lvl}")', 5), (meanings[i], 2)])
    summary_rows += [[('Total', 6), (f'=SUM(B2:B{len(LEVELS) + 1})', 6), (f'=SUM(C2:C{len(LEVELS) + 1})', 6), ('', 0)],
                     [('', 0)] * 4,
                     [('Rows checked by hand', 6),
                      (f'=COUNTA({rng(ccol)})-COUNTIF({rng(ccol)},"auto*")-COUNTIF({rng(ccol)},"Claude*")', 5), ('', 0),
                      ('checked_by not starting with "auto" or "Claude"', 2)],
                     [('Rows still to check', 6), (f'={n}-B{len(LEVELS) + 4}', 5), ('', 0), ('', 0)]]
    summary = sheet(summary_rows, [26, 22, 20, 46])

    legend_rows = [[('Level', 1), ('Use when', 1), ('Keywords (with the exact strain code)', 1)],
                   [(LEVELS[0], 7), ('A source reports a lab test of this phage on this exact host strain (or a synonym)', 2),
                    ('host range, spot test, plaque assay, efficiency of plating (EOP), lysis, susceptible, double agar overlay; result + or −', 2)],
                   [(LEVELS[1], 8), ('Phage was isolated or propagated on this exact strain; no host-range test', 2),
                    ('isolated on, enrichment, direct plating, propagated on, lab_host, single plaque, PhagesDB Isolation Host', 2)],
                   [(LEVELS[2], 9), ('A record names this exact strain as host, with no method (incl. prophage in its genome)', 2),
                    ('NCBI /host, prophage, induced, mitomycin C, temperate, lysogen', 2)],
                   [(LEVELS[3], 10), ('Only species or genus, or a different strain than the one DeepPBI-KG pairs', 2),
                    ('species name only, "sp.", serotype only, another strain code', 2)],
                   [(LEVELS[4], 11), ('No host information found', 2), ('Direct Submission only, no /host, no paper', 2)],
                   [('', 0)] * 3,
                   [('How to check', 6), ('1. Search the paired host strain code (and synonyms in data/derived/strain_synonyms.csv). '
                     '2. Read the sentence/table where it appears. 3. Choose the verdict, fill Method seen, Host strain seen, '
                     'Evidence URL/quote, Checked by. A tested negative (−): keep E3 and write TESTED NEGATIVE in Notes.', 2), ('', 0)],
                   [('Traps', 6), ('"Escherichia phage X" (name only); "isolated from sewage" (sample, not host); predicted / in silico / '
                     'CRISPR match; "lytic" alone; "induced from strain X" is prophage, not infection.', 2), ('', 0)],
                   [('Guide', 6), ('note/MANUAL_CHECK.md; report note/REPORT.md', 2), ('', 0)]]
    legend = sheet(legend_rows, [24, 60, 70])

    sheets = [('Pairs', pairs), ('Summary', summary), ('Legend', legend)]
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + ''.join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                             'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(len(sheets))) + '</Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                   'Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + ''.join(f'<sheet name="{name}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, (name, _) in enumerate(sheets))
                   + '</sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
                   f"'Pairs'!$A$1:${last}${n + 1}</definedName></definedNames>"
                   '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                             f'Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                   'Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml', styles())
        for i, (_, xml) in enumerate(sheets):
            z.writestr(f'xl/worksheets/sheet{i + 1}.xml', xml)
    print(f'{n} rows -> {OUT} ({len(kept)} hand-checked rows kept from the previous workbook)')


if __name__ == '__main__':
    main()
