import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('audit', Path(__file__).resolve().parents[1]/'scripts/audit.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def row(phage='NC_000001.1', host='CP000001', label='1', name='strain A', table='train'):
    return dict(phage=phage, host=host, label=label, host_name=name, phage_name='p',
                table=table, excel_row=2, experiment='1')


class AuditTests(unittest.TestCase):
    def test_quality_versions_missing_and_conflicts(self):
        rows = [row(), row(label='0'), row(phage='NC_000001.2'), row(host=''), row(label='')]
        q = a.quality(rows)
        self.assertEqual((q['rows'],q['unique_pairs'],q['duplicate_excess_rows'],q['conflicting_pairs']), (5,2,2,1))
        self.assertEqual((q['missing_identifiers'],q['invalid_or_missing_labels']), (1,1))
        self.assertEqual(a.quality(rows,True)['unique_pairs'],1)
        self.assertEqual(a.accession_base('KP.1'),'KP.1')
        self.assertEqual(a.accession_base('NZ_CP000001.2'),'NZ_CP000001')
        self.assertEqual(a.pair(row()),('NC_000001.1','CP000001'))
        self.assertNotEqual(a.pair(row()),a.pair(row(phage='NC_000001.2')))

    def test_sampling_deterministic_sources_and_flags(self):
        rows = [row(phage=f'NC_{i:06d}') for i in range(1,13)]
        rows += [row(phage='NC_000012',label='0',name='strain B',table='test')]
        upstream = [dict(r,source='PredPHI') for r in rows[:6]]
        chosen,flags = a.sample_pairs(rows,upstream,[])
        chosen2,flags2 = a.sample_pairs(list(reversed(rows)),upstream,[])
        self.assertEqual([(r['phage'],r['reasons']) for r in chosen],[(r['phage'],r['reasons']) for r in chosen2])
        self.assertEqual(flags,flags2)
        self.assertEqual(sum('positive_match_PredPHI' in r['reasons'] for r in chosen),5)
        self.assertEqual(sum('positive_unknown_origin' in r['reasons'] for r in chosen),5)
        self.assertTrue(any('label_conflict' in r['reasons'] for r in chosen))
        self.assertTrue(any('host_name_variation_candidate' in r['flags'] for r in flags))
        self.assertEqual(len({(r['phage'],r['host']) for r in chosen}),len(chosen))

    def test_overlap_and_no_unsupported_evidence(self):
        self.assertEqual(a.shared_pairs([row(),row()],[row(),row(host='other')]),1)
        self.assertEqual(a.shared_pairs([row()],[row(phage='NC_000001.2')]),0)
        self.assertEqual(a.shared_pairs([row()],[row(phage='NC_000001.2')],True),1)
        for label in ('0','1',''):
            r=dict(row(label=label), assay_reference='plaque assay', host_sequence='a.fasta')
            self.assertNotEqual(a.evidence_category(r),'direct_wetlab')
        self.assertEqual(a.evidence_category(dict(row(),experiment='2')),'dataset_assay_described_pair_unverified')

    def test_flag_sources_and_priority_cap(self):
        rows = [row(phage=f'NC_{i:06d}',host=f'CP{i:06d}') for i in range(100,110)]
        curated = [dict(phage_accession=r['phage'],host_accession=r['host'],relation_to_deeppbi_pair='different_host_strain') for r in rows]
        conflict = row(phage='NC_999999',host='CP999999')
        rows += [conflict, row(phage='NC_000001.1',host='CP000009'),row(phage='NC_000001.2',host='CP000009')]
        upstream = [dict(conflict,label='0',source='PredPHI')]
        chosen,flags=a.sample_pairs(rows,upstream,curated)
        flag_map={(r['phage'],r['host']):r['flags'] for r in flags}
        self.assertIn('label_conflict',flag_map[a.pair(conflict)])
        self.assertIn('curated_strain_mismatch',flag_map[('NC_000100','CP000100')])
        for version in ('1','2'):
            self.assertIn('accession_version_candidate',flag_map[('NC_000001.'+version,'CP000009')])
        # Positive selections are independent; inspect reasons to test the ten-flag cap.
        selected_flags={r['phage'] for r in chosen if any(x in r['reasons'] for x in ('label_conflict','curated_strain_mismatch','accession_version_candidate'))}
        self.assertEqual(selected_flags,{'NC_999999'} | {f'NC_{i:06d}' for i in range(100,109)})
        self.assertEqual(a.accession_base('123456.1'),'123456.1')

    def test_inventory_missing_sheet_and_label_without_prior_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'data/raw/fixture';folder.mkdir(parents=True)
            p=folder/'pairs.XLSX'
            ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="pairs" r:id="r1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>phage</t></is></c><c r="B1" t="inlineStr"><is><t>host</t></is></c></row><row r="7"><c r="A7" t="inlineStr"><is><t>NC_000001.2</t></is></c><c r="B7" t="inlineStr"><is><t>CP000001</t></is></c></row></sheetData></worksheet>')
            with zipfile.ZipFile(folder/'repository.zip','w') as z:
                z.writestr('fixture/phage/NC_000001.2.fasta','>NC_000001.2\nACGT\n')
            original=a.ROOT
            try:
                a.ROOT=root
                inventory,rows,upstream,sequences=a.collect_tables()
            finally:
                a.ROOT=original
            entry=next(r for r in inventory if r.get('sheet')=='pairs')
            self.assertEqual(entry['schema_gap'],'no_ID_sheet;missing_label_header')
            self.assertEqual(rows[0]['excel_row'],7)
            self.assertEqual(rows[0]['label'],'')
            self.assertEqual(list(sequences),['NC_000001'])
            self.assertFalse((root/'data/derived').exists())
            self.assertFalse((folder/'extracted').exists())

    def test_sparse_xlsx_rows_and_missing_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.xlsx'
            ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ID" r:id="r1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>phage</t></is></c></row><row r="7"><c r="A7" t="inlineStr"><is><t>NC_000001.2</t></is></c></row></sheetData></worksheet>')
            rows=list(a.id_rows(p))
            self.assertEqual(rows[1],{'A':'NC_000001.2','_excel_row':7})
            self.assertEqual(list(a.id_rows(p,'missing')),[])
        self.assertFalse(a.is_pair_header(['label','pred','prob']))
        self.assertTrue(a.is_pair_header(['phage','host']))
        parsed=a.canonical({'phage':'NC_000001','host':''},'t',7,'1')
        self.assertEqual(parsed['label'],'')
        self.assertEqual(a.quality([parsed])['missing_identifiers'],1)


if __name__ == '__main__':
    unittest.main()
