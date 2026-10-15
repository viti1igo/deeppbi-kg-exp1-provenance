import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('paper_audit', Path(__file__).resolve().parents[1] / 'paper_audit.py')
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)


def paper(pmid, pairs, mixed='no', pmc='PMC1', e0=1):
    return {'pmid': pmid, 'pairs': pairs, 'mixed': mixed, 'pmc': pmc, 'E0': e0}


class PaperAuditTest(unittest.TestCase):
    def test_tiers_are_disjoint_and_ordered(self):
        papers = [paper('m1', 50, 'yes')] + [paper(f'c{i}', 40 - i) for i in range(12)] + \
                 [paper(f'r{i}', 1) for i in range(40)] + [paper('pay', 1, pmc='')]
        tier, pool, sample = pa.select(sorted(papers, key=lambda r: -r['pairs']), [{'phage': 'p', 'host': 'h'}])
        self.assertEqual(tier['m1'], '1 mixed')
        self.assertEqual(sum(t == '2 coverage' for t in tier.values()), pa.TIER2)
        self.assertEqual(sum(t == '3 random' for t in tier.values()), pa.TIER3)
        self.assertNotIn('pay', {r['pmid'] for r in pool})            # random tier needs free full text
        self.assertTrue(all(tier.get(r['pmid']) in (None, '3 random') for r in pool))
        self.assertEqual(len(sample), 1)

    def test_selection_is_reproducible(self):
        papers = [paper(f'r{i}', 1) for i in range(60)]
        self.assertEqual(pa.select(papers, [])[0], pa.select(papers, [])[0])


if __name__ == '__main__':
    unittest.main()
