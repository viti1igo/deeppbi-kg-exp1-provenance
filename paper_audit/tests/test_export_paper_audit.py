import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('epa', Path(__file__).resolve().parents[1] / 'export_paper_audit_xlsx.py')
epa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(epa)


class ExportPaperAuditTest(unittest.TestCase):
    def test_result_colour(self):
        self.assertEqual(epa.result_style('H1:nt; H2:+'), 8)          # lab test found
        self.assertEqual(epa.result_style('H1:-'), 8)
        self.assertEqual(epa.result_style('H1:nt; H2:+?'), 9)         # needs a decision
        self.assertEqual(epa.result_style('H1:unsearched'), 9)
        self.assertEqual(epa.result_style('H1:nt; H2:iso'), 5)


if __name__ == '__main__':
    unittest.main()
