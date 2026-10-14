"""El bloqueo se comprueba antes de crear un cliente o iniciar una inferencia."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from cranalysis.__main__ import cmd_run


class ApiGuard(TestCase):
    def test_disabled_run_cannot_create_client(self):
        with patch('cranalysis.__main__._client_and_runner') as client:
            self.assertEqual(cmd_run(SimpleNamespace(allow_api_analysis=False), SimpleNamespace()), 2)
        client.assert_not_called()
