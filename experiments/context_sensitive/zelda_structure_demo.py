import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from collections import Counter
from PIL import Image
from experiments.context_sensitive.zelda_experiment import tile_source, sat_instance
from experiments.context_sensitive.object_preprocessor import numeric_grid, constrain
from wfc_to_sat.ordinary_wfc import WFCModel
OUT=ROOT/'context-sensitive-results/object-preprocessor/structure-demo'
def main():
 s,rgba=tile_source(); x,y,w,h=105,14,25,15; g=numeric_grid(s); bg=Counter(v for row in g[y:y+h] for v in row[x:x+w]).most_common(1)[0][0]
 req=[{'dx':i,'dy':j,'tile':g[y+j][x+i]} for j in range(h) for i in range(w) if g[y+j][x+i]!=bg]
 structure={'id':'pawn-bookends-human','classification':'structure','anchor':'top-left','width':w,'height':h,'source':[x,y],'required':req,'components':3,'background_tile':bg,'mechanism':'Human-added candidate'}
 model=WFCModel.from_tile_grid(s); cnf,mapping,tfi=sat_instance(model,rgba,30,20); anchor=(0,0); constrain(cnf,model,structure,anchor,30,20)
 from pysat.solvers import Cadical195
 with Cadical195(bootstrap_with=cnf.clauses) as sol: sat=sol.solve(); assignment=sol.get_model() if sat else []
 pos=set(v for v in assignment if v>0); out=[]
 for yy in range(20):
  row=[]
  for xx in range(30):
   ids=[p for (a,b,p),v in cnf.var_map.items() if a==xx and b==yy and v in pos]; row.append(tfi[ids[0]] if ids else '?')
  out.append(''.join(row))
 verified=sat and all(out[anchor[1]+q['dy']][anchor[0]+q['dx']]==chr(4096+q['tile']) for q in req)
 OUT.mkdir(parents=True,exist_ok=True); (OUT/'structure.json').write_text(json.dumps(structure,indent=2)+'\n'); (OUT/'verification.json').write_text(json.dumps({'sat':sat,'verified':verified,'required_offsets':len(req),'anchor':anchor},indent=2)+'\n')
 im=Image.new('RGBA',(30*16,20*16))
 for yy,row in enumerate(out):
  for xx,t in enumerate(row): im.paste(Image.frombytes('RGBA',(16,16),rgba[ord(t)-4096]),(xx*16,yy*16))
 im.save(OUT/'generated.png')
 print(json.dumps({'sat':sat,'verified':verified,'required_offsets':len(req)}))
if __name__=='__main__': main()
