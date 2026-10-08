import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ncbi_links', Path(__file__).resolve().parents[1] / 'scripts/ncbi_links.py')
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)

BIOSAMPLE = b'''<BioSampleSet><BioSample accession="SAMN1"><Attributes>
<Attribute attribute_name="strain" harmonized_name="strain">DSM 44215</Attribute>
<Attribute attribute_name="culture collection" harmonized_name="culture_collection">NRRL:B-24152</Attribute>
<Attribute attribute_name="lab host" harmonized_name="lab_host">Gordonia westfalica</Attribute>
</Attributes></BioSample></BioSampleSet>'''


class Step3bTest(unittest.TestCase):
    def test_parsers(self):
        with tempfile.TemporaryDirectory() as folder:
            xml, conv = Path(folder) / 'a.xml', Path(folder) / 'b.json'
            xml.write_bytes(BIOSAMPLE)
            conv.write_text(json.dumps({'records': [{'pmid': 1, 'pmcid': 'PMC9'}, {'pmid': 2}]}))
            sample = links.parse_biosamples([xml])['SAMN1']
            self.assertEqual(sample['strain'], 'DSM 44215')
            self.assertEqual(sample['culture_collection'], 'NRRL:B-24152')
            self.assertEqual(sample['lab_host'], 'Gordonia westfalica')
            self.assertEqual(links.parse_pmc([conv]), {'1': 'PMC9'})

    def test_cache_fetches_each_id_once(self):
        calls = []
        def fetch(chunk):
            calls.append(chunk)
            return json.dumps(chunk).encode(), 'json'
        parse = lambda paths: sorted(x for p in paths for x in json.loads(p.read_text()))
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(links.cached_batches(Path(folder), {'a', 'b', 'c'}, fetch, 2, parse), ['a', 'b', 'c'])
            self.assertEqual(links.cached_batches(Path(folder), {'a', 'b', 'c', 'd'}, fetch, 2, parse), ['a', 'b', 'c', 'd'])
        self.assertEqual(calls, [['a', 'b'], ['c'], ['d']])


if __name__ == '__main__':
    unittest.main()
