from __future__ import annotations

import json
from pathlib import Path

def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Air Fryer Recipe Rankings</title>
<style>
:root{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light dark}
body{max-width:1200px;margin:0 auto;padding:1rem 1.25rem;line-height:1.45}
header{display:flex;gap:1rem;align-items:flex-end;justify-content:space-between;flex-wrap:wrap}
h1{margin-bottom:.25rem}.muted{opacity:.72}.controls{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0}
input,select{font:inherit;padding:.55rem .7rem;min-width:13rem}table{width:100%;border-collapse:collapse;font-size:.94rem}
th,td{text-align:left;padding:.55rem;border-bottom:1px solid currentColor;vertical-align:top}th{position:sticky;top:0;background:Canvas}
a{color:LinkText}.score{font-variant-numeric:tabular-nums}.badge{white-space:nowrap}details{margin:1rem 0}footer{margin-top:2rem}.sr{position:absolute;left:-10000px}
@media(max-width:760px){table{font-size:.82rem}th:nth-child(5),td:nth-child(5),th:nth-child(7),td:nth-child(7){display:none}}
</style>
</head>
<body>
<header><div><h1>Air Fryer Recipe Rankings</h1><div class="muted" id="generated">Loading…</div></div><div class="muted">Hierarchical Bayesian ranking with evidence QA</div></header>
<div class="controls">
<label><span class="sr">Search recipes</span><input id="search" type="search" placeholder="Search recipes or publishers"></label>
<label><span class="sr">Category</span><select id="category"><option value="">All categories</option></select></label>
<label><span class="sr">Minimum evidence confidence</span><select id="confidence"><option value="0">Any confidence</option><option value="0.8">≥ 0.80</option><option value="0.9">≥ 0.90</option></select></label>
</div>
<div id="stats" class="muted"></div>
<table aria-describedby="stats"><thead><tr><th>Rank</th><th>Recipe</th><th>Publisher</th><th>Score</th><th>Stars</th><th>Ratings</th><th>Evidence</th><th>Velocity/day</th><th>Movement</th></tr></thead><tbody id="rows"></tbody></table>
<details><summary>Methodology and coverage</summary><pre id="methodology" style="white-space:pre-wrap"></pre></details>
<footer class="muted">Data is automatically refreshed from public recipe pages. Rankings are statistical estimates, not taste-test judgments.</footer>
<script>
let DATA={leaderboard:[],categories:[],methodology:{}};
const esc=s=>String(s??"").replace(/[&<>\"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}[c]));
function render(){
 const q=document.querySelector('#search').value.trim().toLowerCase();
 const cat=document.querySelector('#category').value;
 const min=Number(document.querySelector('#confidence').value||0);
 const rows=DATA.leaderboard.filter(r=>(!q||(`${r.title} ${r.source} ${r.combined_sources}`).toLowerCase().includes(q)))&&(!cat||(r.categories||'').split(' | ').includes(cat))&&Number(r.evidence_confidence||0)>=min);
 document.querySelector('#stats').textContent=`Showing ${rows.length} of ${DATA.leaderboard.length} ranked recipes`;
 document.querySelector('#rows').innerHTML=rows.map(r=>`<tr><td>${r.rank}</td><td><a href="${esc(r.url)}" rel="noopener noreferrer">${esc(r.title)}</a><br><small>${esc(r.categories||'')}</small></td><td>${esc(r.combined_sources||r.source)}</td><td class="score">${Number(r.hierarchical_score).toFixed(4)}</td><td>${Number(r.rating).toFixed(2)}</td><td>${Number(r.rating_count).toLocaleString()}</td><td class="badge">${Number(r.evidence_confidence||0).toFixed(2)} ${esc(r.evidence_status||'')}</td><td>${r.review_velocity_per_day==null?'—':Number(r.review_velocity_per_day).toFixed(1)}</td><td>${r.movement==null?'New':(r.movement>0?'▲ '+r.movement:r.movement<0?'▼ '+Math.abs(r.movement):'—')}</td></tr>`).join('');
}
fetch('data.json',{cache:'no-store'}).then(r=>r.json()).then(data=>{
 DATA=data;
 document.querySelector('#generated').textContent=`Generated ${data.generated_at} · ${data.source_count} configured publishers`;
 const categories=[...new Set(data.leaderboard.flatMap(r=>(r.categories||'').split(' | ').filter(Boolean)))].sort();
 document.querySelector('#category').innerHTML='<option value="">All categories</option>'+categories.map(c=>`<option>${esc(c)}</option>`).join('');
 document.querySelector('#methodology').textContent=JSON.stringify(data.methodology,null,2);
 render();
}).catch(e=>{document.querySelector('#generated').textContent='Could not load leaderboard data';document.querySelector('#stats').textContent=String(e)});
for(const id of ['search','category','confidence'])document.querySelector('#'+id).addEventListener('input',render);
</script>
</body></html>"""


def write_dashboard(
    docs_dir: str | Path,
    generated_at: str,
    ranked: list[dict],
    reliability: list[dict],
    anomalies: list[dict],
    methodology: dict,
    source_count: int,
) -> None:
    docs = Path(docs_dir)
    docs.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": generated_at,
        "source_count": source_count,
        "leaderboard": ranked[:500],
        "source_reliability": reliability,
        "anomalies": anomalies[:100],
        "methodology": methodology,
    }
    (docs / "data.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (docs / "index.html").write_text(_dashboard_html(), encoding="utf-8")
    (docs / ".nojekyll").write_text("", encoding="utf-8")
