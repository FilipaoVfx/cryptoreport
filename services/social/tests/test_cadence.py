"""Replay the deployed worker settings: timely polling within the spend guard."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from crsocial.config import SERVICE,load_config
from crsocial.feed import Feed


class CadenceTests(unittest.TestCase):
    def config(self,root):
        # Replay the actual unit's overrides, not only load_config defaults.
        env={}
        for line in (SERVICE/'ops/cryptoreport-social.service').read_text().splitlines():
            if line.startswith('Environment='):
                key,value=line.removeprefix('Environment=').split('=',1);env[key]=value
        with patch.dict(os.environ,env,clear=True):cfg=load_config()
        return replace(cfg,data=root/'private',public=root/'public',env_file='/not-used',providers=('scraper',),twitterapi_key_file=None)

    def test_deployed_worker_polls_at_three_hours_and_not_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.config(Path(tmp));calls=[]
            at=datetime(2026,10,16,tzinfo=timezone.utc)
            def transport(*args):calls.append(1);return 200,'{"timeline":[],"next_cursor":null}',{}
            first=Feed(cfg).run(at,transport=transport,key='fixture')
            Feed(cfg).run(at+timedelta(hours=2,minutes=45),transport=transport,key='fixture')
            self.assertEqual(len(calls),len(cfg.accounts))
            result=Feed(cfg).run(at+timedelta(hours=3),transport=transport,key='fixture')
            self.assertEqual(len(calls),2*len(cfg.accounts),'Cron must fetch new posts after 3 h rather than wait 12 h')
            self.assertEqual(first['next_attempt_after'],(at+timedelta(hours=3)).isoformat())
            self.assertEqual(result['health']['poll_interval_hours'],3)

    def test_normal_allowance_sustains_all_daily_heads_and_pending_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.config(Path(tmp));rules={a['handle']:a for a in cfg.accounts};clock=None;calls=[]
            at=datetime(2026,10,16,tzinfo=timezone.utc)
            def transport(endpoint,params,*args):
                calls.append(dict(params))
                if params.get('cursor'):return 200,'{"timeline":[],"next_cursor":null}',{}
                name=params['query'].split('from:',1)[1].split()[0];rule=rules[name]
                payload={'timeline':[{'tweet_id':str(10000+len(calls)),'text':'Bitcoin: liquidez y flujos institucionales.',
                    'created_at':(clock-timedelta(minutes=10)).isoformat(),
                    'author':{'rest_id':rule['author_id'],'screen_name':name}}],'next_cursor':'tail'}
                return 200,json.dumps(payload),{}
            for hour in range(0,24,3):
                clock=at+timedelta(hours=hour)
                Feed(cfg).run(clock,transport=transport,key='fixture')
                Feed(cfg).run(clock+timedelta(minutes=15),transport=transport,key='fixture')
            feed=Feed(cfg);result=feed.publish(clock+timedelta(minutes=15))
            self.assertEqual(len(calls),16*len(cfg.accounts),'All eight daily polls and their tails must fit the normal allowance')
            self.assertIsNone(result['last_error'])
            self.assertFalse(any(s.get('pending') for a in feed.state['accounts'].values() for s in a.get('sources',{}).values()))
            self.assertEqual(cfg.twitterapi_daily_credits,12000)
            self.assertEqual(cfg.twitterapi_monthly_credits,60000)
            self.assertLessEqual(16*len(cfg.accounts)*31+31,cfg.monthly_calls)


if __name__=='__main__':unittest.main()
