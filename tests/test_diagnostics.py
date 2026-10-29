import unittest
from lala_core.diagnostics import sanitize_fields


class DiagnosticsTests(unittest.TestCase):
    def test_redact_nested_credentials(self):
        source = {'username': 'user', 'password': 'private',
                  'meta': {'token': 'ABC', 'api_key': 'xyz', 'active': False}}
        result = sanitize_fields(source)
        self.assertEqual(result['password'], '[已遮罩]')
        self.assertEqual(result['meta']['token'], '[已遮罩]')
        self.assertEqual(result['meta']['api_key'], '[已遮罩]')
        self.assertFalse(result['meta']['active'])
        self.assertEqual(source['password'], 'private')

    def test_non_serializable_objects_not_stringified(self):
        class SecretObject:
            def __str__(self):
                return 'sensitive'
        self.assertEqual(sanitize_fields(SecretObject()), '[非預期資料類型]')

    def test_list_redaction(self):
        self.assertEqual(sanitize_fields([{'密碼': 'x'}, 123]), [{'密碼': '[已遮罩]'}, 123])
