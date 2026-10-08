import importlib.util
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


syn = load('strain_synonyms')
pdb = load('phagesdb')
split_name = syn.load('ncbi_trace').split_name


class Step3Test(unittest.TestCase):
    def test_norm_collapses_collection_spellings(self):
        for spelling in ('NRRL B-24152', 'NRRL:B-24152', 'NRRL:B:24152', 'nrrl b 24152'):
            self.assertEqual(syn.norm(spelling), 'NRRLB24152')
        self.assertEqual(syn.norm('mc²155'), syn.norm('MC2 155'))
        self.assertEqual(syn.norm('personal::3612'), '3612')
        self.assertEqual(syn.norm('strain Kb2'), 'KB2')

    def test_strain_match_uses_synonym_group_only(self):
        groups = {'NZ_FNLM01000034': {'DSM44215', 'NRRLB24152'}}
        self.assertTrue(syn.strain_matches('Gordonia westfalica NRRL B-24152', 'NZ_FNLM01000034.1', groups, split_name))
        self.assertFalse(syn.strain_matches('Gordonia westfalica', 'NZ_FNLM01000034', groups, split_name))  # no strain
        self.assertFalse(syn.strain_matches('Gordonia westfalica ATCC 1', 'NZ_FNLM01000034', groups, split_name))
        self.assertFalse(syn.strain_matches('Gordonia westfalica NRRL B-24152', 'OTHER', groups, split_name))

    def test_species_of_prefers_species_rank(self):
        import xml.etree.ElementTree as ET
        strain = ET.fromstring('<Taxon><TaxId>9</TaxId><Rank>strain</Rank><ScientificName>X y K12</ScientificName>'
                               '<LineageEx><Taxon><TaxId>1</TaxId><Rank>genus</Rank><ScientificName>X</ScientificName></Taxon>'
                               '<Taxon><TaxId>5</TaxId><Rank>species</Rank><ScientificName>X y</ScientificName></Taxon>'
                               '</LineageEx></Taxon>')
        self.assertEqual(syn.species_of(strain), ('5', 'X y'))

    def test_phagesdb_helpers(self):
        self.assertEqual(pdb.base('KM101123.1'), 'KM101123')
        self.assertEqual(pdb.base(None), '')
        host = {'genus': 'Mycobacterium', 'species': 'smegmatis', 'strain_name': 'mc²155'}
        self.assertEqual(pdb.strain_text(host), 'Mycobacterium smegmatis mc²155')
        self.assertEqual(pdb.strain_text({}), '')


if __name__ == '__main__':
    unittest.main()
