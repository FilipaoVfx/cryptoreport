"""Boot contract: Urania and its public ingress survive a VPS restart."""
from pathlib import Path
import configparser
import unittest

OPS=Path(__file__).parent/'ops'

class Boot(unittest.TestCase):
    def unit(self,name):
        config=configparser.ConfigParser(interpolation=None,strict=False)
        path=OPS/name
        self.assertTrue(path.exists(),f'{name} must be versioned, not an untracked nohup process')
        config.read(path)
        return config

    def test_web_starts_at_boot_from_main_repository(self):
        c=self.unit('cryptoreport-urania-web.service')
        self.assertEqual(c['Service']['Restart'],'always')
        self.assertIn('/root/cryptoreport/prototypes/movil/serve.py 8741',c['Service']['ExecStart'])
        self.assertEqual(c['Install']['WantedBy'],'multi-user.target')

    def test_tunnel_recovers_and_targets_the_same_web_service(self):
        c=self.unit('cryptoreport-urania-tunnel.service')
        self.assertEqual(c['Service']['Restart'],'always')
        self.assertIn('cryptoreport-urania-web.service',c['Unit']['Wants'])
        self.assertNotIn('Requires',c['Unit'])
        self.assertIn('http://127.0.0.1:8741',c['Service']['ExecStart'])
        self.assertEqual(c['Install']['WantedBy'],'multi-user.target')

if __name__=='__main__':unittest.main()
