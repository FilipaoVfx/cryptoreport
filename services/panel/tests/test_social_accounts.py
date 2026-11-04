"""Catalog administration: real HTTP auth and disk effects; provider is a fixture."""
import copy
from datetime import timedelta
import fcntl
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import crpanel
import social_accounts as social
from crsocial.config import load_config,load_catalog
from crsocial.feed import Feed,now_utc,atomic
from crsocial.twitterapi import configure


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.catalog=self.root/'accounts.json';atomic(self.catalog,{'version':1,'accounts':[{'handle':'one','author_id':'10','lookback_days':3,'name':'One','label':'Cripto'}]})
        env={'CR_SOCIAL_ACCOUNTS':str(self.catalog),'CR_SOCIAL_DATA_DIR':str(self.root/'private'),'CR_MOBILE_DATA_DIR':str(self.root/'public'),
             'CR_SOCIAL_TWITTERAPI_KEY_FILE':str(self.root/'key.json'),'CR_SOCIAL_ENV_FILE':'/not-used'}
        self.env=patch.dict(os.environ,env);self.env.start();self.addCleanup(self.env.stop)
        configure(self.root/'key.json','test_key_1234567890123456')
        self.audit=patch('social_accounts.admin.audit');self.audit.start();self.addCleanup(self.audit.stop)
        self.sleep=patch('crsocial.twitterapi.time.sleep');self.sleep.start();self.addCleanup(self.sleep.stop)

    def preview(self):
        with patch('crsocial.twitterapi.http_request',return_value=(200,json.dumps({'status':'success','data':{'userName':'two','id':'20','name':'Two'}}),{})):
            return social.preview('https://x.com/two')

    def body(self):
        p=self.preview()
        return dict(handle='two',name='Two',label='Cripto',lookback_days=3,enabled=True,preview_token=p['preview_token'],revision=social.listing()['revision'])

    def test_verified_add_survives_restart_and_enters_next_cycle(self):
        body=self.body();body['author_id']='999';social.save(body)
        cfg=load_config();self.assertEqual([a['handle'] for a in cfg.accounts],['one','two'])
        f=Feed(cfg);self.assertIn('two',f.state['refresh_accounts'])
        self.assertEqual(f.state['monthly'][now_utc().strftime('%Y-%m')],1)
        # Forged client IDs cannot change the identity returned by the provider.
        self.assertEqual(cfg.accounts[1]['author_id'],'20')
        with self.assertRaises(social.SocialError):social.save(body)
        self.assertEqual(len(load_catalog(self.catalog)),2)

    def test_unverified_expired_or_wrong_profile_cannot_write(self):
        original=self.catalog.read_bytes();b=self.body();b['handle']='other'
        with self.assertRaises(social.SocialError):social.save(b)
        b['handle']='two';f=Feed(load_config());f.state['account_previews'][b['preview_token']]['expires_at']=(now_utc()-timedelta(seconds=1)).isoformat();f.save()
        with self.assertRaises(social.SocialError):social.save(b)
        self.assertEqual(original,self.catalog.read_bytes())

    def test_invalid_window_and_stale_revision_do_not_change_catalog(self):
        b=self.body();original=self.catalog.read_bytes()
        for days in (0,31,True,'3'):
            b['lookback_days']=days
            with self.assertRaises(social.SocialError):social.save(b)
        self.assertEqual(original,self.catalog.read_bytes())

    def test_nonexistent_profile_does_not_disable_the_feed_provider(self):
        with patch('crsocial.twitterapi.http_request',return_value=(404,'{}',{})):
            with self.assertRaises(social.SocialError) as exc:social.preview('notfound')
        self.assertEqual(exc.exception.http,422)
        self.assertNotEqual(Feed(load_config()).state['providers']['twitterapi-io'].get('status'),'cooldown')
        self.assertEqual(len(load_catalog(self.catalog)),1)

    def test_disable_purges_then_reenable_and_larger_window_queue_full_recovery(self):
        b=self.body();social.save(b);cfg=load_config();f=Feed(cfg);at=now_utc()
        f.merge([{'id':'123','text':'Bitcoin: liquidez institucional.', 'published_at':(at-timedelta(hours=1)).isoformat(),
            'author_id':'20','author_handle':'two','source_account':'two','belongs_to_requested_account':True}],at);f.save()
        row=dict(b,enabled=False,revision=social.listing()['revision']);social.save(row)
        self.assertNotIn('123',Feed(load_config()).state['posts'])
        row.update(enabled=True,lookback_days=10,revision=social.listing()['revision']);social.save(row)
        self.assertIn('two',Feed(load_config()).state['refresh_accounts'])
        self.assertFalse(Feed(load_config()).state['accounts']['two'].get('sources'))

    def test_busy_extraction_prevents_admin_write(self):
        b=self.body();cfg=load_config()
        with (cfg.data/'run.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(social.SocialError) as exc:social.save(b)
            self.assertEqual(exc.exception.http,409)
        self.assertEqual(len(load_catalog(self.catalog)),1)

    def test_http_auth_and_csrf_are_enforced_before_action(self):
        server=crpanel.ThreadingHTTPServer(('127.0.0.1',0),crpanel.Handler);old=crpanel.Handler.token;crpanel.Handler.token='test-admin'
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for headers,expected in (({},403),({'X-Panel':'1'},401)):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port)
                c.request('POST','/test-admin/api/social/accounts',body='{}',headers=headers)
                r=c.getresponse();self.assertEqual(r.status,expected);r.read();c.close()
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('GET','/test-admin/api/social/accounts')
            r=c.getresponse();self.assertEqual(r.status,401);r.read();c.close()
            self.assertEqual(len(load_catalog(self.catalog)),1)
        finally:server.shutdown();server.server_close();crpanel.Handler.token=old;thread.join()


if __name__=='__main__':unittest.main()
