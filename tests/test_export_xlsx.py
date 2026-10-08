import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('export_xlsx', Path(__file__).resolve().parents[1] / 'scripts/export_xlsx.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


class ExportTest(unittest.TestCase):
    def test_column_letters(self):
        self.assertEqual([ex.col_letter(i) for i in (0, 25, 26, 27)], ['A', 'Z', 'AA', 'AB'])

    def test_cells_are_valid_xml(self):
        for value in ('a < b & "c"', 7, '', ('=HYPERLINK("https://x.org/?a=1&b=2","Paper")', 'Paper')):
            ET.fromstring(ex.cell('A1', value, 5))
        link = ET.fromstring(ex.cell('A1', ('=HYPERLINK("u","Paper")', 'Paper'), 3))
        self.assertEqual(link.findtext('v'), 'Paper')        # cached label shown without recalculation

    def test_styles_xml_well_formed(self):
        ET.fromstring(ex.styles().encode())


if __name__ == '__main__':
    unittest.main()
