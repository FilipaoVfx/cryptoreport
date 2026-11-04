"""One read-only X page through Agent Reach's pinned twitter-cli backend.

Runs in the isolated tools Python. Bypass upstream auth discovery entirely:
TwitterClient receives only the explicitly configured session. No browser reads.
"""
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crsocial.x_session import read_session


def fetch(request, client_factory=None, parser=None):
    session=read_session(request['session'])  # before importing or constructing any network client
    if client_factory is None:
        from importlib.metadata import version
        if version('twitter-cli')!='0.8.5':raise ValueError('Backend requiere nueva validación de contrato')
        from twitter_cli.client import TwitterClient
        from twitter_cli.parser import parse_timeline_response
        client_factory,parser=TwitterClient,parse_timeline_response
    client=client_factory(session['auth_token'],session['ct0'],rate_limit_config={'maxRetries':0,'maxCount':40})
    from dataclasses import asdict
    variables={'rawQuery':request['query'],'querySource':'typed_query','product':'Latest','count':40}
    if request.get('cursor'):variables['cursor']=request['cursor']
    from twitter_cli.graphql import FEATURES
    data=client._graphql_get('SearchTimeline',variables,FEATURES)
    # Upstream parser otherwise turns a missing/changed schema into an empty list.
    obj=data
    try:
        for key in ('data','search_by_raw_query','search_timeline','timeline','instructions'):obj=obj[key]
    except (KeyError,TypeError):raise ValueError('X no entregó instrucciones de timeline') from None
    if not isinstance(obj,list):raise ValueError('Timeline inválido')
    tweets,cursor=parser(data,lambda _:obj)
    if len(tweets)>100 or cursor is not None and (not isinstance(cursor,str) or len(cursor)>8192):
        raise ValueError('Página inválida')
    return {'posts':[asdict(t) for t in tweets],'next_cursor':cursor,'schema':'twitter-cli-0.8.5'}


def main():
    logging.disable(logging.CRITICAL)
    try:
        raw=sys.stdin.buffer.read(20001)
        if len(raw)>20000:raise ValueError('Petición demasiado grande')
        result=fetch(json.loads(raw))
    except Exception as exc:
        status=getattr(exc,'status_code',None)
        code=getattr(exc,'error_code','')
        kind='auth' if status in (401,403) or code=='not_authenticated' else 'quota' if status==429 or code=='rate_limited' else 'network' if status==0 else 'schema'
        # Never echo upstream error text, URLs, headers or session values.
        result={'error':{'kind':kind,'http':status,'code':'session_expired' if kind=='auth' else 'rate_limited' if kind=='quota' else 'x_unavailable',
                         'detail':'X: sesión rechazada' if kind=='auth' else 'X: consulta no completada'}}
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
