"""Deterministic tile nominations; semantic labels are supplied by a human.

Coordinates are zero-based tile coordinates. IDs are Unicode tile codes from
zelda_experiment.tile_source (minus 0x1000), not independently extracted pixels.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math

_CACHE = {}

def edge_maps(source):
    """Return deterministic horizontal/vertical tile-transition maps."""
    g=numeric_grid(source); h,w=len(g),len(g[0])
    horizontal=[[(g[y][x]!=g[y][x+1]) for x in range(w-1)] for y in range(h)]
    vertical=[[(g[y][x]!=g[y+1][x]) for x in range(w)] for y in range(h-1)]
    return horizontal, vertical

def discover_edge_first(source, limit=20, min_size=3):
    """Discover bounded/nearly bounded rectangles from edges alone."""
    g=numeric_grid(source); h,w=len(g),len(g[0]); eh,ev=edge_maps(source); out=[]
    for hh in range(min_size,min(h,30)+1):
      for ww in range(min_size,min(w,40)+1):
       area=ww*hh
       for y in range(0,h-hh+1,max(1,hh//3)):
        for x in range(0,w-ww+1,max(1,ww//3)):
         vals=[]
         vals += [eh[y][k] for k in range(x,x+ww-1)] + [eh[y+hh-1][k] for k in range(x,x+ww-1)]
         vals += [ev[k][x] for k in range(y,y+hh-1)] + [ev[k][x+ww-1] for k in range(y,y+hh-1)]
         support=sum(vals)/len(vals); gaps=len(vals)-sum(vals)
         if support < .72 or gaps > max(3,len(vals)//5): continue
         inside=[g[yy][xx] for yy in range(y+1,y+hh-1) for xx in range(x+1,x+ww-1)]
         outside=[g[y-1][xx] for xx in range(x, x+ww) if y>0]+[g[y+hh][xx] for xx in range(x,x+ww) if y+hh<h]
         if not inside or not outside: continue
         contrast=1-sum(min(inside.count(t)/len(inside),outside.count(t)/len(outside)) for t in set(inside+outside))/2
         score=10*support+4*contrast+min(area,400)/80+math.log2(area)
         out.append(dict(width=ww,height=hh,source=[x,y],area=area,perimeter=len(vals),boundary_support=round(support,4),gaps=gaps,enclosure_score=round(score,4),score=round(score,4),contrast=round(contrast,4),mechanisms=['edge-first-region'],tiles=patch(g,x,y,ww,hh),occurrences=[[x,y]],count=1,contained_candidates=[]))
    out.sort(key=lambda c:(-c['enclosure_score'],c['source']))
    selected=[]
    for c in out:
      if any(abs(c['source'][0]-p['source'][0])<=2 and abs(c['source'][1]-p['source'][1])<=2 and abs(c['width']-p['width'])<=3 and abs(c['height']-p['height'])<=3 for p in selected): continue
      c['id']='edge-first-'+hashlib.sha256(json.dumps(c['tiles']).encode()).hexdigest()[:12]; selected.append(c)
      if len(selected)>=limit: break
    return selected


def numeric_grid(source):
    return [[ord(t) - 0x1000 for t in row] for row in source]


def patch(grid, x, y, w, h):
    return [list(row[x:x+w]) for row in grid[y:y+h]]


def occurrences(grid, tiles):
    h, w = len(tiles), len(tiles[0])
    return [[x, y] for y in range(len(grid)-h+1)
            for x in range(len(grid[0])-w+1) if patch(grid, x, y, w, h) == tiles]


def discover(source, limit=32):
    """Prefer bounded/grouped components; cap repeat evidence at 20 occurrences.

    Exclude the modal tile, flood-fill four-connected components, bound them to
    12x8, and group aligned components separated by <=2 ground tiles (max 12x8).
    Also nominate repeated 2x2/3x2/2x3/3x3 patches with >=3 distinct tile IDs.
    Rank by mechanism bonus + diversity + log repetition + small size bonus.
    Suppress contained patches with the same occurrence count; return <=limit.
    """
    cache_key = (tuple(source), limit)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    g = numeric_grid(source)
    height, width = len(g), len(g[0])
    ground = Counter(t for row in g for t in row).most_common(1)[0][0]
    seen, boxes, proposals = set(), [], {}

    def nominate(x, y, w, h, mechanism):
        tiles = patch(g, x, y, w, h)
        key = tuple(map(tuple, tiles))
        proposals.setdefault(key, set()).add(mechanism)

    for y in range(height):
        for x in range(width):
            if (x,y) in seen or g[y][x] == ground:
                continue
            pending, cells = [(x,y)], []
            seen.add((x,y))
            while pending:
                a,b = pending.pop()
                cells.append((a,b))
                for c,d in ((a-1,b),(a+1,b),(a,b-1),(a,b+1)):
                    if 0 <= c < width and 0 <= d < height and (c,d) not in seen and g[d][c] != ground:
                        seen.add((c,d)); pending.append((c,d))
            left, top = min(a for a,b in cells), min(b for a,b in cells)
            w,h = max(a for a,b in cells)-left+1, max(b for a,b in cells)-top+1
            if 2 <= w <= 12 and 2 <= h <= 8:
                boxes.append((left,top,w,h))
                nominate(left,top,w,h,'bounded-component')
                # Hierarchical growth: nominate progressively larger enclosing
                # neighborhoods around each component (deterministic radii).
                for radius in (2, 5, 10):
                    nx, ny = max(0,left-radius), max(0,top-radius)
                    nr = min(width, left+w+radius)-nx
                    nh = min(height, top+h+radius)-ny
                    if nr*nh <= 900 and len(boxes) <= 80:
                        nominate(nx,ny,nr,nh,'hierarchical-growth')
    aligned = defaultdict(list)
    for x,y,w,h in boxes:
        aligned[y,h].append((x,w))
    for (y,h), row in sorted(aligned.items()):
        row.sort()
        for i,(x,w) in enumerate(row):
            end = x+w
            for nx,nw in row[i+1:]:
                if not 0 <= nx-end <= 2 or nx+nw-x > 12:
                    break
                end = nx+nw
                nominate(x,y,end-x,h,'aligned-component-group')
    for w,h in ((2,2),(3,2),(2,3),(3,3)):
        counts = Counter(tuple(tuple(r[x:x+w]) for r in g[y:y+h])
                         for y in range(height-h+1) for x in range(width-w+1))
        for key,count in counts.items():
            if count >= 3 and len(set(t for r in key for t in r)) >= 3:
                proposals.setdefault(key,set()).add('repeated-patch')
    # Relationship-driven grouping: merge nearby aligned component envelopes.
    # The envelope is the natural stopping point; perimeter transition density
    # supplies an interpretable boundary score.
    edges_h, edges_v = edge_maps(source)
    for i,(x,y,w,h) in enumerate(boxes[:80]):
        for j,(xx,yy,ww,hh) in enumerate(boxes[i+1:80], i+1):
            gapx=max(xx-(x+w), x-(xx+ww), 0); gapy=max(yy-(y+h), y-(yy+hh), 0)
            aligned=(abs(y-yy)<=2 or abs((y+h)-(yy+hh))<=2 or abs(x-xx)<=2 or abs((x+w)-(xx+ww))<=2)
            if aligned and gapx+gapy<=5 and (max(xx+ww,x+w)-min(x,xx))*(max(yy+hh,y+h)-min(y,yy))<=500:
                lx,ty=min(x,xx),min(y,yy); rx,by=max(x+w,xx+ww),max(y+h,yy+hh)
                bw,bh=rx-lx,by-ty
                boundary=sum(edges_h[ty][k] for k in range(lx,min(rx-1,len(edges_h[ty])))) if ty<len(edges_h) else 0
                boundary+=sum(edges_h[by-1][k] for k in range(lx,min(rx-1,len(edges_h[by-1])))) if by-1<len(edges_h) else 0
                boundary+=sum(edges_v[k][lx] for k in range(ty,min(by-1,len(edges_v)))) if lx<len(edges_v[0]) else 0
                boundary+=sum(edges_v[k][rx-1] for k in range(ty,min(by-1,len(edges_v)))) if rx-1<len(edges_v[0]) else 0
                if boundary >= 4:
                    nominate(lx,ty,bw,bh,'structural-group')
    ranked = []
    # Build occurrence indices once per nominated size.
    indices = {}
    for key in proposals:
        h,w = len(key),len(key[0])
        if (w,h) not in indices:
            index = defaultdict(list)
            for y in range(height-h+1):
                for x in range(width-w+1):
                    index[tuple(tuple(r[x:x+w]) for r in g[y:y+h])].append([x,y])
            indices[w,h] = index
        locs = indices[w,h][key]
        mechanisms = sorted(proposals[key])
        diversity = len(set(t for r in key for t in r))
        bonus = 14 if 'structural-group' in mechanisms else 12 if 'aligned-component-group' in mechanisms else 10 if 'hierarchical-growth' in mechanisms else 8 if 'bounded-component' in mechanisms else 0
        score = bonus + diversity + 2*math.log2(min(len(locs),20)) + min(w*h,24)/12
        digest = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
        ranked.append(dict(id='candidate-'+digest, width=w, height=h, tiles=list(map(list,key)),
                           occurrences=locs, count=len(locs), source=locs[0], mechanisms=mechanisms,
                           score=round(score,4), distinct_tiles=diversity))
    ranked.sort(key=lambda c:(-c['score'],c['id']))
    selected = []
    # Keep at least one primitive from each mechanism so the shortlist spans scales.
    for mechanism in ('repeated-patch', 'bounded-component', 'aligned-component-group'):
        first = next((c for c in ranked if mechanism in c['mechanisms']), None)
        if first is not None:
            selected.append(first)
    for c in ranked:
        if c in selected:
            continue
        if any(c['count']==p['count'] and c['width']==p['width'] and c['height']==p['height']
               and occurrences(p['tiles'],c['tiles']) for p in selected):
            continue
        selected.append(c)
        if len(selected) >= limit:
            break
    _CACHE[cache_key] = selected
    return selected


def represent(candidate, source, classification='object', name=None, occurrence=0):
    if classification not in ('ignore','texture','object','region'):
        raise ValueError('unknown classification')
    g = numeric_grid(source)
    x,y = candidate['occurrences'][occurrence]
    w,h = candidate['width'],candidate['height']
    if patch(g,x,y,w,h) != candidate['tiles']:
        raise ValueError('candidate does not match source')
    content = [dict(dx=dx,dy=dy,tile=t) for dy,row in enumerate(candidate['tiles']) for dx,t in enumerate(row)]
    boundary = [dict(dx=dx,dy=dy,tile=g[y+dy][x+dx])
                for dy in range(-1,h+1) for dx in range(-1,w+1)
                if not (0<=dx<w and 0<=dy<h) and 0<=x+dx<len(g[0]) and 0<=y+dy<len(g)]
    required = content if classification=='object' else [t for t in content if t['dx'] in (0,w-1) or t['dy'] in (0,h-1)] if classification=='region' else []
    return dict(id=name or candidate['id'], candidate_id=candidate['id'], classification=classification,
                anchor='top-left of candidate rectangle; zero-based tiles', width=w,height=h,
                source=[x,y], required=required, boundary=boundary,
                boundary_policy='exact one-tile ring from chosen occurrence' if classification=='object' else 'no external ring constraint')


def constrain(cnf, model, structure, anchor, width, height):
    """Require one placement: unit clauses specialize object_at(anchor) => tiles.

    No extra SAT variables or observer changes. Boundary clipping is rejected.
    Existing exact-one and adjacency clauses continue to apply everywhere.
    """
    if structure['classification'] in ('ignore','texture'):
        return []
    tiles = structure['required'] + (structure['boundary'] if structure['classification']=='object' else [])
    tile_ids = {ord(t)-0x1000:i for i,t in enumerate(model.tiles)}
    clauses = []
    for item in tiles:
        x,y = anchor[0]+item['dx'],anchor[1]+item['dy']
        if not (0<=x<width and 0<=y<height):
            raise ValueError('entire object and available boundary must fit output')
        clauses.append([cnf.var_map[x,y,tile_ids[item['tile']]]])
    for clause in clauses:
        cnf.add_clause(clause)
    return clauses
