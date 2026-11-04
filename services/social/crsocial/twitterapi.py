"""Read-only twitterapi.io adapter. No X cookies, redirects or inference."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from .collector import CollectionError, timestamp, handle


def read_key(path):
    if path is None:raise ValueError('Credencial no configurada')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size>4096:raise ValueError('Credencial debe ser privada')
        doc=json.load(stream)
    key=doc.get('api_key')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',key):raise ValueError('Credencial inválida')
    return key


def configure(path, text=None):
    if text is None and not sys.stdin.isatty():raise ValueError('Usa una terminal interactiva')
    key=text if text is not None else getpass.getpass('twitterapi.io API key (oculta): ')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',key):raise ValueError('Credencial inválida')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise ValueError('No se admiten enlaces')
    fd,temp=tempfile.mkstemp(prefix='.twitterapi-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump({'api_key':key},stream);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return {'status':'configured','live_verified':False}


def http_request(endpoint, params, key, timeout=25):
    if endpoint not in ('/twitter/tweet/advanced_search','/oapi/my/info','/twitter/user/info'):raise ValueError('Endpoint no permitido')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    request=urllib.request.Request('https://api.twitterapi.io'+endpoint+'?'+urllib.parse.urlencode(params),
                                  headers={'X-API-Key':key,'Accept':'application/json'})
    try:response=urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout)
    except urllib.error.HTTPError as exc:response=exc
    with response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise CollectionError('schema','twitterapi.io: respuesta demasiado grande')
        return response.code,raw.decode('utf-8',errors='replace'),dict(response.headers)


def page(payload,rule,start,until,cursor=None):
    if not isinstance(payload,dict):raise CollectionError('schema','twitterapi.io: respuesta incompatible')
    items=payload.get('tweets');more=payload.get('has_next_page');following=payload.get('next_cursor')
    if (not isinstance(items,list) or len(items)>20 or type(more) is not bool
            or more and (not isinstance(following,str) or not following or len(following)>8192)):
        raise CollectionError('schema','twitterapi.io: página incompatible')
    result={'posts':[],'rejected':[],'error':None,'next_cursor':following if more else None,'coverage_complete':False,
            'stop_reason':'cursor_loop' if more and cursor==following else 'page_limit' if more else 'cursor_exhausted',
            'page_fingerprint':hashlib.sha256(json.dumps([p.get('id') if isinstance(p,dict) else None for p in items]).encode()).hexdigest() if items else None}
    dates=[timestamp(p.get('createdAt')) for p in items if isinstance(p,dict)]
    result['page_stats']={'returned':len(items),'valid_dates':sum(bool(d) for d in dates),
                          'oldest':min((d for d in dates if d),default=None),'newest':max((d for d in dates if d),default=None),
                          'out_of_window':0,'reposts':0}
    for p in items:
        try:
            a=p['author'];date=timestamp(p['createdAt']);identifier=p['id'];text=p['text']
            if (not isinstance(identifier,str) or not identifier.isdigit() or not isinstance(text,str) or not text.strip()
                    or not date or not isinstance(a,dict)):raise ValueError()
            # Search results do not authorize attribution of reposted/other authors' opinions.
            if p.get('retweeted_tweet'):
                result['page_stats']['reposts']+=1;continue
            if str(a.get('userName','')).lower()!=rule['handle'] or a.get('id')!=rule['author_id']:raise ValueError()
            published=datetime.fromisoformat(date)
            if not start<=published<until:
                result['page_stats']['out_of_window']+=1;continue
            entities=p.get('entities') or {};extended=p.get('extendedEntities') or {}
            urls=entities.get('urls',[])
            if not isinstance(urls,list):raise ValueError()
            result['posts'].append({'id':identifier,'text':text,'published_at':date,'fetched_at':datetime.now(timezone.utc).isoformat(),
                'author_id':a['id'],'author_handle':rule['handle'],'source_account':rule['handle'],'belongs_to_requested_account':True,
                'avatar_url':a.get('profilePicture'),'language':p.get('lang'),'conversation_id':p.get('conversationId'),
                'links':[u.get('expanded_url') or u.get('url') for u in urls if isinstance(u,dict)],'media':extended.get('media'),
                'is_reply':p.get('isReply') if isinstance(p.get('isReply'),bool) else None,'is_repost':False,
                'is_quote':bool(p.get('quoted_tweet')),'text_completeness':'unverified','ingest_provider':'twitterapi-io'})
        except (ValueError,KeyError,TypeError,AttributeError):result['rejected'].append('twitterapi.io: publicación incompatible')
    return result


class TwitterAPI:
    def __init__(self,hub,transport=None):
        self.hub=hub;self.feed=hub.feed;self.transport=transport or http_request

    def request(self,endpoint,params):
        at=datetime.now(timezone.utc);state=self.feed.state.setdefault('twitterapi',{})
        day,month=at.date().isoformat(),at.strftime('%Y-%m')
        reserve=300 if endpoint.endswith('advanced_search') else 18 if endpoint=='/twitter/user/info' else 15
        if endpoint.endswith('advanced_search') and state.get('contract_blocked'):
            raise CollectionError('budget','twitterapi.io: contrato de tamaño cambiado; requiere revisión',code='contract_changed')
        daily=state.setdefault('estimated_daily_credits',{});monthly=state.setdefault('estimated_monthly_credits',{})
        bootstrap=state.setdefault('estimated_backfill_daily_credits',{})
        cfg=self.feed.config
        if min(cfg.twitterapi_daily_credits,cfg.twitterapi_backfill_daily_credits)<300 or cfg.twitterapi_monthly_credits<max(cfg.twitterapi_daily_credits,cfg.twitterapi_backfill_daily_credits):raise ValueError('Límite de créditos inválido')
        daily_used=bootstrap.get(day,0) if cfg.backfill else daily.get(day,0)-bootstrap.get(day,0)
        daily_limit=cfg.twitterapi_backfill_daily_credits if cfg.backfill else cfg.twitterapi_daily_credits
        if daily_used+reserve>daily_limit or monthly.get(month,0)+reserve>cfg.twitterapi_monthly_credits:
            raise CollectionError('budget','twitterapi.io: límite de créditos estimados alcanzado',code='credit_budget')
        balance=state.get('balance')
        if endpoint.endswith('advanced_search') and balance and balance['total_credits']-state.get('estimated_since_balance',0)<reserve+300:
            raise CollectionError('quota','twitterapi.io: saldo observado insuficiente',code='insufficient_credits')
        # Shared run.lock protects both this spacing marker and the spend reservation.
        wait=10-(time.time()-state.get('last_request_epoch',0))
        if wait>0:time.sleep(min(wait,10))
        self.hub.reserve('twitterapi-io')
        daily[day]=daily.get(day,0)+reserve;monthly[month]=monthly.get(month,0)+reserve
        if cfg.backfill:bootstrap[day]=bootstrap.get(day,0)+reserve
        state['estimated_since_balance']=state.get('estimated_since_balance',0)+reserve
        state['last_request_epoch']=time.time();self.feed.save()
        try:code,raw,headers=self.transport(endpoint,params,read_key(cfg.twitterapi_key_file),25)
        except (OSError,TimeoutError):raise CollectionError('network','twitterapi.io: fallo de red; reserva conservada') from None
        finally:
            state['last_request_epoch']=time.time();self.feed.save()
        if code in (401,403):raise CollectionError('auth','twitterapi.io: acceso denegado',code='access_denied',http=code)
        if code in (402,429):
            retry=None;value=next((v for k,v in headers.items() if k.lower()=='retry-after'),None)
            try:retry=max(0,int(value))
            except (ValueError,TypeError):
                try:retry=max(0,int((parsedate_to_datetime(value)-at).total_seconds()))
                except (ValueError,TypeError):pass
            raise CollectionError('quota','twitterapi.io: cuota o límite',code='rate_limited' if code==429 else 'payment_required',retry_after=retry,http=code)
        if code==404 and endpoint=='/twitter/user/info':raise CollectionError('not_found','Perfil de X no encontrado',code='profile_not_found',http=404)
        if code!=200:raise CollectionError('http','twitterapi.io: respuesta HTTP no válida',http=code)
        try:data=json.loads(raw)
        except ValueError:raise CollectionError('schema','twitterapi.io: respuesta no JSON') from None
        if endpoint=='/twitter/user/info' and isinstance(data,dict) and data.get('status') in ('error','failed','fail') and any(word in str(data.get('msg','')).lower() for word in ('not found','not exist','unavailable')):
            raise CollectionError('not_found','Perfil de X no encontrado',code='profile_not_found')
        if not isinstance(data,dict) or data.get('error') or data.get('status') in ('error','failed','fail'):
            raise CollectionError('schema','twitterapi.io: error dentro de respuesta')
        if endpoint.endswith('advanced_search'):
            items=data.get('tweets')
            if not isinstance(items,list):raise CollectionError('schema','twitterapi.io: tamaño de página inesperado')
            actual=15*max(1,len(items));refund=reserve-actual
            daily[day]-=refund;monthly[month]-=refund;state['estimated_since_balance']-=refund
            if cfg.backfill:bootstrap[day]-=refund
            state['returned_posts']=state.get('returned_posts',0)+len(items)
            if len(items)>20:
                state['contract_blocked']=True;self.feed.save()
                raise CollectionError('schema','twitterapi.io: página mayor al contrato esperado; búsqueda bloqueada',code='contract_changed')
        elif endpoint=='/oapi/my/info':
            try:
                recharge=float(data['recharge_credits']);bonus=float(data['total_bonus_credits'])
                if not all(math.isfinite(v) and v>=0 for v in (recharge,bonus)):raise ValueError()
            except (KeyError,ValueError,TypeError):raise CollectionError('schema','twitterapi.io: saldo incompatible') from None
            state['balance']={'checked_at':at.isoformat(),'recharge_credits':recharge,'bonus_credits':bonus,'total_credits':recharge+bonus}
            state['estimated_since_balance']=0
        state['estimated_daily_credits']=dict(sorted(daily.items())[-40:]);state['estimated_monthly_credits']=dict(sorted(monthly.items())[-3:])
        state['estimated_backfill_daily_credits']=dict(sorted(bootstrap.items())[-40:])
        self.feed.save();return data

    def profile(self,ref):
        name=handle(ref)
        data=self.request('/twitter/user/info',{'userName':name})
        profile=data.get('data')
        if (not isinstance(profile,dict) or str(profile.get('userName','')).lower()!=name
                or not isinstance(profile.get('id'),str) or not profile['id'].isdigit()):
            raise CollectionError('schema','twitterapi.io: identidad del perfil no confirmada')
        return {'handle':name,'author_id':profile['id'],'name':str(profile.get('name') or name)[:80]}

    def fetch(self,rule,start,until,cursor):
        params={'query':f"from:{rule['handle']} since_time:{int(start.timestamp())} until_time:{int(until.timestamp())}",'queryType':'Latest'}
        if cursor:params['cursor']=cursor
        return page(self.request('/twitter/tweet/advanced_search',params),rule,start,until,cursor)
