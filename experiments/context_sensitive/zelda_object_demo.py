"""Run the small Zelda object-preprocessor demonstration.

Outputs are deliberately isolated in context-sensitive-results/object-preprocessor.
"""
import argparse, base64, html, json, sys
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from experiments.context_sensitive.zelda_experiment import tile_source, sat_instance
from experiments.context_sensitive.object_preprocessor import discover, discover_edge_first, represent, constrain, edge_maps
from wfc_to_sat.ordinary_wfc import WFCModel

OUT = ROOT / "context-sensitive-results/object-preprocessor"

def solve(cnf, structure=None, anchor=(2,2), width=12, height=12):
    if structure: constrain(cnf, MODEL, structure, anchor, width, height)
    from pysat.solvers import Cadical195
    with Cadical195(bootstrap_with=cnf.clauses) as solver:
        sat = solver.solve(); assignment = solver.get_model() if sat else []
    positive = {v for v in assignment if v > 0}
    out=[]
    for y in range(height):
        row=[]
        for x in range(width):
            ids=[p for (xx,yy,p),v in cnf.var_map.items() if xx==x and yy==y and v in positive]
            row.append(TILE_FOR_ID[ids[0]] if ids else "?")
        out.append("".join(row))
    return out, sat

def render(rows, rgba, path):
    im=Image.new("RGBA", (len(rows[0])*16,len(rows)*16))
    for y,row in enumerate(rows):
        for x,t in enumerate(row): im.paste(Image.frombytes("RGBA",(16,16),rgba[ord(t)-0x1000]),(x*16,y*16))
    im.save(path)

def main(argv=None):
    global MODEL, TILE_FOR_ID
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=12); args=ap.parse_args(argv)
    source,rgba=tile_source(); MODEL=WFCModel.from_tile_grid(source); TILE_FOR_ID={i:t for i,t in enumerate(MODEL.tiles)}
    candidates=discover(source,args.limit); edge_candidates=discover_edge_first(source,20)
    for c in edge_candidates: c['contained_candidates']=[p['id'] for p in candidates if p['source'][0]>=c['source'][0] and p['source'][1]>=c['source'][1] and p['source'][0]+p['width']<=c['source'][0]+c['width'] and p['source'][1]+p['height']<=c['source'][1]+c['height']]
    candidates += edge_candidates
    chosen=represent(candidates[0],source,"object",name="zelda-object-0")
    OUT.mkdir(parents=True,exist_ok=True)
    source_img=Image.open(ROOT/"examples/context-sensitive/zelda-map-authors.png").convert("RGBA")
    source_img.save(OUT/"source-map.png")
    eh,ev=edge_maps(source); em=Image.new("RGB",(len(source[0]),len(source)),"white"); px=em.load()
    for y,row in enumerate(eh):
        for x,v in enumerate(row):
            if v: px[x,y]=(20,20,20)
    em.resize((len(source[0])*4,len(source)*4)).save(OUT/"edge-map.png")
    for i,c in enumerate(candidates):
        x,y=c["source"]; w,h=c["width"],c["height"]
        source_img.crop((x*16,y*16,(x+w)*16,(y+h)*16)).save(OUT/f"candidate-{i}-crop.png")
        source_img.crop((max(0,x-2)*16,max(0,y-2)*16,min(len(source[0]),x+w+2)*16,min(len(source),y+h+2)*16)).save(OUT/f"candidate-{i}-context.png")
    (OUT/"candidates.json").write_text(json.dumps(candidates,indent=2)+"\n")
    (OUT/"selections.json").write_text(json.dumps({"selections":[chosen]},indent=2)+"\n")
    cnf,mapping,_=sat_instance(MODEL,rgba,width=12,height=12)
    before,sat_before=solve(cnf)
    cnf2,mapping2,_=sat_instance(MODEL,rgba,width=12,height=12)
    after,sat_after=solve(cnf2,chosen,anchor=(2,2))
    (OUT/"before.png").unlink(missing_ok=True); render(before,rgba,OUT/"before.png"); render(after,rgba,OUT/"after.png")
    result={"candidate_count":len(candidates),"selected":chosen["id"],"selected_occurrences":candidates[0]["occurrences"],"before_sat":sat_before,"after_sat":sat_after,"anchor":[2,2],"preserved":all(after[2+q["dy"]][2+q["dx"]]==chr(0x1000+q["tile"]) for q in chosen["required"])}
    (OUT/"results.json").write_text(json.dumps(result,indent=2)+"\n")
    cards=[]
    for c in candidates:
        tile_text = "\n".join(" ".join(f"{t:02x}" for t in row) for row in c["tiles"])
        cards.append(f'<article><h3>#{len(cards)+1} {c["id"]}</h3><p>{c["width"]}×{c["height"]}; {c["count"]} occurrences; score {c["score"]}; mechanisms: {html.escape(", ".join(c["mechanisms"]))}</p><p>source: {c["source"]}; locations: {c["occurrences"]}</p><img src="candidate-{len(cards)}-crop.png"><img src="candidate-{len(cards)}-context.png"><pre>{tile_text}</pre></article>')
    counts={m:sum(m in c['mechanisms'] for c in candidates) for m in ('repeated-patch','bounded-component','aligned-component-group','hierarchical-growth','structural-group','edge-first-region')}
    (OUT/"results.json").write_text(json.dumps({"candidate_count":len(candidates),"mechanism_counts":counts,"new_structural_dimensions":[[c['width'],c['height']] for c in candidates if 'structural-group' in c['mechanisms']]},indent=2)+"\n")
    (OUT/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>Zelda object preprocessing</title><style>body{font:15px system-ui;margin:2rem}article{border:1px solid #ccd;padding:1rem;margin:.7rem;display:inline-block;vertical-align:top;max-width:440px}pre{font-size:11px;overflow:auto}img{image-rendering:pixelated;max-width:200px;max-height:180px;margin:3px} .map{max-width:900px}</style><h1>Zelda multi-scale candidate discovery</h1><p>Structural groups use aligned nearby components and explicit tile-transition edges; the envelope is the stopping boundary. Human labels decide semantics.</p><p><img class="map" src="source-map.png"><img class="map" src="edge-map.png"></p><p><img src="before.png"><img src="after.png"></p><p>Results: <a href="results.json">results.json</a>; editable selection: <a href="selections.json">selections.json</a>.</p>'+''.join(cards))
    print(json.dumps(result,indent=2))
if __name__ == "__main__": main()
