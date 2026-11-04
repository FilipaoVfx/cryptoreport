"""Read-only deployment proof; never invokes an extraction or an inference."""
from datetime import datetime,timezone
import json
from pathlib import Path
import urllib.request

repo=Path(__file__).resolve().parents[4]
root=Path('/var/lib/cryptoreport-transcripts/social')
state=json.loads((root/'state.json').read_text())
url='https://communist-mature-gravity-deeper.trycloudflare.com/data/social-feed.json'
with urllib.request.urlopen(urllib.request.Request(url,headers={'Cache-Control':'no-cache'}),timeout=25) as response:
    public=json.loads(response.read(4_000_000));http=response.status
local=json.loads((repo/'prototypes/movil/data/social-feed.json').read_text())
assert http==200 and {p['id'] for p in public['posts']}=={p['id'] for p in local['posts']}
assert public['status']=='ok' and len(public['accounts'])==8
assert not any(src.get('pending') for account in state['accounts'].values() for src in account.get('sources',{}).values())
required={'bulltheoryio','bitcoinarchive','watcherguru','crediblecrypto'}
rows=[a for a in public['accounts'] if a['handle'] in required]
assert len(rows)==4 and all(a['status']=='ok' and a['posts']>0 and a['lookback_days']==3 for a in rows)
assert public['health']['poll_interval_hours']==3
assert public['twitterapi_budget']['monthly_limit']==60000
assert public['model_api_enabled'] is False
paused=json.loads(Path('/var/lib/cryptoreport-transcripts/analysis-plan/status.json').read_text())
assert paused.get('paused_by_user') is True and paused['status']=='paused_by_user'
result={'status':'PASS','verified_at':datetime.now(timezone.utc).isoformat(),'http':http,'public_matches_local_ids':True,
        'total_posts':len(public['posts']),'new_account_posts':sum(a['posts'] for a in rows),
        'accounts':[{k:a.get(k) for k in ('handle','author_id','lookback_days','posts','status','label')} for a in rows],
        'pending_pages':0,'poll_interval_hours':3,'budget':public['budget'],'monthly_estimated_credit_limit':60000,
        'analysis':'paused_by_user','model_api_enabled':False,'classification':public['classification']}
Path(__file__).with_name('deployment-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
