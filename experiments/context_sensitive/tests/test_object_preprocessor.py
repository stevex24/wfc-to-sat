import unittest
from experiments.context_sensitive.zelda_experiment import tile_source
from experiments.context_sensitive.object_preprocessor import discover, represent

class ObjectPreprocessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.source,_=tile_source()
    def test_deterministic_and_repeated(self):
        a=discover(self.source); self.assertEqual(a,discover(self.source)); self.assertTrue(any(c['count']>1 and c['width']*c['height']>1 for c in a))
    def test_occurrences_match_source(self):
        for c in discover(self.source,8):
            for x,y in c['occurrences'][:3]:
                self.assertEqual([list(r[x:x+c['width']]) for r in self.source[y:y+c['height']]], [[chr(0x1000+t) for t in r] for r in c['tiles']])
    def test_object_offsets_and_rejection(self):
        c=next(c for c in discover(self.source) if c['count']>1 and c['width']>2)
        obj=represent(c,self.source)
        self.assertEqual(len(obj['required']),c['width']*c['height']); self.assertEqual(obj['required'][0]['dx'],0); self.assertEqual(obj['required'][0]['dy'],0)
        bad=dict(c); bad['tiles']=[row[:] for row in c['tiles']]; bad['tiles'][0][0]^=1
        with self.assertRaises(ValueError): represent(bad,self.source)

if __name__=='__main__': unittest.main()
