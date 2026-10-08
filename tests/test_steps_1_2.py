import importlib.util
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory = load('inventory')
membership = load('source_membership')


class StepsTest(unittest.TestCase):
    def test_inventory_counts_unique_pairs_and_split(self):
        row = lambda table, phage, host, label: {'table': f'x/{table}#ID', 'phage': phage, 'host': host,
                                                 'label': label, 'phage_name': 'P', 'host_name': 'H'}
        rows = [row('RF_all_sample.xlsx', 'P1', 'H1', '1'), row('key_gene_test_set.xlsx', 'P1', 'H1', '1'),
                row('external_PHI_final.xlsx', 'P2', 'H2', '0'), row('interaction_ref_infor.csv', 'P1', 'H1', '')]
        out = {(e['kind'], e['accession']): e for e in inventory.build(rows, {'H1': 'Bacillota'})}
        self.assertEqual(out['host', 'H1']['positive_pairs'], 1)          # two rows, one unique pair
        self.assertEqual(out['host', 'H1']['split'], 'train_test')
        self.assertEqual(out['host', 'H1']['phylum'], 'Bacillota')
        self.assertEqual(out['host', 'H2']['split'], 'external')
        self.assertEqual(out['host', 'H2']['in_host_phylum_info'], 'no')

    def test_wgs_prefix(self):
        self.assertEqual(membership.wgs_prefix('NZ_FNLM01000034.1'), 'FNLM01')
        self.assertEqual(membership.wgs_prefix('QUAI01000001'), 'QUAI01')
        self.assertEqual(membership.wgs_prefix('CP027541'), '')

    def test_same_species_handles_renames_and_sp(self):
        self.assertEqual(membership.same_species('Mycobacterium smegmatis mc2 155',
                                                 'Mycolicibacterium smegmatis MKD8 chromosome'), 'yes')
        self.assertEqual(membership.same_species('Synechococcus sp. WH7805', 'Synechococcus sp. PCC 6312'), 'no')
        self.assertEqual(membership.same_species('', 'Escherichia coli'), '')


if __name__ == '__main__':
    unittest.main()
