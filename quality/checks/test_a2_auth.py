"""Credential precedence, root resolution and sanitized single-request errors."""
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from src.collect.cache import api_key
from src.collect.auth_check import check, URL
from test_a2_support import temporary_workspace


class AuthTests(unittest.TestCase):
    def test_env_precedence_and_blank_fallback_without_mutation(self):
        with temporary_workspace() as root:
            path = root / '.env'
            original = b'OPENALEX_API_KEY="file-fixture" # comment\nOTHER=keep\n'
            path.write_bytes(original)
            with patch.dict(os.environ, {'OPENALEX_API_KEY': 'env-fixture'}):
                self.assertEqual(api_key(root), 'env-fixture')
            with patch.dict(os.environ, {'OPENALEX_API_KEY': ''}):
                self.assertEqual(api_key(root), 'file-fixture')
                self.assertEqual(os.environ['OPENALEX_API_KEY'], '')
            self.assertEqual(path.read_bytes(), original)

    def test_default_root_is_independent_of_cwd(self):
        with temporary_workspace() as root, patch.dict(os.environ, {'OPENALEX_API_KEY': ''}), patch('src.collect.cache.REPO_ROOT', root):
            (root / '.env').write_text('export OPENALEX_API_KEY=file-fixture\n')
            elsewhere = root / 'elsewhere'; elsewhere.mkdir()
            (elsewhere / '.env').write_text('OPENALEX_API_KEY=wrong-fixture\n')
            previous = os.getcwd()
            try:
                os.chdir(elsewhere)
                self.assertEqual(api_key(), 'file-fixture')
            finally:
                os.chdir(previous)

    def test_success_exactly_one_request_no_response_read(self):
        response = MagicMock(); response.__enter__.return_value = response
        response.status = 200; response.geturl.return_value = URL
        with patch('src.collect.auth_check.api_key', return_value='private-fixture'), patch('src.collect.auth_check.urlopen', return_value=response) as network:
            result = check()
            self.assertTrue(result['success']); self.assertEqual(network.call_count, 1)
            request = network.call_args.args[0]
            self.assertEqual(request.full_url, URL)
            self.assertEqual(request.get_header('Authorization'), 'Bearer private-fixture')
            response.read.assert_not_called()
            self.assertNotIn('private-fixture', json.dumps(result))

    def test_error_categories_never_expose_exception_or_key(self):
        for code, category in [(401,'authentication'),(403,'authentication'),(429,'rate_limit'),(503,'http')]:
            with self.subTest(code=code), patch('src.collect.auth_check.api_key',return_value='private-fixture'), patch('src.collect.auth_check.urlopen',side_effect=HTTPError(URL,code,'private-fixture',{},None)) as network:
                result = check()
                self.assertEqual(result['http_status'],code)
                self.assertEqual(result['error_category'],category)
                self.assertNotIn('private-fixture',json.dumps(result))
                self.assertEqual(network.call_count,1)
        with patch('src.collect.auth_check.api_key',return_value='private-fixture'), patch('src.collect.auth_check.urlopen',side_effect=URLError('private-fixture')):
            result=check(); self.assertEqual(result['error_category'],'network')
            self.assertNotIn('private-fixture',json.dumps(result))

    def test_missing_key_does_not_call_network(self):
        with patch('src.collect.auth_check.api_key',return_value=''), patch('src.collect.auth_check.urlopen') as network:
            self.assertFalse(check()['key_loaded']); network.assert_not_called()
