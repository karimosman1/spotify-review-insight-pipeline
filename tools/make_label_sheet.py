"""Build tools/label_golden.html: an offline page for hand-labeling data/golden_50_to_label.csv.

  python3 tools/make_label_sheet.py && open tools/label_golden.html

Labels autosave in the browser. "Export CSV" downloads golden_50_labeled.csv; save it to data/.
No model is involved: these are the human reference labels and must never be sent to a model.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = list(csv.DictReader((ROOT / "data/golden_50_to_label.csv").open(encoding="utf-8")))
data = [{k: r[k] for k in ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")}
        for r in rows]

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Golden 50 Labeling</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--acc:#1f6f5c;--warn:#a33;--ok:#1f6f5c;--chip:#eef3f1}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--mute:#a09f98;--line:#33332f;--acc:#5fbfa4;--warn:#e07a7a;--ok:#5fbfa4;--chip:#23302c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0;flex:1 1 auto}.bar{flex:1 1 200px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:var(--acc)}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 12px;border-radius:6px;cursor:pointer}button.pri{background:var(--acc);color:#fff;border-color:var(--acc)}
main{max-width:1200px;margin:0 auto;padding:16px;display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:16px}
@media (max-width:900px){main{grid-template-columns:1fr}aside{order:-1;position:static;max-height:30vh}}
aside{position:sticky;top:64px;align-self:start;max-height:calc(100vh - 80px);overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;font-size:13px}
aside h3{margin:10px 0 4px;font-size:13px}aside dt{font-weight:600}aside dd{margin:0 0 6px;color:var(--mute)}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:12px}
.card.done{border-left:4px solid var(--ok)}.meta{color:var(--mute);font-size:12px;margin-bottom:6px}
.text{white-space:pre-wrap;margin:0 0 10px;font-size:15px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
label{font-size:12px;color:var(--mute);display:block}select,input[type=text]{width:100%;font:inherit;padding:5px;border:1px solid var(--line);border-radius:5px;background:var(--bg);color:var(--ink)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}@media (max-width:600px){.row2{grid-template-columns:1fr}}
.q-bad{color:var(--warn);font-size:12px}.chk{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--ink);margin-top:8px}
</style></head><body>
<header><h1>Golden 50 — hand labels</h1><div class="bar"><i id="prog"></i></div><span id="count"></span>
<button id="filter">Show unlabeled only</button><button class="pri" id="export">Export CSV</button></header>
<main><section id="list"></section>
<aside>
<b>Rules (GRADING_CONTRACT.md)</b>
<h3>Topic — highest-severity specific problem; tie → first mentioned; praise → first specific praised feature; general → other</h3>
<dl><dt>access</dt><dd>login, signup, password, account access</dd><dt>usability</dt><dd>navigation, controls, layout, queue/playlist mgmt, ads</dd>
<dt>playback</dt><dd>failures, crashes, lag, connection errors, audio quality, resource use</dd><dt>downloads</dt><dd>downloading, saved music, offline</dd>
<dt>catalog</dt><dd>missing songs/artists, search, recommendations, lyrics availability</dd><dt>billing</dt><dd>price, charges, subscriptions, paywalls, premium entitlement, premium-only controls. A paid-plan mention alone is not billing.</dd>
<dt>support</dt><dd>contacting support / its response</dd><dt>other</dt><dd>general praise/criticism, unrelated, no specific topic</dd></dl>
<h3>Intent (precedence)</h3><dl><dt>cancellation</dt><dd>explicitly leaving / uninstalling / cancelling / threatening to</dd><dt>complaint</dt><dd>negative experience incl. mixed; "bad app"</dd><dt>request</dt><dd>desired change, no failure reported</dd><dt>praise</dt><dd>positive</dd><dt>unclear</dt><dd>bare boycott slogans, unrelated, meaningless</dd></dl>
<h3>Severity</h3><dl><dt>1</dt><dd>no problem: praise, neutral/unclear, pure request</dd><dt>2</dt><dd>dislike, generic criticism, minor annoyance</dd><dt>3</dt><dd>degraded/restricted; some use or workaround remains</dd><dt>4</dt><dd>core task clearly blocked (can't log in / play)</dd><dt>5</dt><dd>explicit serious financial, privacy or data harm</dd></dl>
<p style="color:var(--mute)">Stars, angry words and cancellation threats do not set severity. Tick "ambiguous" when two answers are defensible and record the alternative.</p>
</aside></main>
<script>
const DATA = __DATA__;
const TOPICS=["access","usability","playback","downloads","catalog","billing","support","other"];
const INTENTS=["cancellation","complaint","request","praise","unclear"];
const SENT=[["-1","-1 very negative"],["-0.5","-0.5 negative"],["0","0 neutral/mixed"],["0.5","0.5 positive"],["1","1 very positive"]];
const KEY="golden50-labels-v1";
let S={};try{S=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){S={}}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}};
let onlyOpen=false;
const opt=(vals,cur,blank)=>(blank?'<option value="">—</option>':'')+vals.map(v=>{const[val,lab]=Array.isArray(v)?v:[v,v];return `<option value="${val}" ${String(cur)===String(val)?'selected':''}>${lab}</option>`}).join('');
const esc=s=>s.replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const complete=l=>l&&l.topic&&l.intent&&l.severity&&l.sentiment!==undefined&&l.sentiment!=="";
function render(){
  const list=document.getElementById('list');list.innerHTML='';
  DATA.forEach((r,i)=>{const l=S[r.review_id]||{};if(onlyOpen&&complete(l))return;
    const d=document.createElement('div');d.className='card'+(complete(l)?' done':'');
    const qOk=!l.evidence_quote||r.review_text.includes(l.evidence_quote);
    d.innerHTML=`<div class="meta">#${i+1} · ${r.review_id} · ${r.review_rating}★ · ${r.review_timestamp}</div>
    <p class="text">${esc(r.review_text)}</p>
    <div class="grid">
     <div><label>topic</label><select data-f="topic">${opt(TOPICS,l.topic,1)}</select></div>
     <div><label>intent</label><select data-f="intent">${opt(INTENTS,l.intent,1)}</select></div>
     <div><label>severity</label><select data-f="severity">${opt(["1","2","3","4","5"],l.severity,1)}</select></div>
     <div><label>sentiment</label><select data-f="sentiment">${opt(SENT,l.sentiment,1)}</select></div></div>
    <div class="row2"><div><label>evidence_quote (paste exact text from the review; optional)</label><input type="text" data-f="evidence_quote" value="${esc(l.evidence_quote||'')}">${qOk?'':'<div class="q-bad">Not an exact substring of the review</div>'}</div>
     <div><label>notes (why; language; doubts)</label><input type="text" data-f="notes" value="${esc(l.notes||'')}"></div></div>
    <label class="chk"><input type="checkbox" data-f="ambiguous" ${l.ambiguous?'checked':''}> ambiguous — alternative also acceptable:</label>
    <div class="grid" style="margin-top:4px"><div><label>alt topic</label><select data-f="alt_topic">${opt(TOPICS,l.alt_topic,1)}</select></div>
     <div><label>alt intent</label><select data-f="alt_intent">${opt(INTENTS,l.alt_intent,1)}</select></div>
     <div><label>alt severity</label><select data-f="alt_severity">${opt(["1","2","3","4","5"],l.alt_severity,1)}</select></div></div>`;
    d.querySelectorAll('[data-f]').forEach(el=>el.addEventListener('change',()=>{const f=el.dataset.f;S[r.review_id]=S[r.review_id]||{};
      S[r.review_id][f]=el.type==='checkbox'?el.checked:el.value;save();if(f==='evidence_quote'||!onlyOpen)render();progress();}));
    list.appendChild(d);});progress();}
function progress(){const n=DATA.filter(r=>complete(S[r.review_id])).length;document.getElementById('count').textContent=`${n}/50 labeled`;document.getElementById('prog').style.width=(n*2)+'%';}
document.getElementById('filter').onclick=e=>{onlyOpen=!onlyOpen;e.target.textContent=onlyOpen?'Show all':'Show unlabeled only';render();};
document.getElementById('export').onclick=()=>{
  const cols=["review_id","review_text","review_rating","review_likes","app_version","review_timestamp","topic","intent","sentiment","severity","entities","evidence_quote","needs_review","ambiguous","alt_topic","alt_intent","alt_severity","notes"];
  const q=v=>{v=v==null?'':String(v);return /[",\n\r]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v};
  const lines=[cols.join(',')];DATA.forEach(r=>{const l=S[r.review_id]||{};const o={...r,...l,entities:l.entities||'',needs_review:l.ambiguous?'true':'false',ambiguous:l.ambiguous?'true':'false'};lines.push(cols.map(c=>q(o[c])).join(','));});
  const n=DATA.filter(r=>complete(S[r.review_id])).length;if(n<50&&!confirm(`Only ${n}/50 labeled. Export anyway?`))return;
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([lines.join('\n')+'\n'],{type:'text/csv'}));a.download='golden_50_labeled.csv';a.click();};
render();
</script></body></html>"""

out = ROOT / "tools/label_golden.html"
out.write_text(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")
print(f"wrote {out} ({len(data)} reviews)")
