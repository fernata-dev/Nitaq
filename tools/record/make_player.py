import json, sys
cast = json.load(open(sys.argv[1], encoding="utf-8"))
html = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#1b1f24;height:100%}
body{display:flex;align-items:flex-start;justify-content:center;padding:28px 0;box-sizing:border-box}
.win{background:#0d1117;border:1px solid #30363d;border-radius:12px;box-shadow:0 18px 50px rgba(0,0,0,.55);overflow:hidden}
.bar{height:34px;background:#161b22;border-bottom:1px solid #30363d;display:flex;align-items:center;padding:0 14px;gap:8px;
 font:12.5px "DejaVu Sans",sans-serif;color:#8b949e}
.dot{width:12px;height:12px;border-radius:50%}.title{margin-left:12px;white-space:nowrap}
.badge{margin-left:auto;background:#1f6feb33;color:#79c0ff;border:1px solid #1f6feb66;border-radius:999px;padding:2px 10px;font-size:11.5px}
.term{font:14px/19px "JetBrains Mono","DejaVu Sans Mono","DejaVu Sans",monospace;color:#c9d1d9;padding:12px 16px;
 width:calc(118ch + 2px);box-sizing:content-box;white-space:pre-wrap;word-break:break-all;overflow:hidden}
.term div{min-height:19px;direction:ltr;unicode-bidi:isolate}
.cursor{display:inline-block;width:.6em;background:#c9d1d9;animation:b 1s steps(1) infinite}@keyframes b{50%{opacity:0}}
.intro{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0d1117;
 color:#e6edf3;font:22px "DejaVu Sans",sans-serif;gap:14px;z-index:5}
.intro b{font-size:44px;letter-spacing:1px}.intro small{color:#8b949e;font-size:16px;max-width:900px;text-align:center;line-height:1.6}
</style></head><body>
<div class="win" id="win"><div class="bar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span>
<span class="dot" style="background:#27c93f"></span><span class="title" id="title"></span><span class="badge">REAL RECORDING · FAKE HOME</span></div>
<div class="term" id="term"></div></div>
<script>
const CAST = __CAST__;
const FG = {30:"#6e7681",31:"#ff7b72",32:"#3fb950",33:"#d29922",34:"#58a6ff",35:"#bc8cff",36:"#39c5cf",37:"#b1bac4",
            90:"#6e7681",91:"#ffa198",92:"#56d364",93:"#e3b341",94:"#79c0ff",95:"#d2a8ff",96:"#56d4dd",97:"#f0f6fc"};
const BRIGHT = {31:"#ffa198",32:"#56d364",33:"#e3b341",34:"#79c0ff",35:"#d2a8ff",36:"#56d4dd"};
let lines=[[]], col=0, st={fg:null,bold:false,dim:false}, esc="";
function sgr(params){const ps=params===""?[0]:params.split(";").map(Number);
  for(const p of ps){ if(p===0) st={fg:null,bold:false,dim:false}; else if(p===1) st.bold=true; else if(p===2) st.dim=true;
    else if(p===22){st.bold=false;st.dim=false} else if(p===39) st.fg=null; else if((p>=30&&p<=37)||(p>=90&&p<=97)) st.fg=p; }}
function put(ch){const L=lines[lines.length-1]; const cell={ch,fg:st.fg,bold:st.bold,dim:st.dim};
  if(col<L.length) L[col]=cell; else { while(L.length<col) L.push({ch:" "}); L.push(cell);} col++;}
function feed(s){for(const ch of s){
  if(esc){esc+=ch; if(esc.length===2&&ch!=="["){esc="";continue} if(/[A-Za-z~]/.test(ch)&&esc.length>2){const body=esc.slice(2,-1);
      if(ch==="m") sgr(body.replace("?","")); esc=""} continue}
  if(ch==="\x1b"){esc=ch;continue}
  if(ch==="\n"){lines.push([]);col=0;continue}
  if(ch==="\r"){col=0;continue}
  if(ch==="\b"){col=Math.max(0,col-1);continue}
  if(ch==="\t"){const n=8-(col%8);for(let i=0;i<n;i++)put(" ");continue}
  if(ch<" ")continue; put(ch);}}
function color(c){if(!c.fg) return c.bold?"#f0f6fc":(c.dim?"#8b949e":null); return (c.bold&&BRIGHT[c.fg])?BRIGHT[c.fg]:FG[c.fg];}
function renderLine(L){const d=document.createElement("div"); let cur=null,buf="";
  const flush=()=>{if(!buf)return; const sp=document.createElement("span"); sp.textContent=buf;
    if(cur){const c=color(cur); if(c) sp.style.color=c; if(cur.bold) sp.style.fontWeight="700"; if(cur.dim&&!cur.fg) sp.style.opacity=".8";} d.appendChild(sp); buf="";};
  for(const c of L){const k=c.fg+"|"+c.bold+"|"+c.dim; const ck=cur?cur.fg+"|"+cur.bold+"|"+cur.dim:null;
    if(k!==ck){flush(); cur=c} buf+=c.ch} flush(); return d;}
function render(rows, cursor){const T=document.getElementById("term"); T.textContent="";
  let view=lines; if(rows) view=lines.slice(-rows*2);
  view.forEach((L,i)=>{const d=renderLine(L); if(cursor&&i===view.length-1){const cu=document.createElement("span");cu.className="cursor";cu.textContent=" ";d.appendChild(cu)} T.appendChild(d)});
  if(rows){T.style.height=(rows*19)+"px"; T.scrollTop=T.scrollHeight;}}
function reset(){lines=[[]];col=0;st={fg:null,bold:false,dim:false};esc=""}
window.shot=function(a,b,maxLines,title){reset(); for(let i=CAST.marks[a].start;i<CAST.marks[b].end;i++) feed(CAST.events[i][2]);
  while(lines.length&&lines[lines.length-1].length===0) lines.pop();
  if(maxLines&&lines.length>maxLines){const n=lines.length-maxLines; lines=lines.slice(-maxLines);
    reset2(n)}
  document.getElementById("title").textContent=title; render(0,false);};
function reset2(n){const note=`⋮ ${n} earlier line(s) of this command's output not shown in this screenshot (full output: video / cast file)`;
  lines.unshift([...note].map(ch=>({ch,fg:90})));}
window.play=async function(){document.getElementById("title").textContent="nitaq — recorded "+CAST.meta.recorded_at;
  const intro=document.createElement("div");intro.className="intro";
  intro.innerHTML="<b>Nitaq</b><span>real terminal recording</span><small>Every command really ran in a pseudo-terminal in the build container on "+CAST.meta.recorded_at+
  ". HOME is a FAKE home with synthetic Claude Code and Gemini CLI configs (no real secrets, attacker = attacker@test.local). Only the typing is animated.</small>";
  document.body.appendChild(intro); await new Promise(r=>setTimeout(r,4200)); intro.remove();
  reset(); render(34,true); let prev=0;
  for(const [t,_,s] of CAST.events){const gap=Math.min(Math.max(t-prev,0),1.1); prev=t; if(gap>0.004) await new Promise(r=>setTimeout(r,gap*1000));
    feed(s); render(34,true);}
  await new Promise(r=>setTimeout(r,3500)); window.done=true;};
</script></body></html>"""
open(sys.argv[2], "w", encoding="utf-8").write(html.replace("__CAST__", json.dumps(cast, ensure_ascii=False)))
print("ok", len(cast["events"]))
