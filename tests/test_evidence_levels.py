import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('evidence_levels', Path(__file__).resolve().parents[1] / 'scripts/evidence_levels.py')
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

SYN = {'NZ_FNLM01000034': {'DSM44215', 'NRRLB24152'}, 'LIV': {'1326'}, 'FDA': {'FDAARGOS14'}, 'NEW': {'LEVINE1'}}


class EvidenceLevelsTest(unittest.TestCase):
    def test_relation_exact_synonym_and_prefix(self):
        rel = lambda claim, organism, host: ev.relation(claim, organism, host, SYN)
        self.assertEqual(rel('Gordonia westfalica NRRL B-24152', 'Gordonia westfalica', 'NZ_FNLM01000034'), 'same_strain')
        self.assertEqual(rel('Streptomyces lividans JI 1326', 'Streptomyces lividans 1326', 'LIV'), 'same_strain_prefix')
        # substring look-alikes must not match
        self.assertEqual(rel('Staphylococcus aureus 1', 'Staphylococcus aureus', 'FDA'), 'same_species_other_strain')
        self.assertEqual(rel('Salmonella enterica serovar Typhi Vi', 'Salmonella enterica', 'NEW'), 'same_species_other_strain')
        self.assertEqual(rel('Salmonella enterica', 'Salmonella enterica', 'NEW'), 'same_species')

    def test_prefix_match_limits(self):
        self.assertTrue(ev.prefix_match('JI1326', '1326'))
        self.assertFalse(ev.prefix_match('1', 'FDAARGOS1'))      # too short
        self.assertFalse(ev.prefix_match('VI', 'LEVINEVI'))       # no digit
        self.assertFalse(ev.prefix_match('A1326', '21326'))       # prefix not letters-only

    def test_grade_takes_strongest_same_strain_claim(self):
        claims = [('E1_annotation_strain', 'NCBI /host', 'Gordonia westfalica DSM 44215'),
                  ('E2_isolation_strain', 'PhagesDB isolation host', 'Gordonia westfalica NRRL B-24152')]
        level, basis, _ = ev.grade(claims, 'Gordonia westfalica', 'NZ_FNLM01000034', SYN)
        self.assertEqual(level, 'E2_isolation_strain')
        self.assertIn('PhagesDB', basis)
        self.assertEqual(ev.grade([('E2_isolation_strain', 'NCBI /lab_host', 'Gordonia westfalica')],
                                  'Gordonia westfalica', 'NZ_FNLM01000034', SYN)[0], 'E0_annotation_coarse')
        self.assertEqual(ev.grade([('E1_annotation_strain', 'NCBI /host', '')], 'X y', 'H', SYN)[0], 'U_unresolved')


if __name__ == '__main__':
    unittest.main()
