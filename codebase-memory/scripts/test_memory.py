"""Behavior checks in disposable codebases; run with python test_memory.py."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
import uuid

HELPER = Path(__file__).with_name('memory.py')


class MemoryBehavior(unittest.TestCase):
    def setUp(self):
        # Allow sandboxed callers to keep disposable fixtures inside their workspace.
        base = Path(os.environ.get('MEMORY_TEST_TMP', str(Path.cwd() / 'tmp'))).resolve()
        base.mkdir(parents=True, exist_ok=True)
        # Normal directory ACLs also work for restricted Windows process tokens.
        self.root = base / ('codebase-memory-test-' + uuid.uuid4().hex)
        self.root.mkdir()
        def cleanup():
            target = self.root.resolve()
            if target.parent != base:
                raise ValueError('Fixture cleanup escaped its temporary parent.')
            shutil.rmtree(target)
        self.addCleanup(cleanup)
        (self.root / 'service.py').write_text(
            'import json\nTIMEOUT = 30\nclass Service:\n'
            '    def send(self):\n        return json.dumps({})\n', encoding='utf-8')
        self.entry = {'kind': 'method', 'symbol': 'Service.send',
                      'summary': 'Serializes a request to JSON.', 'tags': ['request'],
                      'sources': [{'path': 'service.py', 'start_line': 4, 'end_line': 5}]}

    def run_cli(self, *args, payload=None, fail=False):
        result = subprocess.run([sys.executable, str(HELPER), '--root', str(self.root), *args],
                                input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, encoding='utf-8')
        if fail:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def upsert(self, entry=None):
        return self.run_cli('upsert', '--input', '-', payload=entry or self.entry)['upserted'][0]

    def test_scan_extracts_source_without_executing_or_dumping_values(self):
        with (self.root / 'service.py').open('a', encoding='utf-8') as f:
            f.write('PASSWORD = "DO_NOT_STORE_THIS_VALUE"\nraise RuntimeError("do not execute")\n')
        result = self.run_cli('scan')
        symbols = result['candidates'][0]['symbols']
        self.assertTrue(any(s['symbol'] == 'Service.send' and s['kind'] == 'method' for s in symbols))
        self.assertTrue(any(s.get('call_targets') == ['json.dumps'] for s in symbols))
        self.assertNotIn('DO_NOT_STORE_THIS_VALUE', json.dumps(result))
        self.assertEqual(self.run_cli('list'), [])

    def test_exclusions_diagnostics_and_nonpython_handoff(self):
        for name, content in {'.env': 'TOKEN=secret', 'broken.py': 'def (',
                              'routes.ts': 'export function route() {}',
                              'asset.png': 'image', 'binary.json': '\0binary',
                              'large.md': 'a' * 1024}.items():
            (self.root / name).write_text(content, encoding='utf-8')
        (self.root / 'node_modules').mkdir()
        (self.root / 'node_modules' / 'dependency.py').write_text('def dep(): pass')
        (self.root / '.gitignore').write_text('ignored.py\n', encoding='utf-8')
        (self.root / 'ignored.py').write_text('def hidden(): pass', encoding='utf-8')
        result = self.run_cli('scan', '--max-bytes', '512')
        files = result['files']
        self.assertNotIn('.env', files)
        self.assertNotIn('node_modules/dependency.py', files)
        if result['coverage']['ignore_engine'] == 'rg-ignore-files':
            self.assertNotIn('ignored.py', files)
        self.assertEqual(files['broken.py']['status'], 'syntax-error')
        self.assertEqual(files['routes.ts']['status'], 'needs-agent-extraction')
        self.assertEqual(files['asset.png']['status'], 'unsupported')
        self.assertEqual(files['binary.json']['status'], 'binary')
        self.assertEqual(files['large.md']['status'], 'oversized')

    def test_duplicate_correction_retains_identity_and_new_summary(self):
        old_id = self.upsert()
        new_entry = {**self.entry, 'summary': 'Corrected: serializes an empty payload.', 'note': 'Reviewed code.'}
        self.assertEqual(self.upsert(new_entry), old_id)
        self.assertEqual(len(self.run_cli('list')), 1)
        found = self.run_cli('search', 'corrected')
        self.assertEqual(found[0]['id'], old_id)
        self.assertEqual(found[0]['sources'][0]['start_line'], 4)
        self.assertEqual(found[0]['freshness']['status'], 'current')
        self.assertIn('sha256', found[0]['sources'][0])

    def test_stale_search_change_delete_and_verified_refresh(self):
        entry_id = self.upsert()
        with (self.root / 'service.py').open('a', encoding='utf-8') as f:
            f.write('# changed\n')
        self.assertEqual(self.run_cli('search', 'Service.send'), [])
        self.assertEqual(self.run_cli('search', 'Service.send', '--include-stale')[0]['freshness']['status'], 'stale')
        self.run_cli('scan')
        self.assertEqual(self.run_cli('show', entry_id)['freshness']['status'], 'stale')
        self.upsert()
        self.assertEqual(self.run_cli('status')['counts'], {'current': 1})
        (self.root / 'service.py').unlink()
        state = self.run_cli('show', entry_id)['freshness']
        self.assertEqual(state['problems'][0]['reason'], 'deleted')

    def test_remove_tombstone_scan_does_not_restore_and_explicit_upsert_does(self):
        entry_id = self.upsert()
        self.run_cli('remove', entry_id, '--reason', 'Obsolete fact.')
        self.run_cli('scan')
        self.assertEqual(self.run_cli('search', 'Service.send', '--include-stale'), [])
        store = json.loads((self.root / '_memoryStorage').read_text(encoding='utf-8'))
        self.assertIn(entry_id, store['removed'])
        self.assertNotIn('Serializes a request', json.dumps(store))
        self.upsert()
        store = json.loads((self.root / '_memoryStorage').read_text(encoding='utf-8'))
        self.assertNotIn(entry_id, store['removed'])

    def test_invalid_batch_is_atomic_and_rejects_source_escape(self):
        self.upsert()
        before = (self.root / '_memoryStorage').read_bytes()
        invalid = {**self.entry, 'symbol': 'invalid', 'sources': [{'path': '../escape.py', 'start_line': 1, 'end_line': 1}]}
        self.run_cli('upsert', '--input', '-', payload=[self.entry, invalid], fail=True)
        self.assertEqual(before, (self.root / '_memoryStorage').read_bytes())
        invalid['sources'][0] = {'path': 'service.py', 'start_line': 1, 'end_line': 999}
        self.run_cli('upsert', '--input', '-', payload=invalid, fail=True)
        (self.root / '.env').write_text('secret')
        invalid['sources'][0] = {'path': '.env', 'start_line': 1, 'end_line': 1}
        self.run_cli('upsert', '--input', '-', payload=invalid, fail=True)
        self.assertEqual(before, (self.root / '_memoryStorage').read_bytes())

    def test_narrow_scans_preserve_other_memories_and_budget_failure_preserves_store(self):
        self.upsert()
        (self.root / 'other.py').write_text('def other(): pass\n', encoding='utf-8')
        self.run_cli('scan')
        self.run_cli('scan', '--include', 'other.py')
        store = json.loads((self.root / '_memoryStorage').read_text(encoding='utf-8'))
        self.assertIn('service.py', store['files'])
        self.assertEqual(len(store['entries']), 1)
        before = (self.root / '_memoryStorage').read_bytes()
        self.run_cli('scan', '--include', '*.py', '--max-files', '1', fail=True)
        self.assertEqual(before, (self.root / '_memoryStorage').read_bytes())

    def test_read_commands_leave_store_unchanged(self):
        entry_id = self.upsert()
        before = (self.root / '_memoryStorage').read_bytes()
        for command in [('list',), ('show', entry_id), ('status',), ('search', 'request')]:
            self.run_cli(*command)
        self.assertEqual(before, (self.root / '_memoryStorage').read_bytes())

    def test_different_root_cannot_reuse_store(self):
        self.upsert()
        other = self.root / 'nested'
        other.mkdir()
        result = subprocess.run([sys.executable, str(HELPER), '--root', str(other),
                                 '--store', str(self.root / '_memoryStorage'), 'status'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('root mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
