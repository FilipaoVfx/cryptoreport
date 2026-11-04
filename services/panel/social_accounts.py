"""Authenticated panel actions for the social catalog; collector shares the lock."""
from contextlib import contextmanager
from datetime import timedelta
import fcntl
import hashlib
import json
import sys
import uuid
import admin
import content

sys.path.insert(0,str(content.REPO/'services/social'))
from crsocial.config import load_config,load_catalog
from crsocial.collector import CollectionError,handle
from crsocial.feed import Feed,atomic,instant,now_utc
from crsocial.providers import Providers


class SocialError(ValueError):
    def __init__(self,message,http=422):super().__init__(message);self.http=http


def revision(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


@contextmanager
def locked():
    cfg=load_config();cfg.data.mkdir(parents=True,exist_ok=True)
    with (cfg.data/'run.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SocialError('Hay una extracción en curso. Vuelve a intentarlo al terminar.',409) from None
        yield load_config()


def listing():
    cfg=load_config();rows=load_catalog(cfg.accounts_file)
    return {'accounts':rows,'revision':revision(rows),'poll_interval_hours':cfg.interval_hours,
            'max_accounts':16,'monthly_credit_limit':cfg.twitterapi_monthly_credits}


def preview(ref):
    try:
        with locked() as cfg:
            feed=Feed(cfg);hub=Providers(feed,now_utc())
            if not hub.available('twitterapi-io'):raise SocialError('twitterapi.io no está disponible; revisa el monitor.',503)
            try:profile=hub.twitterapi.profile(ref)
            except CollectionError as exc:
                if exc.kind in ('auth','quota','network') or (exc.http or 0)>=500:hub.failure('twitterapi-io',exc.public())
                feed.save();raise SocialError(str(exc),422 if exc.kind=='not_found' else 503) from None
            now=now_utc();token=uuid.uuid4().hex
            cached={k:v for k,v in feed.state.get('account_previews',{}).items() if instant(v['expires_at'])>now}
            cached=dict(list(cached.items())[-15:])
            cached[token]=dict(profile,expires_at=(now+timedelta(minutes=15)).isoformat())
            feed.state['account_previews']=cached;feed.save()
            exists=any(a['handle']==profile['handle'] for a in load_catalog(cfg.accounts_file))
            return dict(profile,preview_token=token,exists=exists)
    except (TypeError,ValueError) as exc:
        if isinstance(exc,SocialError):raise
        raise SocialError('URL o perfil inválido; usa una cuenta de x.com o @handle.') from None


def save(data):
    with locked() as cfg:
        rows=load_catalog(cfg.accounts_file)
        if data.get('revision')!=revision(rows):raise SocialError('La lista cambió. Recarga antes de guardar.',409)
        try:
            if not isinstance(data.get('handle'),str):raise ValueError()
            name=handle(data['handle'])
        except (KeyError,TypeError,ValueError):raise SocialError('Cuenta inválida') from None
        old=next((r for r in rows if r['handle']==name),None)
        days=data.get('lookback_days');enabled=data.get('enabled',True)
        if type(days) is not int or not 1<=days<=30 or type(enabled) is not bool:raise SocialError('Ventana de 1 a 30 días y estado válidos requeridos')
        feed=Feed(cfg)
        if old:identity=old
        else:
            if len(rows)>=16:raise SocialError('Se permiten como máximo 16 cuentas')
            token=data.get('preview_token')
            if not isinstance(token,str) or len(token)>64:raise SocialError('Comprueba el perfil antes de añadirlo.')
            identity=feed.state.get('account_previews',{}).get(token)
            if not identity or identity.get('handle')!=name or instant(identity['expires_at'])<=now_utc():
                raise SocialError('Comprueba el perfil antes de añadirlo; la comprobación dura quince minutos.')
            if any(r['author_id']==identity['author_id'] for r in rows):raise SocialError('Esta identidad ya está registrada con otro handle')
        row={'handle':name,'author_id':identity['author_id'],'name':data.get('name',identity.get('name',name)),
             'label':data.get('label','Cripto'),'lookback_days':days,'enabled':enabled}
        for field,limit in (('name',80),('label',40)):
            text=row[field]
            if not isinstance(text,str) or not text.strip() or len(text)>limit or any(ord(c)<32 for c in text):raise SocialError('Nombre o categoría inválidos')
            row[field]=text.strip()
        updated=[row if r['handle']==name else r for r in rows] if old else rows+[row]
        refresh=enabled and (not old or not old['enabled'] or days>old['lookback_days'])
        pending=set(feed.state.get('refresh_accounts',[]))
        if refresh:
            # Rebuild the full newly authorized window; an old checkpoint cannot
            # prove coverage of the older days that have just been added.
            feed.state['accounts'][name]={'status':'pending','retrieval_exhausted':False}
            pending.add(name)
        if not enabled:pending.discard(name)
        feed.state['refresh_accounts']=sorted(pending)
        feed.state['catalog_updated_at']=now_utc().isoformat()
        if data.get('preview_token'):feed.state.get('account_previews',{}).pop(data['preview_token'],None)
        # Persist the recovery intent first: a crash before catalog publication
        # leaves safe redundant work, never an account without a queued first read.
        feed.save();atomic(cfg.accounts_file,{'version':1,'accounts':updated})
        published=Feed(load_config()).publish()
    admin.audit('social.account.saved','x:'+name,detail={'lookback_days':days,'enabled':enabled,'new':old is None})
    return dict(listing(),ok=True,message='Cuenta guardada. La ingesta entra en el próximo ciclo (hasta quince minutos).' if enabled else 'Cuenta desactivada; sus posts se retiraron del Feed.',posts=len(published['posts']))
