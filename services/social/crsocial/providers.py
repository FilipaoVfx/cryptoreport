"""Bounded provider routing with durable circuit breakers; no model calls."""
from datetime import timedelta, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from .collector import Client, CollectionError, credential, http_transport, timestamp
from .x_session import read_session
from .twitterapi import TwitterAPI, read_key


def instant(v):
    return datetime.fromisoformat(v.replace('Z','+00:00'))


def agent_page(payload, account, since, until, cursor=None):
    result={'account':account['handle'],'posts':[],'rejected':[],'next_cursor':None,'error':None,'coverage_complete':False,'stop_reason':'error'}
    if not isinstance(payload,dict):raise CollectionError('schema','X: respuesta incompatible')
    if payload.get('error'):
        e=payload['error']
        kind=e.get('kind')
        if kind not in ('auth','quota','network','schema','http'):kind='schema'
        raise CollectionError(kind,'X: consulta no completada',code=e.get('code') if e.get('code') in ('session_expired','rate_limited','x_unavailable') else 'x_unavailable',http=e.get('http') if type(e.get('http')) is int else None)
    items=payload.get('posts');following=payload.get('next_cursor')
    if payload.get('schema')!='twitter-cli-0.8.5' or not isinstance(items,list) or len(items)>100 or following is not None and (not isinstance(following,str) or len(following)>8192):
        raise CollectionError('schema','X: página incompatible')
    for p in items:
        try:
            a=p['author'];published=timestamp(p['created_at'])
            if not isinstance(p['id'],str) or not p['id'].isdigit() or not isinstance(p['text'],str) or not p['text'].strip() or not published:
                raise ValueError()
            # A repost by this account is not an authored assertion by this account.
            if p.get('is_retweet'):continue
            if str(a.get('screen_name','')).lower()!=account['handle'] or a.get('id')!=account['author_id']:raise ValueError()
            if not since<=instant(published)<until:continue
            result['posts'].append({'id':p['id'],'text':p['text'],'published_at':published,'fetched_at':datetime.now(timezone.utc).isoformat(),
                'author_id':a['id'],'author_handle':account['handle'],'source_account':account['handle'],'belongs_to_requested_account':True,
                'avatar_url':a.get('profile_image_url'),'language':p.get('lang'),'links':p.get('urls',[]),'media':p.get('media',[]),
                'is_repost':False,'is_reply':None,'is_quote':bool(p.get('quoted_tweet')),'text_completeness':'unverified'})
        except (KeyError,TypeError,ValueError):result['rejected'].append('X: publicación incompatible')
    result['next_cursor']=following
    result['stop_reason']='cursor_loop' if following and following==cursor else 'page_limit' if following else 'cursor_exhausted'
    return result


class Providers:
    def __init__(self,feed,at,transport=None,key=None):
        self.feed,self.at,self.transport=feed,at,transport
        self.calls=0;self.states=feed.state.setdefault('providers',{})
        self.secret=None
        try:self.secret=key if key is not None else credential(feed.config.env_file)
        except (CollectionError,OSError):pass
        self.client=Client(self.secret or 'unconfigured',max_calls=feed.config.max_calls,timeout=20,transport=self.scraper_request)
        self.twitterapi=TwitterAPI(self)

    def ready(self,name):
        if name=='twitterapi-io':
            try:read_key(self.feed.config.twitterapi_key_file);return True
            except (OSError,ValueError,TypeError):return False
        if name=='scraper':return bool(self.secret)
        if name=='agent-reach':
            try:
                read_session(self.feed.config.x_session)
                return Path(self.feed.config.x_python).is_file()
            except (OSError,ValueError):return False
        raise ValueError('Proveedor social desconocido')

    def available(self,name):
        s=self.states.setdefault(name,{})
        s['configured']=self.ready(name)
        if not s['configured']:
            s['status']='needs_credentials';return False
        if s.get('retry_at') and instant(s['retry_at'])>self.at:return False
        return True

    def reserve(self,name):
        if self.calls>=self.feed.config.max_calls:raise CollectionError('budget','Límite por ciclo alcanzado')
        self.feed.reserve(self.at,name)
        self.calls+=1

    def scraper_request(self,endpoint,params,key,timeout):
        self.reserve('scraper')
        return (self.transport or http_transport)(endpoint,params,key,timeout)

    def failure(self,name,error):
        s=self.states.setdefault(name,{})
        n=min(s.get('consecutive_failures',0)+1,12)
        if error.get('code') in ('plan_expired','payment_required') or error['kind']=='auth':delay=86400
        elif name=='twitterapi-io' and error.get('code')=='rate_limited':delay=max(120*2**(n-1),error.get('retry_after') or 0)
        elif error['kind']=='quota':delay=max(900,error.get('retry_after') or 3600)
        else:delay=min(6*3600,900*2**(n-1))
        observed=self.at
        if name=='twitterapi-io':observed=max(observed,datetime.fromtimestamp(self.feed.state.get('twitterapi',{}).get('last_request_epoch',self.at.timestamp()),timezone.utc))
        s.update(status='blocked' if error['kind']=='auth' or error.get('code') in ('plan_expired','payment_required') else 'cooldown',
                 consecutive_failures=n,last_error=error,retry_at=(observed+timedelta(seconds=delay)).isoformat())

    def fetch(self,name,rule,start,until,cursor=None):
        s=self.states.setdefault(name,{})
        s['last_attempt']=self.at.isoformat()
        try:
            if name=='scraper':result=self.client.collect(rule['handle'],mode='search',max_pages=1,since_at=start,until_at=until,cursor=cursor)
            elif name=='twitterapi-io':result=self.twitterapi.fetch(rule,start,until,cursor)
            else:
                self.reserve(name)
                request={'session':str(self.feed.config.x_session),'query':f"from:{rule['handle']} since_time:{int(start.timestamp())} until_time:{int(until.timestamp())}",'cursor':cursor}
                # No secrets in arguments or inherited debug output; worker never invokes CLI auth.
                worker=Path(__file__).with_name('x_worker.py')
                proc=subprocess.run([self.feed.config.x_python,str(worker)],input=json.dumps(request).encode(),capture_output=True,timeout=50,
                                    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONSTARTUP')})
                if proc.returncode or len(proc.stdout)>2_000_000:raise CollectionError('schema','X: ejecutor no completado')
                result=agent_page(json.loads(proc.stdout),rule,start,until,cursor)
            if result['error']:
                if result['error']['kind']!='budget':self.failure(name,result['error'])
            else:
                s.update(status='ok',last_success=self.at.isoformat(),last_error=None,consecutive_failures=0)
                s.pop('retry_at',None)
            return result
        except (OSError,subprocess.TimeoutExpired):e=CollectionError('network','Proveedor no disponible o timeout')
        except (ValueError,TypeError):e=CollectionError('schema','Respuesta de proveedor incompatible')
        except CollectionError as exc:e=exc
        error=e.public()
        if e.kind!='budget':self.failure(name,error)
        return {'posts':[],'rejected':[],'next_cursor':cursor,'stop_reason':'error','error':error}
