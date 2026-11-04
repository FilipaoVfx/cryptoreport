"""Durable bounded feed. State is a small JSON file, separate from video queues."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from .collector import Client, CollectionError, credential
from .quality import classify, VERSION as QUALITY_VERSION


def now_utc():
    return datetime.now(timezone.utc)


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Fecha sin zona horaria')
    return parsed.astimezone(timezone.utc)


def atomic(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.social-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(obj, stream, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def safe_url(value, avatar=False):
    try:
        u = urlsplit(value or '')
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None,443):
            return None
        if avatar and u.hostname != 'pbs.twimg.com':
            return None
        return value
    except (ValueError, TypeError):
        return None


class Feed:
    def __init__(self, config):
        self.config = config
        self.path = config.data / 'state.json'
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state.get('version') != 1:
                raise ValueError('Estado social incompatible; no se reinicia el presupuesto')
        else:
            self.state = {'version':1, 'posts':{}, 'accounts':{}, 'daily':{}, 'monthly':{}, 'conflicts':0}
        self.accounts = {a['handle']:a for a in config.accounts}
        if 'provider_usage' not in self.state:
            # Before multi-provider support every reserved operation used Scraper.tech.
            self.state['provider_usage']={'scraper':{'daily':dict(self.state['daily']),'monthly':dict(self.state['monthly'])}}
        if not 1 <= config.max_calls <= 100 or not 1 <= config.daily_calls <= config.monthly_calls <= 10000 or not 1<=config.interval_hours<=24:
            raise ValueError('Presupuesto social inválido')

    def save(self):
        atomic(self.path,self.state)

    def reserve(self, at, provider='scraper'):
        day, month = at.date().isoformat(), at.strftime('%Y-%m')
        bootstrap=self.state.setdefault('backfill_daily',{})
        normal=self.state['daily'].get(day,0)-bootstrap.get(day,0)
        if ((bootstrap.get(day,0)>=40 if self.config.backfill else normal>=self.config.daily_calls)
                or self.state['monthly'].get(month,0) >= self.config.monthly_calls):
            raise CollectionError('budget','Límite diario o mensual de X alcanzado')
        if self.config.backfill:bootstrap[day]=bootstrap.get(day,0)+1
        self.state['daily'][day] = self.state['daily'].get(day,0)+1
        self.state['monthly'][month] = self.state['monthly'].get(month,0)+1
        usage=self.state.setdefault('provider_usage',{}).setdefault(provider,{'daily':{},'monthly':{}})
        for bucket,key in (('daily',day),('monthly',month)):
            usage[bucket][key]=usage[bucket].get(key,0)+1
        usage['daily']={k:v for k,v in usage['daily'].items() if k >= (at-timedelta(days=40)).date().isoformat()}
        usage['monthly']=dict(sorted(usage['monthly'].items())[-3:])
        self.state['daily'] = {k:v for k,v in self.state['daily'].items() if k >= (at-timedelta(days=40)).date().isoformat()}
        self.state['monthly'] = dict(sorted(self.state['monthly'].items())[-3:])
        self.save()  # Reserve before the request; crashes must not reset spend.

    def merge(self, posts, at):
        kept = changed = rejected = 0
        for raw in posts:
            try:
                account = str(raw.get('source_account') or raw.get('author_handle') or '').lower()
                rule = self.accounts[account]
                published = instant(raw['published_at'])
                if (str(raw.get('author_handle','')).lower() != account or raw.get('author_id') != rule['author_id']
                        or raw.get('belongs_to_requested_account') is not True
                        or not at-timedelta(days=rule['lookback_days']) < published < at
                        or not isinstance(raw['id'],str) or not raw['id'].isdigit()
                        or not isinstance(raw['text'],str) or not raw['text'].strip() or len(raw['text']) > 50000):
                    raise ValueError('Identidad, ventana o texto inválido')
                old = self.state['posts'].get(raw['id'])
                if old and old['author_id'] != raw['author_id']:
                    self.state['conflicts'] += 1
                    raise ValueError('Conflicto de identidad')
                p = {k:raw.get(k) for k in ('id','text','published_at','fetched_at','author_id','language','conversation_id','is_reply','is_quote','is_repost','text_completeness','ingest_provider')}
                p['published_at']=published.isoformat()
                p.update(author_handle=account, source_account=account, url=f"https://x.com/i/web/status/{p['id']}",
                         expires_at=(published+timedelta(days=rule['lookback_days'])).isoformat(),
                         author_name=rule.get('name',account), avatar_url=safe_url(raw.get('avatar_url'),avatar=True),
                         links=[url for url in (raw.get('links') or []) if isinstance(url,str) and safe_url(url)],
                         has_media=bool(raw.get('has_media') or raw.get('media')), externally_verified=False)
                p['content_hash'] = hashlib.sha256((p['author_id']+'\n'+p['published_at']+'\n'+p['text']).encode()).hexdigest()
                if old and old['content_hash'] != p['content_hash']:
                    changed += 1
                if not old:
                    kept += 1
                if old and not p['avatar_url']:
                    p['avatar_url'] = old.get('avatar_url')
                self.state['posts'][p['id']] = p  # Current version only; changed hash invalidates future links.
            except (ValueError,TypeError,KeyError):
                rejected += 1
        self.prune(at)
        return {'added':kept,'changed':changed,'rejected':rejected}

    def prune(self, at):
        previous_ids = set(self.state['posts'])
        kept={}
        counts={}
        for p in sorted(self.state['posts'].values(),key=lambda p:(p['published_at'],int(p['id'])),reverse=True):
            h=p['author_handle'];rule=self.accounts.get(h)
            if not rule or p['author_id'] != rule['author_id'] or not at-timedelta(days=rule['lookback_days']) < instant(p['published_at']) < at:
                continue
            counts[h]=counts.get(h,0)+1
            if counts[h]<=self.config.max_posts_per_account:
                p['expires_at']=(instant(p['published_at'])+timedelta(days=rule['lookback_days'])).isoformat()
                kept[p['id']]=p
        self.state['posts']=kept
        for h,status in self.state['accounts'].items():
            if h not in self.accounts:continue
            cutoff=at-timedelta(days=self.accounts[h]['lookback_days'])
            for src in [status,*status.get('sources',{}).values()]:
                if src.get('pending') and instant(src['pending']['until_at'])<=cutoff:src.pop('pending',None)
        removed = len(previous_ids - set(kept))
        retention = self.state.setdefault('retention', {})
        retention.update(checked_at=at.isoformat(), removed_total=retention.get('removed_total', 0)+removed)
        if removed:
            retention.update(last_removal_at=at.isoformat(), last_removed=removed)

    def prune_references(self, at):
        """Remove managed local corpora and links whose exact source no longer exists.

        No provider, Drive or model access. Budget counters and video sources are untouched.
        The CLI and bridge already hold run.lock when publishing.
        """
        posts = self.state['posts']
        def current(p):
            source = posts.get(p.get('post_id', p.get('id')))
            return bool(source and p.get('post_content_hash', p.get('content_hash')) == source['content_hash'])
        links_path = self.config.public/'social-connections.json'
        if links_path.is_file() and not links_path.is_symlink():
            links = json.loads(links_path.read_text())
            original = links.get('connections', [])
            kept = []
            for c in original:
                try:
                    if current(c) and instant(c['expires_at']) > at:
                        kept.append(c)
                except (ValueError, KeyError, TypeError):
                    pass
            if len(kept) != len(original):
                links.update(connections=kept, coverage_complete=False, retention_checked_at=at.isoformat())
                if not kept and links.get('status') == 'ok':
                    links['status'] = 'pending_schedule'
                atomic(links_path, links)
        root = self.config.data/'semantic'
        if not root.is_dir() or root.is_symlink():
            return
        managed = re.compile(r'semantic-[a-f0-9]{64}')
        valid = set()
        windows = {h: a['lookback_days'] for h, a in self.accounts.items()}
        for path in root.glob('semantic-*.json'):
            if path.is_symlink() or not managed.fullmatch(path.stem):
                continue
            try:
                job = json.loads(path.read_text())
                ok = (instant(job['expires_at']) > at
                      and {a['handle']: a['lookback_days'] for a in job['accounts']} == windows
                      and all(current(p) for p in job['corpus']['posts']))
            except (ValueError, KeyError, TypeError):
                ok = False
            if ok:
                valid.add(path.stem)
            else:
                path.unlink()
        for path in root.glob('semantic-*.semantic'):
            if not path.is_symlink() and managed.fullmatch(path.stem) and path.stem not in valid:
                path.unlink()

    def seed(self, corpus, at):
        result=self.merge(corpus['posts'],at)
        for row in corpus.get('accounts',[]):
            account=row.get('account','').lower()
            if account not in self.accounts:
                continue
            status=self.state['accounts'].setdefault(account,{})
            source_asof=instant(corpus['as_of'])
            if source_asof > at:
                raise ValueError('Corpus futuro')
            if status.get('last_success') and instant(status['last_success'])>=source_asof:
                continue
            status.update(last_success=source_asof.isoformat(), status='importado', retrieval_exhausted=bool(row.get('retrieval_exhausted')), last_error=None)
            if row.get('retrieval_exhausted'):
                status['checkpoint']=source_asof.isoformat()
        self.save();self.publish(at)
        return result

    def run(self, at=None, transport=None, key=None, force=False, recovery_only=False):
        from .providers import Providers
        at=at or now_utc()
        self.prune(at)
        if not self.config.providers or len(set(self.config.providers))!=len(self.config.providers) or any(p not in ('twitterapi-io','scraper','agent-reach') for p in self.config.providers):
            raise ValueError('Proveedores sociales inválidos')
        hub=Providers(self,at,transport,key)
        self.state['last_dispatch_at']=at.isoformat()
        self.state['last_dispatch_requests']=0
        if not self.accounts:
            self.save();return self.publish(at)
        refresh_accounts=set(self.state.get('refresh_accounts',[]))&set(self.accounts)
        retry_due=any(s.get('retry_at') and instant(s['retry_at'])<=at for s in hub.states.values())
        newly_ready=any(hub.ready(p) and hub.states.get(p,{}).get('status')=='needs_credentials' for p in self.config.providers)
        last=self.state.get('last_poll_at',self.state.get('last_attempt'))
        poll_due=not recovery_only and (force or not last or at-instant(last)>=timedelta(hours=self.config.interval_hours))
        recovery_due=recovery_only or any(src.get('pending') and (not src.get('last_page_at') or at-instant(src['last_page_at'])>=timedelta(hours=1))
                         for s in self.state['accounts'].values() for src in s.get('sources',{}).values())
        if not poll_due and not retry_due and not newly_ready and not recovery_due and not refresh_accounts:
            self.save();return self.publish(at)
        if poll_due:self.state['last_poll_at']=at.isoformat()
        self.state['last_attempt']=at.isoformat();self.save()
        errors=[]
        balance_at=self.state.get('twitterapi',{}).get('balance',{}).get('checked_at')
        if poll_due and 'twitterapi-io' in self.config.providers and hub.available('twitterapi-io') and (not balance_at or at-instant(balance_at)>=timedelta(hours=24)):
            try:hub.twitterapi.request('/oapi/my/info',{})
            except CollectionError as exc:
                errors.append(exc.public())
                if exc.kind!='budget':hub.failure('twitterapi-io',exc.public())
        jobs=[]
        active={}
        def source(status,name):
            sources=status.setdefault('sources',{})
            if name not in sources:
                # Legacy cursor belongs only to Scraper.tech. A timestamp may be
                # shared across sources, never a provider's opaque cursor.
                sources[name]={k:status[k] for k in ('checkpoint','pending','last_page_at') if k in status and name!='twitterapi-io' and (name=='scraper' or k=='checkpoint')}
            return sources[name]
        def observe(rule,name,result,start,until,head,attempted=True):
            h=rule['handle'];status=self.state['accounts'].setdefault(h,{})
            src=source(status,name)
            fingerprint=result.get('page_fingerprint')
            seen=src.get('pending',{}).get('page_fingerprints',[]) if not head else []
            if fingerprint and fingerprint in seen:
                result=dict(result,error={'kind':'cursor_loop','detail':'Página repetida; ventana sin confirmar'})
            current=[];expired=0
            for post in result['posts']:
                try:aged_out=instant(post['published_at'])<=at-timedelta(days=rule['lookback_days'])
                except (KeyError,ValueError,TypeError,AttributeError):aged_out=False
                if aged_out:expired+=1
                else:current.append(dict(post,source_account=h))
            merged=self.merge(current,at)
            error=result['error']
            if not error and (result['rejected'] or merged['rejected']):error={'kind':'schema','detail':'Publicaciones rechazadas; ventana sin confirmar'}
            if not error and result['stop_reason']=='cursor_loop':error={'kind':'cursor_loop','detail':'Cursor repetido; ventana sin confirmar'}
            if not error:
                status.update(last_success=at.isoformat(),last_error=None,provider=name,status='partial',retrieval_exhausted=False)
                if head:status['last_head_success']=at.isoformat()
                src['last_success']=at.isoformat()
                if result['stop_reason'] in ('cursor_exhausted','empty_page'):
                    src['checkpoint']=until.isoformat();src.pop('pending',None)
                    # Another provider can recover the same time window, but its
                    # opaque cursor is never used. Retire only fully covered work.
                    for other in status['sources'].values():
                        pending=other.get('pending')
                        if pending and start<=instant(pending['since_at']) and until>=instant(pending['until_at']):other.pop('pending',None)
                    status.update(checkpoint=until.isoformat(),status='ok' if not any(s.get('pending') for s in status['sources'].values()) else 'partial',retrieval_exhausted=until==at)
                elif result['next_cursor']:
                    # A new head includes the oldest pending start. Replace its window
                    # as a whole; completing an older cursor must never hide a new gap.
                    src['pending']={'since_at':start.isoformat(),'until_at':until.isoformat(),'cursor':result['next_cursor'],
                                    'page_fingerprints':(seen+[fingerprint])[-100:] if fingerprint else seen}
                status.pop('pending',None)
                if src.get('pending'):status['pending']=dict(src['pending'],provider=name)
            else:
                status.update(last_error=error,status='partial',retrieval_exhausted=False)
                if not result.get('error'):hub.failure(name,error)
            src['last_error']=error
            event={'at':at.isoformat(),'account':h,'provider':name,'stage':'head' if head else 'recovery','outcome':'error' if error else 'ok',
                   'error_code':(error or {}).get('code',(error or {}).get('kind')),'added':merged['added'],'changed':merged['changed'],'rejected':len(result['rejected'])+merged['rejected'],
                   'expired_during_recovery':expired}
            if result.get('page_stats'):event['page_stats']=result['page_stats']
            if attempted:
                self.state['events']=(self.state.get('events',[])+[event])[-200:]
                stats=self.state.setdefault('pilot',{'started_at':at.isoformat(),'successes':0,'failures':0})
                stats['failures' if error else 'successes']+=1
            self.save()
            return error
        order=sorted(self.accounts.values(),key=lambda a:self.state['accounts'].get(a['handle'],{}).get('last_success',''))
        for rule in order:
            h=rule['handle'];status=self.state['accounts'].setdefault(h,{})
            if refresh_accounts and not poll_due and h not in refresh_accounts:
                for name,src in status.get('sources',{}).items():
                    if src.get('pending') and name in self.config.providers:jobs.append((rule,name,src['pending']))
                continue
            if h not in refresh_accounts and recovery_due and not poll_due and (recovery_only or not retry_due and not newly_ready
                    or status.get('last_head_success') and at-instant(status['last_head_success'])<timedelta(hours=self.config.interval_hours)):
                for name,src in status.get('sources',{}).items():
                    if src.get('pending') and name in self.config.providers:jobs.append((rule,name,src['pending']))
                continue
            if h not in refresh_accounts and not poll_due and not newly_ready and status.get('status')=='ok' and status.get('last_success') and at-instant(status['last_success'])<timedelta(hours=self.config.interval_hours):continue
            last_error=None
            for name in self.config.providers:
                if not hub.available(name):continue
                src=source(status,name);start=at-timedelta(days=rule['lookback_days'])
                if src.get('checkpoint'):start=max(start,instant(src['checkpoint'])-timedelta(hours=1))
                outstanding=[instant(s['pending']['since_at']) for s in status.get('sources',{}).values() if s.get('pending')]
                if outstanding:start=max(at-timedelta(days=rule['lookback_days']),min(start,*outstanding))
                before=hub.calls
                result=hub.fetch(name,rule,start,at)
                if hub.calls>before:status['last_attempt']=at.isoformat()
                last_error=observe(rule,name,result,start,at,True,hub.calls>before)
                if not last_error:
                    self.state['refresh_accounts']=[x for x in self.state.get('refresh_accounts',[]) if x!=h]
                    active[h]=name
                    if src.get('pending'):jobs.append((rule,name,src['pending']))
                    break
                if last_error['kind']=='budget':break
            if h not in active:
                error=last_error or next((s['last_error'] for s in hub.states.values() if s.get('last_error')),{'kind':'auth','code':'needs_credentials','detail':'Sin proveedor configurado y disponible'})
                status.update(last_error=error,status='partial',retrieval_exhausted=False)
                errors.append(error)
        # Head page for every account first; then spend the remaining bounded calls on pagination.
        jobs.sort(key=lambda job:self.state['accounts'][job[0]['handle']]['sources'][job[1]].get('last_page_at',''))
        while jobs and hub.calls<self.config.max_calls:
            rule,name,pending=jobs.pop(0)
            if not hub.available(name):continue
            status=self.state['accounts'][rule['handle']];src=source(status,name)
            start,until=instant(pending['since_at']),instant(pending['until_at'])
            result=hub.fetch(name,rule,start,until,pending['cursor'])
            src['last_page_at']=status['last_page_at']=at.isoformat()
            error=observe(rule,name,result,start,until,False)
            if error:errors.append(error)
            elif src.get('pending'):jobs.append((rule,name,src['pending']))
            if error and error['kind']=='budget':break
        for name in self.config.providers:hub.available(name)
        self.state['last_requests']=hub.calls
        self.state['last_dispatch_requests']=hub.calls
        self.state['last_error']=errors[0] if errors else None
        self.save();return self.publish(at)

    def publish(self,at=None):
        from .health import summarize
        at=at or now_utc();self.prune(at)
        # Older snapshots hid provider errors globally even though the account kept them.
        if not self.state.get('last_error'):
            self.state['last_error'] = next((s.get('last_error') for h, s in self.state['accounts'].items()
                                             if h in self.accounts and s.get('last_error')), None)
        # publish() is also called by the bridge: expiry must persist there too.
        self.save()
        self.prune_references(at)
        posts=[dict(p,quality=classify(p)) for p in sorted(self.state['posts'].values(),key=lambda p:(p['published_at'],int(p['id'])),reverse=True)]
        accounts=[{**a,**{k:v for k,v in self.state['accounts'].get(a['handle'],{}).items() if k in ('last_success','status','last_error','last_attempt','retrieval_exhausted','provider')},'posts':sum(p['author_handle']==a['handle'] for p in posts)} for a in self.accounts.values()]
        health=summarize(self.state,self.config.accounts,at,self.config.interval_hours)
        payload={'version':1,'generated_at':at.isoformat(),'coverage_complete':False,'status':'partial' if self.state.get('last_error') or any(a.get('status')!='ok' for a in accounts) else 'ok',
                 'accounts':accounts,'posts':posts,'last_error':self.state.get('last_error'),
                 'last_attempt':self.state.get('last_attempt'),'next_attempt_after':(instant(self.state.get('last_poll_at',self.state['last_attempt']))+timedelta(hours=self.config.interval_hours)).isoformat() if self.state.get('last_attempt') else None,
                 'last_dispatch_at':self.state.get('last_dispatch_at'),'last_dispatch_requests':self.state.get('last_dispatch_requests'),
                 'budget':{'daily_used':self.state['daily'].get(at.date().isoformat(),0),'daily_limit':self.config.daily_calls,
                           'backfill_daily_used':self.state.get('backfill_daily',{}).get(at.date().isoformat(),0),
                           'normal_daily_used':self.state['daily'].get(at.date().isoformat(),0)-self.state.get('backfill_daily',{}).get(at.date().isoformat(),0),
                           'monthly_used':self.state['monthly'].get(at.strftime('%Y-%m'),0),'monthly_limit':self.config.monthly_calls},
                 'twitterapi_budget':dict(self.state.get('twitterapi',{}),daily_limit=self.config.twitterapi_daily_credits,backfill_daily_limit=self.config.twitterapi_backfill_daily_credits,monthly_limit=self.config.twitterapi_monthly_credits,
                                         unit='estimated_credits',usd_per_100000_credits=1,billing_reconciled=False),
                 'model_api_enabled':False,
                 'health':health,'provider_usage':self.state.get('provider_usage',{}),'budget_unit':'provider_operation',
                 'retention':dict(self.state['retention']),
                 'classification':{'version':QUALITY_VERSION,'relevant':sum(p['quality']['visibility']=='relevante' for p in posts),'secondary':sum(p['quality']['visibility']=='secundario' for p in posts),'semantic_eligible':sum(p['quality']['semantic_eligible'] for p in posts)}}
        atomic(self.config.public/'social-feed.json',payload)
        atomic(self.config.data/'status.json',{k:v for k,v in payload.items() if k!='posts'})
        return payload
