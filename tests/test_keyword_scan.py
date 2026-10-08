import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('keyword_scan', Path(__file__).resolve().parents[1]/'scripts/keyword_scan.py')
keyword_scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keyword_scan)


class KeywordScanTest(unittest.TestCase):
    def test_bibliography_dropped_and_variants_matched(self):
        xml = ('<body>Spot assays and a double agar overlay plaque assay; wet-laboratory work. '
               'In-vitro tests.</body><ref-list>plaque in vitro wet lab</ref-list>')
        hits = [k for k, _ in keyword_scan.scan(keyword_scan.plain_text(xml))]
        self.assertEqual(sorted(hits), ['in vitro', 'plaque', 'spot test/assay', 'wet-lab'])


if __name__ == '__main__':
    unittest.main()
