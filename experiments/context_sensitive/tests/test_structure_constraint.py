import unittest
from experiments.context_sensitive.zelda_experiment import tile_source, sat_instance
from experiments.context_sensitive.object_preprocessor import numeric_grid, constrain
from wfc_to_sat.ordinary_wfc import WFCModel
class StructureConstraintTest(unittest.TestCase):
 def test_offsets_are_units(self):
  s,rgba=tile_source(); g=numeric_grid(s); st={'classification':'structure','required':[{'dx':0,'dy':0,'tile':g[14][105]},{'dx':2,'dy':1,'tile':g[15][107]}]}; m=WFCModel.from_tile_grid(s); c,_,_=sat_instance(m,rgba,4,4); clauses=constrain(c,m,st,(0,0),4,4); self.assertEqual(len(clauses),2); self.assertTrue(all(len(x)==1 for x in clauses))
