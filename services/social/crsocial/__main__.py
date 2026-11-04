"""python -m crsocial run|import-corpus|export|status. Never calls a model."""
import argparse
import fcntl
import json
from .config import load_config
from .feed import Feed, now_utc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','backfill','balance','import-corpus','export','status','semantic-export','semantic-solve','configure-x','configure-twitterapi','health'])
    parser.add_argument('--corpus')
    parser.add_argument('--jobs',type=int,default=1,help='Trabajos semánticos por ejecución (semantic-solve)')
    args=parser.parse_args()
    if args.command=='import-corpus' and not args.corpus:
        parser.error('--corpus requerido')
    if args.command=='semantic-solve' and not 1<=args.jobs<=3:
        parser.error('--jobs debe estar entre 1 y 3')
    cfg=load_config();cfg.data.mkdir(parents=True,exist_ok=True)
    if args.command=='configure-twitterapi':
        from .twitterapi import configure
        configure(cfg.twitterapi_key_file)
    if args.command=='backfill':
        cfg.backfill=True;cfg.max_calls=40
    if args.command=='configure-x':
        from .x_session import configure
        try:print(json.dumps(configure(cfg.x_session),ensure_ascii=False))
        except (OSError,ValueError,EOFError):
            print('{"status":"error","detail":"Sesión no guardada; usa una exportación válida en la terminal."}')
            return 1
    with (cfg.data/'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"status":"busy"}');return 0
        try:
            # The catalog can change between initial configuration and taking
            # run.lock. Read it again under the lock before pruning or fetching.
            cfg=load_config()
            if args.command=='backfill':cfg.backfill=True;cfg.max_calls=40
            feed=Feed(cfg)
            if args.command=='configure-twitterapi':
                feed.state.setdefault('providers',{})['twitterapi-io']={'status':'needs_credentials','configured':False}
                feed.save()
            if args.command=='balance':
                from .providers import Providers
                from .collector import CollectionError
                hub=Providers(feed,now_utc())
                try:hub.twitterapi.request('/oapi/my/info',{})
                except CollectionError as exc:
                    print(json.dumps({'status':'error','error':exc.public()}));return 1
            if args.command=='configure-x':
                feed.state.setdefault('providers',{})['agent-reach']={'status':'needs_credentials','configured':False}
                feed.save()
            if args.command=='import-corpus':
                from pathlib import Path
                feed.seed(json.loads(Path(args.corpus).read_text()),now_utc())
            pending=args.command=='backfill' and any(src.get('pending') for s in feed.state['accounts'].values() for src in s.get('sources',{}).values())
            result=feed.run(force=args.command=='backfill' and not pending and not feed.state.get('refresh_accounts'),recovery_only=bool(pending)) if args.command in ('run','backfill') else feed.publish()
            if args.command=='health':print(json.dumps(result['health'],ensure_ascii=False))
            if args.command=='semantic-export':
                from .scheduled import run
                semantic=run(feed)
                print(json.dumps({k:v for k,v in semantic.items() if k!='connections'},ensure_ascii=False))
            if args.command=='semantic-solve':
                # Inferencia por suscripción: el puente revalida y publica aparte.
                from .semantic_local import run as solve
                print(json.dumps(solve(feed,limit=args.jobs),ensure_ascii=False))
            if args.command!='status':
                feed.save()
            print(json.dumps({k:result[k] for k in ('status','generated_at','last_attempt','next_attempt_after','budget','model_api_enabled')} | {'posts':len(result['posts'])},ensure_ascii=False))
            return 0
        except (OSError,ValueError,KeyError,TypeError) as error:
            print(json.dumps({'status':'error','detail':type(error).__name__,'action':'Revisar estado/configuración; presupuesto no reiniciado'}))
            return 1


if __name__=='__main__':
    raise SystemExit(main())
