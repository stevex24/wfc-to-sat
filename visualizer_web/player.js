const canvas = document.querySelector('#board');
const ctx = canvas.getContext('2d');
const controls = Object.fromEntries(['status','back','play','forward','scrub','view','epf','fps','fpsValue','png','sequence'].map(id => [id, document.querySelector(`#${id}`)]));

class Replay {
  constructor(header, events, name) {
    this.header = header; this.events = events; this.name = name; this.cursor = 0;
    this.width = header.grid.width; this.height = header.grid.height;
    this.patterns = header.patterns.map((p, index) => ({...p, index, pixels: decode(p.rgba)}));
    this.byId = new Map(this.patterns.map(p => [p.id, p]));
    this.full = this.patterns.map(p => p.id);
    this.domains = Array.from({length: this.width * this.height}, () => this.full.slice());
    this.selected = Array(this.domains.length).fill(null); this.level = 0; this.trails = [[]];
    this.undo = []; this.conflicts = 0; this.restarts = 0; this.terminal = 'running'; this.stats = {};
    this.flash = new Set(); this.flashPower = 0;
    this.blendCache = new Map();
  }
  cell(x,y) { return y * this.width + x; }
  apply() {
    if (this.cursor >= this.events.length) return false;
    const event = this.events[this.cursor], type = event[0]; let undo = {type};
    if (type === 'l') { undo.level = this.level; this.level = event[1]; while (this.trails.length <= this.level) this.trails.push([]); }
    else if (type === 'p' || type === 'n') {
      const cell = this.cell(event[1], event[2]), oldDomain = this.domains[cell].slice(), oldSelected = this.selected[cell];
      const next = type === 'p' ? [event[3]] : oldDomain.filter(id => id !== event[3]);
      const nextSelected = type === 'p' ? event[3] : oldSelected;
      while (this.trails.length <= event[4]) this.trails.push([]);
      const record = {cell, oldDomain, oldSelected, newDomain: next.slice(), newSelected: nextSelected};
      this.trails[event[4]].push(record); this.domains[cell] = next; this.selected[cell] = nextSelected; undo.record = record; undo.level = event[4];
    } else if (type === 'b') {
      undo.oldLevel = this.level; undo.removed = [];
      this.flash = new Set();
      for (let level = this.level; level > event[1]; level--) {
        const records = this.trails[level].splice(0); undo.removed.push([level, records]);
        for (let i = records.length - 1; i >= 0; i--) { const r = records[i]; this.domains[r.cell] = r.oldDomain.slice(); this.selected[r.cell] = r.oldSelected; this.flash.add(r.cell); }
      }
      this.level = event[1]; this.conflicts++; this.flashPower = Math.min(1, .2 + Math.log2(event[2] + 1) / 10);
    } else if (type === 'r') { this.restarts++; }
    else if (type === 'e') { undo.terminal = this.terminal; undo.stats = this.stats; this.terminal = event[1]; this.stats = event[2] || {}; }
    this.undo[this.cursor] = undo; this.cursor++; return true;
  }
  back() {
    if (!this.cursor) return false; const index = --this.cursor, undo = this.undo[index], event = this.events[index];
    if (undo.type === 'l') this.level = undo.level;
    else if (undo.type === 'p' || undo.type === 'n') { const r = this.trails[undo.level].pop(); this.domains[r.cell] = r.oldDomain.slice(); this.selected[r.cell] = r.oldSelected; }
    else if (undo.type === 'b') { for (let i = undo.removed.length - 1; i >= 0; i--) { const [level, records] = undo.removed[i]; this.trails[level].push(...records); for (const r of records) { this.domains[r.cell] = r.newDomain.slice(); this.selected[r.cell] = r.newSelected; } } this.level = undo.oldLevel; this.conflicts--; this.flash.clear(); }
    else if (undo.type === 'r') this.restarts--;
    else if (undo.type === 'e') { this.terminal = undo.terminal; this.stats = undo.stats; }
    return true;
  }
  seek(fraction) { const target = Math.round(fraction * this.events.length); while (this.cursor < target) this.apply(); while (this.cursor > target) this.back(); }
}

function decode(encoded) { const raw = atob(encoded), bytes = new Uint8Array(raw.length); for (let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i); return bytes; }
async function loadTrace(index, name) {
  const response = await fetch(`/trace/${index}`), lines = await parseJsonl(response);
  if (!lines.length || lines[0].type !== 'header' || lines[0].version !== 1) throw new Error(`${name}: unsupported or missing trace header`);
  return new Replay(lines[0], lines.slice(1), name);
}
async function parseJsonl(response) { if(!response.ok)throw new Error(`trace request failed: ${response.status}`);const reader=response.body.getReader(),decoder=new TextDecoder();let pending='',records=[];for(;;){const {done,value}=await reader.read();pending+=decoder.decode(value||new Uint8Array(),{stream:!done});const parts=pending.split(/\r?\n/);pending=parts.pop();for(const line of parts)if(line.trim())records.push(JSON.parse(line));if(done)break;}if(pending.trim())records.push(JSON.parse(pending));return records; }

let replays = [], playing = false, lastTick = 0, exporting = false;
const config = await (await fetch('/config')).json();
try { replays = await Promise.all(config.traceNames.map((name, i) => loadTrace(i, name))); controls.sequence.hidden = !config.exportEnabled; controls.status.textContent = 'Ready'; }
catch (error) { controls.status.textContent = error.message; throw error; }

function resize() { const ratio = devicePixelRatio || 1, rect = canvas.getBoundingClientRect(); const w=Math.round(rect.width*ratio), h=Math.round(rect.height*ratio); if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;} render(); }
new ResizeObserver(resize).observe(canvas);

function render() {
  ctx.clearRect(0,0,canvas.width,canvas.height); ctx.fillStyle='#05080c'; ctx.fillRect(0,0,canvas.width,canvas.height);
  const gap = replays.length === 2 ? 26 : 0, panelWidth = (canvas.width - gap) / replays.length;
  replays.forEach((replay, i) => drawReplay(replay, i * (panelWidth + gap), 0, panelWidth, canvas.height));
  const progress = replays.reduce((n,r)=>n+r.cursor/r.events.length,0)/replays.length; controls.scrub.value = Math.round(progress*1000);
  controls.status.textContent = replays.map(r => { const exact=r.terminal!=='running'&&r.stats.conflicts!==undefined?` / exact ${r.stats.conflicts}`:''; return `${r.name}  ${r.cursor.toLocaleString()}/${r.events.length.toLocaleString()}  L${r.level}  conflicts* ${r.conflicts}${exact}  restarts ${r.restarts}  ${r.terminal.toUpperCase()}`; }).join('\n');
}

function drawReplay(r, px, py, pw, ph) {
  const titleH=38, pad=16, cell=Math.min((pw-pad*2)/r.width,(ph-titleH-pad*2)/r.height), ox=px+(pw-r.width*cell)/2, oy=py+titleH+(ph-titleH-r.height*cell)/2;
  ctx.fillStyle='#d9e8f8'; ctx.font=`${Math.max(13,canvas.width/90)}px ui-monospace, monospace`; ctx.textAlign='center'; ctx.fillText(`${r.name} · ${r.header.run.heuristic}`,px+pw/2,25);
  for(let y=0;y<r.height;y++) for(let x=0;x<r.width;x++){ const index=r.cell(x,y), domain=r.domains[index]; drawCell(r,domain,r.selected[index],ox+x*cell,oy+y*cell,cell); if(r.flash.has(index)){ctx.fillStyle=`rgba(255,70,45,${.55*r.flashPower})`;ctx.fillRect(ox+x*cell,oy+y*cell,cell,cell);} }
  r.flashPower*=.92; if(r.flashPower<.02)r.flash.clear();
}

function drawCell(r, domain, selected, x,y,size) {
  ctx.fillStyle='#0d141d'; ctx.fillRect(x,y,size,size);
  if (controls.view.value === 'entropy') { const t=(domain.length-1)/Math.max(1,r.patterns.length-1), hue=220-220*t; ctx.fillStyle=`hsl(${hue} 88% ${28+30*t}%)`; ctx.fillRect(x,y,size,size); }
  else if (controls.view.value === 'collapsed') { if(selected!==null||domain.length===1) drawPattern(r.byId.get(selected ?? domain[0]),x,y,size); }
  else if(domain.length) drawBlend(r,domain,x,y,size);
  ctx.strokeStyle='rgba(120,160,195,.16)';ctx.lineWidth=1;ctx.strokeRect(x+.5,y+.5,size-1,size-1);
}

function tileCanvas(pattern) { if(pattern.canvas)return pattern.canvas; const off=document.createElement('canvas');off.width=pattern.width;off.height=pattern.height;off.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(pattern.pixels),pattern.width,pattern.height),0,0);pattern.canvas=off;return off; }
function drawPattern(pattern,x,y,size) { if(!pattern)return;ctx.imageSmoothingEnabled=false;ctx.drawImage(tileCanvas(pattern),x,y,size,size); }
function drawBlend(r,domain,x,y,size) { const key=domain.join(','), cached=r.blendCache.get(key); if(cached){ctx.imageSmoothingEnabled=false;ctx.drawImage(cached,x,y,size,size);return;} const patterns=domain.map(id=>r.byId.get(id)), first=patterns[0], out=new Uint8ClampedArray(first.width*first.height*4); let total=patterns.reduce((n,p)=>n+p.frequency,0); for(let i=0;i<out.length;i++)out[i]=patterns.reduce((n,p)=>n+p.pixels[i]*p.frequency,0)/total; const tile=tileCanvas({...first,pixels:out});if(r.blendCache.size>=4096)r.blendCache.clear();r.blendCache.set(key,tile);ctx.imageSmoothingEnabled=false;ctx.drawImage(tile,x,y,size,size); }

function step(direction, count=1){ for(let n=0;n<count;n++) for(const replay of replays) direction>0?replay.apply():replay.back(); render(); }
controls.play.onclick=()=>{playing=!playing;controls.play.textContent=playing?'Pause':'Play';};
controls.back.onclick=()=>step(-1); controls.forward.onclick=()=>step(1); controls.view.onchange=render;
controls.scrub.oninput=()=>{playing=false;controls.play.textContent='Play'; const f=Number(controls.scrub.value)/1000;replays.forEach(r=>r.seek(f));render();};
controls.fps.oninput=()=>controls.fpsValue.value=controls.fps.value;
controls.png.onclick=()=>{const a=document.createElement('a');a.download='cdcl-frame.png';a.href=canvas.toDataURL('image/png');a.click();};
controls.sequence.onclick=async()=>{ if(exporting)return;exporting=true;playing=false;replays.forEach(r=>r.seek(0));let frame=0;while(replays.some(r=>r.cursor<r.events.length)){step(1,Math.max(1,Number(controls.epf.value)));const blob=await new Promise(ok=>canvas.toBlob(ok,'image/png'));await fetch(`/export/frame-${String(frame++).padStart(6,'0')}.png`,{method:'POST',body:blob});await new Promise(requestAnimationFrame);}exporting=false;controls.status.textContent=`Exported ${frame} frames`;};

function animate(time){ if(playing&&!exporting&&time-lastTick>=1000/Number(controls.fps.value)){step(1,Math.max(1,Number(controls.epf.value)));lastTick=time;if(replays.every(r=>r.cursor>=r.events.length)){playing=false;controls.play.textContent='Play';}}else render();requestAnimationFrame(animate); }
resize();requestAnimationFrame(animate);
