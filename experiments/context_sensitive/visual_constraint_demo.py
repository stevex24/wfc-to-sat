"""Run SAT from a visually saved demo selection JSON."""
import argparse,json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from experiments.context_sensitive.zelda_experiment import tile_source,sat_instance
from experiments.context_sensitive.object_preprocessor import numeric_grid,constrain
from wfc_to_sat.ordinary_wfc import WFCModel
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--selection',required=True); a=ap.parse_args(); d=json.loads(Path(a.selection).read_text()); s,rgba=tile_source(); g=numeric_grid(s); model=WFCModel.from_tile_grid(s); w,h=30,20; cnf,_,tfi=sat_instance(model,rgba,w,h); req=[]
 for r in d.get('components', [d.get('area')]):
  if not r: continue
  x,y,ww,hh=r['x'],r['y'],r['width'],r['height']
  for j in range(hh):
   for i in range(ww):
    if g[y+j][x+i]!=d.get('background_tile',0): req.append({'dx':x+i-d['components'][0]['x'],'dy':y+j-d['components'][0]['y'],'tile':g[y+j][x+i]})
 st={'classification':d['semantic'],'required':req,'boundary':[]}; constrain(cnf,model,st,(0,0),w,h)
 from pysat.solvers import Cadical195
 with Cadical195(bootstrap_with=cnf.clauses) as sol: sat=sol.solve(); vals=set(v for v in (sol.get_model() if sat else []) if v>0)
 out=[]
 for y in range(h): out.append(''.join(tfi[next(p for (x,y2,p),v in cnf.var_map.items() if x==xx and y2==y and v in vals)] for xx in range(w)))
 verified=sat and all(out[q['dy']][q['dx']]==chr(4096+q['tile']) for q in req); outdir=Path(d.get('output','context-sensitive-results/object-preprocessor/visual-demo')); outdir.mkdir(parents=True,exist_ok=True); (outdir/'verification.json').write_text(json.dumps({'sat':sat,'verified':verified,'required_offsets':len(req)},indent=2)+'\n'); print(json.dumps({'sat':sat,'verified':verified,'required_offsets':len(req)}))
if __name__=='__main__': main()
