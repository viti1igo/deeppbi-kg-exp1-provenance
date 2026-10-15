import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('apply_paper_audit', Path(__file__).resolve().parents[1] / 'apply_paper_audit.py')
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)


def pair(phage, host, level):
    return {'phage': phage, 'host': host, 'auto_level': level, 'phage_name': '', 'host_name': ''}


class ApplyTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(ap.parse('CP027541:nt; NC_018289.1:iso;  NC_1:+?'), {'CP027541': 'nt', 'NC_018289': 'iso', 'NC_1': '+?'})

    def test_strongest_result_wins_and_never_lowers(self):
        pairs = [pair('P1', 'H1', 'E1_annotation_strain'), pair('P1', 'H2', 'E2_isolation_strain'), pair('P2', 'H1', 'E0_annotation_coarse')]
        papers = [{'pmid': '1', 'tier': '1 mixed', 'checked_by': 'Axel', 'result_per_paired_host': 'H1:iso; H2:prophage'},
                  {'pmid': '2', 'tier': '3 random', 'checked_by': 'Claude (draft - to confirm)', 'result_per_paired_host': 'H1:+'}]
        links = {'P1': ['1', '2'], 'P2': ['2']}
        got = {(p['phage'], p['host']): lvl for p, lvl, _ in ap.apply(pairs, papers, links)}
        self.assertEqual(got['P1', 'H1'], 'E3_hostrange')          # + beats iso
        self.assertEqual(got['P1', 'H2'], 'E2_isolation_strain')   # prophage never lowers E2
        self.assertEqual(got['P2', 'H1'], 'E3_hostrange')
        confirmed = {(p['phage'], p['host']): lvl for p, lvl, _ in ap.apply(pairs, papers, links, confirmed_only=True)}
        self.assertEqual(confirmed['P1', 'H1'], 'E2_isolation_strain')   # Claude draft ignored
        self.assertEqual(confirmed['P2', 'H1'], 'E0_annotation_coarse')

    def test_unknown_codes_are_pending_not_applied(self):
        pairs = [pair('P', 'H', 'E0_annotation_coarse')]
        papers = [{'pmid': '1', 'tier': '1 mixed', 'checked_by': 'Axel', 'result_per_paired_host': 'H:check'}]
        applied = ap.apply(pairs, papers, {'P': ['1']})
        self.assertEqual(applied[0][1], 'E0_annotation_coarse')
        self.assertEqual(ap.summarise(applied)['pending_pairs'], 1)


if __name__ == '__main__':
    unittest.main()
