import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'repository_check', Path(__file__).resolve().parents[1] / 'scripts/check_repository.py')
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class RepositoryMetadataTests(unittest.TestCase):
    def test_generated_merge_identity_passes_while_personal_metadata_is_rejected(self):
        cases = [
            ('noreply' + '@github.com', 0),
            ('demo' + '@users.noreply.github.com', 0),
            ('personal' + '@example.com', 1),
        ]
        for email, expected in cases:
            with self.subTest(email=email), \
                    patch.object(scanner.sys, 'argv', ['check_repository.py']), \
                    patch.object(scanner, 'tracked_worktree_files', return_value=[]), \
                    patch.object(scanner, 'parse_denylist', return_value=[]), \
                    patch.object(scanner, 'git', return_value=f'Author: Demo <{email}>'.encode()), \
                    patch('sys.stdout', new_callable=io.StringIO), \
                    patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(scanner.main(), expected)
