import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('ncbi_trace', Path(__file__).resolve().parents[1]/'scripts/ncbi_trace.py')
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)


def record(organism, strain=''):
    return {'organism': organism, 'quals': {'strain': strain} if strain else {}}


class NcbiTraceTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(n.host_level('Mycobacterium smegmatis mc2 155'), 'strain')
        self.assertEqual(n.host_level('Salmonella enterica subsp. enterica serovar Typhimurium'), 'species')
        self.assertEqual(n.host_level('Arthrobacter sp.'), 'genus')
        self.assertEqual(n.host_level(''), 'none')

    def test_agreement(self):
        mc2 = record('Mycolicibacterium smegmatis MC2 155', 'MC2 155')
        mkd8 = record('Mycolicibacterium smegmatis MKD8', 'MKD8')
        self.assertEqual(n.compare('Mycobacterium smegmatis mc2 155', mc2), 'same_strain')  # renamed genus
        self.assertEqual(n.compare('Mycobacterium smegmatis mc2 155', mkd8), 'same_species_other_strain')
        self.assertEqual(n.compare('Clostridium difficile', record('Clostridioides difficile R20291', 'R20291')), 'same_species')
        self.assertEqual(n.compare('E. coli K-12', record('Escherichia coli O157', 'O157')), 'same_species_other_strain')  # abbreviated genus
        self.assertEqual(n.compare('Brevibacillus laterosporus', record('Paenibacillus larvae')), 'different_genus')
        self.assertEqual(n.compare('', mkd8), 'not_comparable')


if __name__ == '__main__':
    unittest.main()
