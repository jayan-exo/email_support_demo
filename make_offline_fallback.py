"""Build a self-contained, no-network HTML walkthrough for backup demos.

This is NOT a model/API app. The Streamlit app is the actual implementation.
"""
from __future__ import annotations
import json
from pathlib import Path
from core import CASE_PATH, INCOMING_PATH, CATEGORIES, PRIORITIES, PRIORITY_NAMES, load_csv, propose_offline

root=Path(__file__).resolve().parent
incoming = load_csv(INCOMING_PATH)
cases = load_csv(CASE_PATH)
records = []
for t in incoming:
    prop = propose_offline(t['subject'],t['body'])
    records.append({"id":t["ticket_id"], "tenant":t["tenant_id"],"customer":t["customer"],
                    "subject":t["subject"],"body":t["body"],"suggested_priority":prop.priority,
                    "suggested_category":prop.category,"signals":prop.signals})
valid = [{"case_id":c["case_id"], "tenant":c["tenant_id"],"category":c["category"],
          "subject":c["subject"], "resolution":c["verified_resolution"],"next_step":c["safe_next_step"],
          "date":c["resolved_at"][:10]} for c in cases if c['status']=='resolved' and c['is_current']=='true' and c['resolution_verified']=='true']
seed = json.dumps({"tickets":records,"cases":valid,"categories":CATEGORIES,"priorities":PRIORITY_NAMES}, ensure_ascii=False)
seed=seed.replace('</','<\\/')
html=r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SupportFlow — offline browser simulation</title>
<style>
:root{--bg:#0c1424;--panel:#142039;--panel2:#1b2a46;--ink:#f4f7fc;--muted:#a5b2ca;--line:#31425c;--blue:#8ab5ff;--accent:#74d5ae;--warn:#f0c984;}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 0 0,#1c3455 0,#0c1424 52%);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
header{max-width:1220px;margin:auto;padding:30px 24px 18px;display:flex;align-items:center;gap:16px;justify-content:space-between}
.brand{font-size:28px;font-weight:800;letter-spacing:-.8px}.brand span{color:var(--accent)}
.meta{color:var(--muted);font-size:13px}.chip{display:inline-block;border:1px solid #59728c;color:#d3e6ff;border-radius:30px;padding:6px 10px;font-size:12px;font-weight:700}
main{max-width:1220px;margin:auto;padding:0 24px 50px}
.notice{border:1px solid #a77e42;background:#322a22;border-radius:12px;padding:13px 16px;color:#ffe8b8;margin-bottom:18px}
.hero{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}.metric{background:#14213b;border:1px solid var(--line);border-radius:13px;padding:13px 17px}.metric small{display:block;color:var(--muted)}.metric strong{font-size:25px}
.layout{display:grid;grid-template-columns:1fr 1fr;gap:18px}
section{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:18px;box-shadow:0 18px 50px #060b1750}
h2{font-size:19px;letter-spacing:-.3px;margin:0 0 10px}h3{margin:0 0 10px;font-size:15px;color:#e3eefd}p{margin:6px 0 13px;color:var(--muted)}label{display:block;font-size:13px;font-weight:700;color:#dce7fa;margin:14px 0 6px}
select,textarea,input{font:inherit;width:100%;background:#0f1a30;border:1px solid #3b4f6d;border-radius:9px;padding:10px 12px;color:var(--ink)}textarea{resize:vertical;min-height:170px}
.email{background:#101b32;border:1px solid #324563;border-radius:12px;padding:14px;white-space:pre-wrap;min-height:115px}
.subject{font-size:17px;font-weight:750;line-height:1.3;margin:10px 0}.subtle{font-size:13px;color:var(--muted)}
button{font:inherit;cursor:pointer;border:0;border-radius:10px;padding:10px 14px;font-weight:730;background:var(--accent);color:#07281f;margin:7px 7px 0 0}button.secondary{background:#263953;color:#e5edff;border:1px solid #546784}button:disabled{background:#3c4b60;color:#9aabc4;cursor:not-allowed}
.result{border-radius:10px;background:#112d31;border:1px solid #366f64;padding:12px;margin:12px 0;color:#d5ffee}.pending{background:#292822;border-color:#766543;color:#fff0c9}
#classification{display:none}#retrieval{display:none}#draftSection{display:none}#approved{display:none}
.evidence{padding:13px;background:#111e34;border-radius:10px;border:1px solid #304665;margin:9px 0}.evidence b{color:#b9d5ff}code{font-family:ui-monospace,monospace;color:var(--accent)}
.rail{display:flex;gap:8px;margin-bottom:15px;flex-wrap:wrap}.rail span{border:1px solid #394e68;border-radius:30px;font-size:12px;color:#a7bad6;padding:5px 9px}.rail span.active{border-color:#66c6a4;color:#bdfae3}
.full{grid-column:1/-1}#audit{white-space:pre-wrap;font:12px/1.75 ui-monospace,monospace;color:#cad7e9;min-height:45px}a{color:#afcdff}
@media(max-width:800px){.layout{grid-template-columns:1fr}.hero{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}}
</style></head>
<body><header><div><div class="brand">✉️ Support<span>Flow</span></div><div class="meta">Human-reviewed support email workflow · Demo build · November 2026</div></div><span class="chip">OFFLINE SIMULATION · NO API CALLS · NO SEND</span></header>
<main><div class="notice"><b>Supervisor demo backup:</b> This standalone browser page simulates classification, retrieval and email drafting using fixed rules/templates. It does <b>not</b> call OpenJev or Groq. Use the Streamlit app for live provider calls.</div>
<div class="hero"><div class="metric"><small>Historical synthetic archive</small><strong>288 cases</strong></div><div class="metric"><small>Built-in incoming tickets</small><strong>12</strong></div><div class="metric"><small>Mandatory human approval gates</small><strong>2</strong></div></div>
<div class="rail"><span class="active">1 · New email</span><span>2 · Review classification</span><span>3 · Retrieve evidence & draft</span><span>4 · Review reply (unsent)</span></div>
<div class="layout"><div><section><h2>Incoming customer email</h2><label for="ticket">Choose an example</label><select id="ticket"></select><div class="subtle" id="customer"></div><div class="subject" id="subject"></div><div class="email" id="body"></div><button id="suggestBtn">1. Propose classification</button><button class="secondary" id="resetBtn">Reset this ticket</button></section>
<section id="classification"><h2>Human Gate 1 · Classification</h2><p>Rule-based suggestion; reviewer must validate priority and category.</p><div id="suggestion" class="result pending"></div><label for="priority">Human-approved priority</label><select id="priority"></select><label for="category">Human-approved issue category</label><select id="category"></select><button id="approveClass">Approve classification</button><div id="classApproved" class="result" style="display:none"></div></section></div>
<div><section id="retrieval"><h2>Historical case retrieval</h2><p>Local token-overlap matching; same synthetic tenant, verified/current solved cases only. Example similarity does <b>not</b> prove a fix.</p><div id="evidence"></div><button id="draftBtn">2. Prepare offline reply draft</button></section>
<section id="draftSection"><h2>Human Gate 2 · Review generated template</h2><p>The text below is an editable non-AI template draft. Approval does not send an email.</p><label for="draft">Draft reply (editable)</label><textarea id="draft" rows="12"></textarea><button id="approveDraft">3. Approve draft (do NOT send)</button><button id="rejectDraft" class="secondary">Reject / redraft</button><div id="approved" class="result">Approved by human reviewer — UNSENT. <button id="downloadBtn" class="secondary">Download TXT</button></div></section></div>
<section class="full"><h2>Audit log</h2><div id="audit">No activity yet. Select a ticket and propose its classification.</div></section></div></main>
<script id="seed" type="application/json">__SEED__</script>
<script>
const db=JSON.parse(document.getElementById('seed').textContent),$=x=>document.getElementById(x);
let ticket=null, proposed=null, approved=null, matches=[], events=[];
function log(event){events.push(new Date().toLocaleTimeString()+' | '+event);$('audit').textContent=events.join('\n')}
function show(id,yes=true){$(id).style.display=yes?'block':'none'}
function opts(el,values,labels){el.innerHTML='';for(const val of values){let o=document.createElement('option');o.value=val;o.textContent=labels[val]||val;el.add(o)}}
function reset(){ticket=db.tickets.find(t=>t.id===$('ticket').value);proposed=approved=null;matches=[];events=[];
 $('subject').textContent=ticket.subject;$('body').textContent=ticket.body;$('customer').textContent=ticket.customer+' · '+ticket.id;
 show('classification',false);show('retrieval',false);show('draftSection',false);show('approved',false);$('audit').textContent='No activity yet';$('suggestBtn').disabled=false}
function suggest(){proposed={priority:ticket.suggested_priority,category:ticket.suggested_category};
 $('suggestion').textContent='PROPOSED '+proposed.priority+' · '+db.categories[proposed.category]+' · Rule-based simulation. Signals: '+(ticket.signals.join('; ')||'insufficient signals');
 $('priority').value=proposed.priority;$('category').value=proposed.category;show('classification');show('classApproved',false);show('retrieval',false);show('draftSection',false);$('suggestBtn').disabled=true;log('Classification proposed by offline rules; waiting on reviewer')}
function overlap(a,b){let words=s=>new Set(s.toLowerCase().match(/[a-z0-9]+/g)||[]);let w1=words(a),w2=words(b);let out=0;for(const x of w1){if(x.length>3&&w2.has(x))out++}return out}
function retrieve(){let input=ticket.subject+' '+ticket.body;return db.cases.filter(c=>c.tenant===ticket.tenant).map(c=>({data:c,score:overlap(input,c.subject)+(c.category===approved.category?3:0)})).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,3).map(x=>x.data)}
function approveClass(){approved={priority:$('priority').value,category:$('category').value};matches=retrieve();
 $('classApproved').textContent='APPROVED: '+approved.priority+' · '+db.categories[approved.category];show('classApproved');show('retrieval');show('draftSection',false);
 $('evidence').innerHTML='';if(!matches.length){$('evidence').textContent='No matching approved historical cases; the draft must request clarification without guessing a fix.'}else{
 for(const c of matches){const el=document.createElement('div');el.className='evidence';let title=document.createElement('b');title.textContent=c.case_id+' — '+c.subject;let d=document.createElement('div');d.className='subtle';d.textContent='Past verified resolution: '+c.resolution+'  |  Safe diagnostic: '+c.next_step;el.append(title,d);$('evidence').append(el)}}
 log('HUMAN gate 1 approved '+approved.priority+'/'+approved.category+'; '+matches.length+' old cases retrieved')}
function makeDraft(){let impact=approved.priority==='P0'?'We understand this may affect site-wide operations. The support team will need to confirm the scope and escalation route.':approved.priority==='P1'?'We recognize the operational disruption and the urgency of validating the affected workflow.':'We will review the reported issue and confirm the appropriate next steps.';
 let check=matches.length?'For an initial diagnostic review, the team can '+matches[0].next_step.replace(/[.]$/,'')+'.':'We cannot confirm a known fix from the available verified cases, so we need to investigate this occurrence.';
 return 'Hello,\n\nThank you for reaching out. We understand you are reporting: '+ticket.subject+'.\n\n'+impact+'\n\n'+check+'\n\nCould you share the time this began, the affected facility, and a screenshot of the error without any passwords or tokens?\n\nKind regards,\nSupport Team'}
function draft(){show('draftSection');show('approved',false);$('draft').value=makeDraft();$('draft').disabled=false;$('approveDraft').disabled=false;log('Offline TEMPLATE draft prepared; waiting for HUMAN gate 2')}
function approveDraft(){if($('draft').value.trim().length<40){alert('Draft is too short; revise before approving.');return}show('approved');$('draft').disabled=true;$('approveDraft').disabled=true;log('HUMAN gate 2 approved draft. UNSENT. No API calls or email sending')}
function rejectDraft(){show('approved',false);$('draft').disabled=false;$('approveDraft').disabled=false;log('HUMAN gate 2 rejected draft; ready for editing/redraft')}
function download(){let blob=new Blob([$('draft').value],{type:'text/plain'}),a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=ticket.id+'_approved_UNSENT.txt';a.click();URL.revokeObjectURL(url)}
opts($('priority'),Object.keys(db.priorities),db.priorities);opts($('category'),Object.keys(db.categories),db.categories);
for(const t of db.tickets){const o=document.createElement('option');o.value=t.id;o.textContent=t.id+' · '+t.subject;$('ticket').add(o)}
$('ticket').onchange=reset;$('resetBtn').onclick=reset;$('suggestBtn').onclick=suggest;$('approveClass').onclick=approveClass;$('draftBtn').onclick=draft;$('approveDraft').onclick=approveDraft;$('rejectDraft').onclick=rejectDraft;$('downloadBtn').onclick=download;
reset();
</script></body></html>'''
output=root/'offline_demo.html'
output.write_text(html.replace('__SEED__',seed),encoding='utf-8')
print('Created',output.name,'bytes',output.stat().st_size, 'cases included',len(valid))
