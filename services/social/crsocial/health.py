"""Freshness is time since a successful read, not time since a JSON export."""
from datetime import timedelta


def summarize(state,accounts,at,interval_hours):
    from .feed import instant
    rows=[];alerts=[]
    for rule in accounts:
        s=state.get('accounts',{}).get(rule['handle'],{})
        fresh_at=s.get('last_head_success',s.get('last_success'))
        age=max(0,int((at-instant(fresh_at)).total_seconds())) if fresh_at else None
        pending=[{'provider':name,'since_at':src['pending']['since_at'],'until_at':src['pending']['until_at']}
                 for name,src in s.get('sources',{}).items() if src.get('pending')]
        if not pending and s.get('pending'):pending=[{'provider':s.get('provider','scraper'),'since_at':s['pending']['since_at'],'until_at':s['pending']['until_at']}]
        fresh=age is not None and age<=(interval_hours+1)*3600
        row={'handle':rule['handle'],'last_success':fresh_at,'age_seconds':age,'fresh':fresh,
             'provider':s.get('provider'),'pending':pending,'last_error':s.get('last_error')}
        rows.append(row)
        if not fresh:alerts.append({'code':'stale_source','account':rule['handle']})
        if s.get('last_error'):alerts.append({'code':s['last_error'].get('code',s['last_error'].get('kind','source_error')),'account':rule['handle']})
        if pending:alerts.append({'code':'pending_pages','account':rule['handle']})
    providers=state.get('providers',{})
    for name,s in providers.items():
        if s.get('status') not in ('ok',):alerts.append({'code':(s.get('last_error') or {}).get('code',s.get('status','unknown')),'provider':name})
    events=state.get('events',[])
    window=[e for e in events if at-instant(e['at'])<=timedelta(days=7)]
    good=state.get('pilot',{}).get('successes',0)
    total=good+state.get('pilot',{}).get('failures',0)
    return {'status':'degraded' if alerts else 'ok','observed_at':at.isoformat(),'poll_interval_hours':interval_hours,
            'accounts':rows,'providers':providers,'alerts':alerts,'pilot':{'period_days':7,'started_at':state.get('pilot',{}).get('started_at'),
               'observed_operations':total,'successful_operations':good,'success_rate':good/total if total else None,'metrics_window':'since_start',
               'observation_complete':bool(state.get('pilot',{}).get('started_at')) and at-instant(state['pilot']['started_at'])>=timedelta(days=7)},
            'event_limit':200,'events':window}
