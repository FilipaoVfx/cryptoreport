"""Retention is persistent and independent of provider/Drive/model availability."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from crsocial.config import Config, SERVICE, load_accounts
from crsocial.feed import Feed, atomic


NOW = datetime(2026, 10, 16, 3, tzinfo=timezone.utc)
ACCOUNTS = [dict(handle='one', author_id='10', name='One', lookback_days=3),
            dict(handle='two', author_id='20', name='Two', lookback_days=15)]


class RetentionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.cfg = Config(root/'private', root/'public', copy.deepcopy(ACCOUNTS), '/not-read')
        self.feed = Feed(self.cfg)

    def post(self, id='123', account='one'):
        return dict(id=id, text='Bitcoin y su liquidez: condición de la tesis.',
                    author_id='10' if account == 'one' else '20', author_handle=account,
                    source_account=account, belongs_to_requested_account=True,
                    published_at=(NOW-timedelta(days=1)).isoformat())

    def seed(self):
        self.feed.merge([self.post(), self.post('456', 'two')], NOW)
        self.feed.save()

    def test_publish_physically_removes_expired_posts_and_preserves_budget(self):
        self.seed()
        self.feed.state['daily'] = {'2026-10-16': 6}
        self.feed.state['monthly'] = {'2026-10': 12}
        self.feed.save()
        result = self.feed.publish(NOW+timedelta(days=3))
        fresh = Feed(self.cfg)
        self.assertEqual(set(fresh.state['posts']), {'456'})
        self.assertEqual([p['id'] for p in result['posts']], ['456'])
        self.assertEqual(fresh.state['daily'], {'2026-10-16': 6})
        self.assertEqual(fresh.state['monthly'], {'2026-10': 12})

    def test_exact_expiry_boundary_is_removed_from_private_and_public(self):
        self.seed()
        result = self.feed.publish(NOW+timedelta(days=2))
        self.assertEqual([p['id'] for p in result['posts']], ['456'])
        self.assertNotIn('123', Feed(self.cfg).state['posts'])

    def test_shorter_policy_is_applied_without_fetching_again(self):
        self.cfg.accounts[0]['lookback_days'] = 4
        self.feed = Feed(self.cfg)
        p = self.post()
        p['published_at'] = (NOW-timedelta(days=3, hours=1)).isoformat()
        self.feed.merge([p], NOW)
        self.feed.save()
        self.cfg.accounts[0]['lookback_days'] = 3
        self.feed = Feed(self.cfg)
        self.feed.publish(NOW)
        self.assertEqual(Feed(self.cfg).state['posts'], {})

    def test_connections_and_job_corpora_cannot_outlive_their_posts(self):
        self.seed()
        root = self.cfg.data/'semantic'
        root.mkdir()
        job_id = 'semantic-'+'a'*64
        valid_id = 'semantic-'+'b'*64
        def job(post_id):
            return dict(job_id=job_id, accounts=self.cfg.accounts,
                        expires_at=(NOW+timedelta(days=10)).isoformat(),
                        corpus={'posts': [self.feed.state['posts'][post_id]]})
        atomic(root/(job_id+'.json'), job('123'))
        atomic(root/(job_id+'.semantic'), {'responses': [{'post_quote': 'stale text'}]})
        atomic(root/(valid_id+'.json'), job('456'))
        atomic(root/(valid_id+'.semantic'), {'responses': []})
        def connection(post_id):
            return dict(post_id=post_id, post_content_hash=self.feed.state['posts'][post_id]['content_hash'],
                        expires_at=(NOW+timedelta(days=10)).isoformat(), post_quote='text')
        atomic(self.cfg.public/'social-connections.json', dict(status='ok', coverage_complete=True,
               connections=[connection('123'), connection('456')]))
        self.feed.publish(NOW+timedelta(days=3))
        self.assertFalse((root/(job_id+'.json')).exists())
        self.assertFalse((root/(job_id+'.semantic')).exists())
        self.assertTrue((root/(valid_id+'.json')).exists())
        self.assertTrue((root/(valid_id+'.semantic')).exists())
        links = json.loads((self.cfg.public/'social-connections.json').read_text())
        self.assertEqual([c['post_id'] for c in links['connections']], ['456'])
        self.assertFalse(links['coverage_complete'])

    def test_edited_post_invalidates_connections_without_a_semantic_run(self):
        self.seed()
        atomic(self.cfg.public/'social-connections.json', dict(status='ok', connections=[dict(
            post_id='123', post_content_hash='superseded', expires_at=(NOW+timedelta(days=1)).isoformat())]))
        self.feed.publish(NOW)
        self.assertEqual(json.loads((self.cfg.public/'social-connections.json').read_text())['connections'], [])

    def test_maintenance_during_cooldown_never_contacts_provider(self):
        self.seed()
        at = NOW+timedelta(days=3)
        self.feed.state['last_attempt'] = (at-timedelta(hours=1)).isoformat()
        def forbidden(*args):
            raise AssertionError('Maintenance must not consume extraction requests')
        result = self.feed.run(at, transport=forbidden, key='unused')
        self.assertEqual([p['id'] for p in result['posts']], ['456'])
        self.assertEqual(self.feed.state['daily'], {})

    def test_quota_error_is_reported_globally_and_preserved_by_publication(self):
        calls = []
        def quota(*args):
            calls.append(1)
            return 402, '{}', {}
        result = self.feed.run(NOW, transport=quota, key='unused')
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['last_error']['kind'], 'quota')
        self.assertEqual(self.feed.publish(NOW+timedelta(minutes=15))['last_error']['kind'], 'quota')
        self.assertEqual(self.feed.state['daily'][NOW.date().isoformat()], 1)

    def test_catalog_uses_the_configured_window_for_each_creator(self):
        # The production catalog is now administrator-editable. Test the loader
        # contract with an owned catalog rather than freezing users' settings.
        path=self.cfg.data.parent/'accounts.json'
        atomic(path,{'version':1,'accounts':copy.deepcopy(ACCOUNTS)})
        rules = {a['handle']: a['lookback_days'] for a in load_accounts(path)}
        self.assertEqual(rules, dict(one=3,two=15))


if __name__ == '__main__':
    unittest.main()
