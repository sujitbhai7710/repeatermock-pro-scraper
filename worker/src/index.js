// RepeaterMock PRO Scraper — Dashboard Worker
const HTML = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>PRO Scraper Dashboard</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:system-ui;background:#0f172a;color:#e2e8f0}
.container{max-width:1200px;margin:0 auto;padding:24px}
.stat{display:inline-block;background:#1e293b;padding:16px;border-radius:8px;margin:4px;min-width:120px}
.stat .v{font-size:28px;font-weight:bold}.stat .l{color:#94a3b8;font-size:12px}
.green{color:#4ade80}.yellow{color:#facc15}.red{color:#f87171}.blue{color:#38bdf8}
table{width:100%;border-collapse:collapse;margin:12px 0}th{text-align:left;padding:8px;color:#94a3b8;border-bottom:1px solid #334155;font-size:12px}
td{padding:8px;border-bottom:1px solid #1e293b;font-size:13px}
.bar{background:#334155;border-radius:4px;height:8px;min-width:60px}.bar>div{height:100%;background:#4ade80;border-radius:4px}
</style></head><body><div class="container">
<h1 style="color:#38bdf8">📊 PRO Scraper Dashboard</h1>
<div id="stats"></div>
<h3 style="margin-top:20px">Series Progress</h3>
<div id="series"></div>
<h3 style="margin-top:20px">Recent Runs</h3>
<div id="runs"></div>
</div>
<script>
async function load(){const d=await(await fetch('/api/dashboard')).json();
const o=d.overview;
document.getElementById('stats').innerHTML=
['<div class="stat"><div class="l">TOTAL</div><div class="v blue">'+o.total+'</div></div>',
'<div class="stat"><div class="l">SCRAPED</div><div class="v green">'+o.scraped+'</div></div>',
'<div class="stat"><div class="l">PARTIAL</div><div class="v yellow">'+o.partial+'</div></div>',
'<div class="stat"><div class="l">FAILED</div><div class="v red">'+o.failed+'</div></div>',
'<div class="stat"><div class="l">PENDING</div><div class="v">'+o.pending+'</div></div>',
'<div class="stat"><div class="l">PROGRESS</div><div class="v green">'+o.pct+'%</div></div>'].join('');
document.getElementById('series').innerHTML='<table>'+d.series.map(s=>{
const p=s.total?Math.round(s.scraped/s.total*100):0;
return '<tr><td>'+s.name.substring(0,40)+'</td><td>'+s.scraped+'/'+s.total+'</td><td><div class="bar"><div style="width:'+p+'%"></div></div></td><td>'+p+'%</td></tr>';
}).join('')+'</table>';
document.getElementById('runs').innerHTML='<table><tr><th>Started</th><th>Scraped</th><th>Min</th></tr>'+
(d.runs||[]).slice(0,10).map(r=>'<tr><td>'+new Date(r.started_at*1000).toLocaleString()+'</td><td>'+r.tests_scraped+'</td><td>'+(r.time_minutes||0).toFixed(1)+'</td></tr>').join('')+'</table>';
}
load();setInterval(load,60000);
</script></body></html>`;

function parseCookies(h){const c={};if(!h)return c;for(const p of h.split(';')){const[k,...v]=p.trim().split('=');if(k)c[k]=v.join('=')}return c}

export default{
  async fetch(req,env){
    const url=new URL(req.url);const DB=env.DB;const path=url.pathname;
    try{
      if(path==='/'||path==='/index.html')return new Response(HTML,{headers:{'Content-Type':'text/html'}});
      if(path==='/api/dashboard'){
        const r=await DB.batch([
          DB.prepare('SELECT COUNT(*) as total, SUM(CASE WHEN status=\'scraped\' THEN 1 ELSE 0 END) as scraped, SUM(CASE WHEN status=\'partial\' THEN 1 ELSE 0 END) as partial, SUM(CASE WHEN status=\'failed\' THEN 1 ELSE 0 END) as failed, SUM(CASE WHEN status=\'pending\' THEN 1 ELSE 0 END) as pending FROM tests'),
          DB.prepare('SELECT s.slug,s.name,s.total_tests as total,COALESCE((SELECT COUNT(*) FROM tests t WHERE t.series_slug=s.slug AND t.status=\'scraped\'),0) as scraped FROM series s ORDER BY s.total_tests DESC'),
          DB.prepare('SELECT * FROM runs ORDER BY started_at DESC LIMIT 10'),
        ]);
        const o=r[0].results[0]||{};const total=o.total||0;const scraped=o.scraped||0;
        return Response.json({overview:{total,scraped,partial:o.partial,failed:o.failed,pending:o.pending,pct:total?Math.round(scraped/total*100):0},series:r[1].results||[],runs:r[2].results||[]});
      }
      if(path==='/api/trigger'&&req.method==='POST'){
        const c=parseCookies(req.headers.get('Cookie'));
        if(c.admin_token!==env.ADMIN_PASSWORD)return Response.json({success:false,error:'Unauthorized'},{status:401});
        const r=await fetch('https://api.github.com/repos/'+env.GH_REPO+'/actions/workflows/scrape.yml/dispatches',{method:'POST',headers:{Authorization:'Bearer '+env.GH_TOKEN,Accept:'application/vnd.github+json','Content-Type':'application/json'},body:JSON.stringify({ref:'main'})});
        return Response.json({success:r.status===204});
      }
      if(path==='/admin'&&req.method==='POST'){
        const b=await req.json();
        if(b.password!==env.ADMIN_PASSWORD)return Response.json({success:false,error:'Wrong'});
        return new Response(JSON.stringify({success:true}),{status:200,headers:{'Content-Type':'application/json','Set-Cookie':'admin_token='+encodeURIComponent(env.ADMIN_PASSWORD)+'; HttpOnly; Path=/; Max-Age=86400'}});
      }
      if(path==='/admin')return new Response('<html><body><form method=POST><input name=password type=password><button>Login</button></form></body></html>',{headers:{'Content-Type':'text/html'}});
      return Response.json({error:'Not found'},{status:404});
    }catch(e){return Response.json({error:e.message},{status:500})}
  },
  async scheduled(event,env,ctx){
    if(env.GH_TOKEN&&env.GH_REPO){
      try{await fetch('https://api.github.com/repos/'+env.GH_REPO+'/actions/workflows/scrape.yml/dispatches',{method:'POST',headers:{Authorization:'Bearer '+env.GH_TOKEN,Accept:'application/vnd.github+json','Content-Type':'application/json'},body:JSON.stringify({ref:'main'})})}catch(e){console.error(e)}
    }
  }
};
