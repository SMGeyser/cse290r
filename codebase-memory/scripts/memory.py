"""Source-backed codebase memory. Standard library only; never executes source code."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SKIP_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.cache',
             '.pytest_cache', 'vendor', 'dist', 'build', 'coverage', 'output', 'tmp'}
SECRET_GLOBS = ('.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx', 'id_rsa*',
                'id_ed25519*', '*credentials*', '*secrets*', '*.lock', 'package-lock.json',
                'yarn.lock', 'pnpm-lock.yaml')
TEXT_SUFFIXES = {'.py', '.js', '.jsx', '.ts', '.tsx', '.rb', '.go', '.rs', '.java',
                 '.kt', '.c', '.h', '.cpp', '.cs', '.php', '.swift', '.sh', '.ps1',
                 '.sql', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.md'}
TEXT_NAMES = {'Dockerfile', 'Makefile', 'Gemfile', 'Rakefile', 'Procfile'}
KINDS = {'architecture', 'flow', 'function', 'class', 'method', 'route', 'config',
         'export', 'relationship', 'module'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def matches(path, patterns):
    parts = Path(path).parts
    candidates = [path, parts[-1]] + ['/'.join(parts[:i]) for i in range(1, len(parts))]
    return any(fnmatch.fnmatchcase(p, g.replace('\\', '/')) for g in patterns for p in candidates)


def excluded(path):
    parts = Path(path).parts
    return (any(p.lower() in SKIP_DIRS or p in {'.ssh', '.aws'} for p in parts[:-1])
            or parts[-1].startswith('_memoryStorage')
            or parts[-1].endswith('.memory-tmp')
            or matches(path.lower(), SECRET_GLOBS))


def source_path(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('Source paths must be nonempty paths relative to --root.')
    p = root / value
    if any(q.is_symlink() for q in [p, *p.parents] if q != root and root in q.parents):
        raise ValueError(f'Symlink source is excluded: {value}')
    resolved = p.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError(f'Source escapes root: {value}')
    rel = resolved.relative_to(root).as_posix()
    if excluded(rel):
        raise ValueError(f'Excluded source: {rel}')
    return resolved, rel


def load_store(store, root, create=False):
    raw = store.read_bytes() if store.exists() else None
    if raw is None:
        if not create:
            raise ValueError('Memory store does not exist. Run scan or upsert first.')
        return {'version': 1, 'root': str(root), 'updated_at': now(), 'files': {},
                'coverage': {}, 'entries': {}, 'removed': {}}, None
    data = json.loads(raw)
    if data.get('version') != 1 or Path(data.get('root', '')).resolve() != root:
        raise ValueError('Unsupported store version or codebase root mismatch; choose the correct --root/--store.')
    for key in ('files', 'coverage', 'entries', 'removed'):
        if not isinstance(data.get(key), dict):
            raise ValueError(f'Invalid memory store field: {key}')
    return data, raw


def save_store(store, data, original):
    current = store.read_bytes() if store.exists() else None
    if current != original:
        raise ValueError('Store changed concurrently; reread before retrying.')
    data['updated_at'] = now()
    store.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=store.name + '.', suffix='.memory-tmp', dir=store.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        if (store.read_bytes() if store.exists() else None) != original:
            raise ValueError('Store changed concurrently; reread before retrying.')
        os.replace(temp, store)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f'{base}.{node.attr}' if base else ''
    if isinstance(node, ast.Call):
        return dotted(node.func)
    return ''


class Symbols(ast.NodeVisitor):
    def __init__(self):
        self.items, self.parents = [], []

    def record(self, node, kind, symbol, **extra):
        self.items.append({'kind': kind, 'symbol': symbol, 'start_line': node.lineno,
                           'end_line': node.end_lineno, **extra})

    def definition(self, node, kind):
        name = '.'.join([p[0] for p in self.parents] + [node.name])
        calls = sorted({dotted(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)} - {''})
        self.record(node, kind, name, call_targets=calls,
                    decorators=[dotted(d) for d in node.decorator_list if dotted(d)])
        self.parents.append((node.name, kind))
        self.generic_visit(node)
        self.parents.pop()

    def visit_ClassDef(self, node):
        self.definition(node, 'class')

    def visit_FunctionDef(self, node):
        kind = 'method' if self.parents and self.parents[-1][1] == 'class' else 'function'
        self.definition(node, kind)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node):
        for alias in node.names:
            self.record(node, 'import', alias.name)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.record(node, 'import', '.' * node.level + (node.module or '') + '.' + alias.name)

    def visit_Assign(self, node):
        if not self.parents:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    self.record(node, 'config', target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if not self.parents and isinstance(node.target, ast.Name) and node.target.id.isupper():
            self.record(node, 'config', node.target.id)
        self.generic_visit(node)


def enumerate_files(root, excludes):
    rg = shutil.which('rg')
    if rg:
        command = [rg, '--files', '--hidden', '--no-require-git']
        for directory in sorted(SKIP_DIRS | {'.ssh', '.aws'}):
            command += ['--glob', f'!**/{directory}/**']
        for pattern in excludes:
            pattern = pattern.replace('\\', '/')
            command += ['--glob', '!' + pattern, '--glob', '!' + pattern.rstrip('/') + '/**']
        result = subprocess.run(command, cwd=root, capture_output=True, encoding='utf-8')
        if result.returncode not in (0, 1):
            raise ValueError(f'File traversal failed: {result.stderr.strip()}')
        return sorted(result.stdout.splitlines()), 'rg-ignore-files'
    files = []
    def fail(error):
        raise error
    for parent, directories, names in os.walk(root, followlinks=False, onerror=fail):
        directories[:] = [d for d in directories if d.lower() not in SKIP_DIRS
                          and d not in {'.ssh', '.aws'} and not (Path(parent) / d).is_symlink()
                          and not matches((Path(parent) / d).relative_to(root).as_posix(), excludes)]
        files += [(Path(parent) / name).relative_to(root).as_posix() for name in names]
    return sorted(files), 'fallback-explicit-exclusions-only'


def scan(args, root, store, data):
    names, engine = enumerate_files(root, args.exclude)
    includes = args.include or ['**']
    candidates, records = [], {}
    counts = Counter()
    selected = []
    for name in names:
        rel = name.replace('\\', '/')
        p = root / rel
        if excluded(rel):
            counts['excluded'] += 1
            continue
        if matches(rel, args.exclude) or not matches(rel, includes):
            counts['outside_scope'] += 1
            continue
        if p.resolve() == store or (args.output and p.resolve() == Path(args.output).resolve()):
            counts['excluded'] += 1
            continue
        if p.is_symlink() or any(q.is_symlink() for q in p.parents if q != root and root in q.parents):
            counts['symlink'] += 1
            continue
        selected.append((p, rel))
    if len(selected) > args.max_files:
        raise ValueError(f'{len(selected)} files exceed --max-files {args.max_files}; narrow --include/--exclude.')
    for p, rel in selected:
        record = {'checked_at': now()}
        try:
            if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in TEXT_NAMES:
                record['status'] = 'unsupported'
            elif p.stat().st_size > args.max_bytes:
                record['status'] = 'oversized'
            else:
                raw = p.read_bytes()
                record['sha256'] = digest(raw)
                text = raw.decode('utf-8-sig')
                if '\0' in text:
                    record['status'] = 'binary'
                elif p.suffix.lower() == '.py':
                    visitor = Symbols()
                    visitor.visit(ast.parse(text, filename=rel))
                    record['status'] = 'python-ast'
                    candidates.append({'path': rel, 'sha256': record['sha256'],
                                       'symbols': visitor.items})
                else:
                    record['status'] = 'needs-agent-extraction'
                    candidates.append({'path': rel, 'sha256': record['sha256'],
                                       'status': record['status']})
        except SyntaxError as error:
            record.update(status='syntax-error', line=error.lineno)
        except UnicodeDecodeError:
            record['status'] = 'non-utf8'
        except OSError as error:
            record.update(status='unreadable', error_type=type(error).__name__)
        counts[record['status']] += 1
        records[rel] = record
    for rel in list(data['files']):
        if matches(rel, includes) and not matches(rel, args.exclude):
            del data['files'][rel]
    data['files'].update(records)
    coverage = {'scanned_at': now(), 'include': includes, 'exclude': args.exclude,
                'default_excluded_directories': sorted(SKIP_DIRS | {'.ssh', '.aws'}),
                'default_excluded_files': list(SECRET_GLOBS) + ['_memoryStorage*', '*.memory-tmp'],
                'ignore_engine': engine, 'counts': dict(counts), 'selected_files': len(selected),
                'max_bytes': args.max_bytes,
                'scope': 'partial' if includes != ['**'] or args.exclude else 'all-nonexcluded-files'}
    data['coverage'] = coverage
    return {'coverage': coverage, 'files': records, 'candidates': candidates}


def compact_string(value, field, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{field} must be a nonempty string of at most {limit} characters.')
    return value.strip()


def string_list(value, field, limit):
    if not isinstance(value, list) or len(value) > 30:
        raise ValueError(f'{field} must be an array of at most 30 strings.')
    return list(dict.fromkeys(compact_string(v, field, limit) for v in value))


def prepare_entry(item, root):
    if not isinstance(item, dict) or item.get('kind') not in KINDS:
        raise ValueError('Entry kind must be one of: ' + ', '.join(sorted(KINDS)))
    symbol = compact_string(item.get('symbol'), 'symbol', 300)
    summary = compact_string(item.get('summary'), 'summary', 2000)
    evidence = item.get('evidence', 'observed')
    if evidence not in {'observed', 'inferred'}:
        raise ValueError('evidence must be observed or inferred.')
    if not isinstance(item.get('sources'), list) or not 1 <= len(item['sources']) <= 30:
        raise ValueError('Entry requires 1–30 source locations.')
    sources = []
    for source in item['sources']:
        p, rel = source_path(root, source['path'])
        raw = p.read_bytes()
        lines = raw.decode('utf-8-sig').splitlines()
        start, end = source['start_line'], source['end_line']
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError(f'Invalid source line range: {rel}')
        ref = {'path': rel, 'start_line': start, 'end_line': end, 'sha256': digest(raw)}
        if ref not in sources:
            sources.append(ref)
    identity = json.dumps([item['kind'], symbol, sources[0]['path']], ensure_ascii=False)
    entry_id = digest(identity.encode('utf-8'))[:20]
    entry = {'id': entry_id, 'kind': item['kind'], 'symbol': symbol, 'summary': summary,
             'evidence': evidence, 'tags': string_list(item.get('tags', []), 'tags', 100),
             'relationships': string_list(item.get('relationships', []), 'relationships', 500),
             'sources': sources, 'updated_at': now()}
    if item.get('note'):
        entry['note'] = compact_string(item['note'], 'note', 1000)
    return entry


def freshness(entry, root, cache):
    problems = []
    for source in entry['sources']:
        rel = source['path']
        if rel not in cache:
            try:
                p, _ = source_path(root, rel)
                cache[rel] = digest(p.read_bytes())
            except FileNotFoundError:
                cache[rel] = 'deleted'
            except (OSError, ValueError):
                cache[rel] = 'unreadable-or-excluded'
        current = cache[rel]
        if current != source['sha256']:
            problems.append({'path': rel, 'reason': current if current in {'deleted', 'unreadable-or-excluded'} else 'changed'})
    return {'status': 'stale' if problems else 'current', 'problems': problems}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    parser.add_argument('--store', help='Defaults to <root>/_memoryStorage.')
    commands = parser.add_subparsers(dest='command', required=True)
    s = commands.add_parser('scan', help='Inventory files and extract candidates, not curated entries.')
    s.add_argument('--include', action='append', default=[])
    s.add_argument('--exclude', action='append', default=[])
    s.add_argument('--output')
    s.add_argument('--max-files', type=int, default=5000)
    s.add_argument('--max-bytes', type=int, default=1024 * 1024)
    u = commands.add_parser('upsert')
    u.add_argument('--input', required=True)
    q = commands.add_parser('search')
    q.add_argument('query')
    q.add_argument('--include-stale', action='store_true')
    q.add_argument('--limit', type=int, default=10)
    commands.add_parser('list')
    commands.add_parser('status')
    sh = commands.add_parser('show')
    sh.add_argument('id')
    rm = commands.add_parser('remove')
    rm.add_argument('id')
    rm.add_argument('--reason', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    store = Path(args.store).resolve() if args.store else root / '_memoryStorage'
    if not root.is_dir():
        raise ValueError('--root must be an existing directory.')
    data, original = load_store(store, root, create=args.command in {'scan', 'upsert'})
    if args.command == 'scan':
        if args.max_files < 1 or args.max_bytes < 1:
            raise ValueError('Scan budgets must be positive.')
        if args.output and Path(args.output).resolve() == store:
            raise ValueError('--output cannot overwrite the memory store.')
        result = scan(args, root, store, data)
        if args.output:
            out = Path(args.output)
            if out.exists():
                raise ValueError('Candidate output already exists; choose a temporary unused filename.')
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open('x', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        save_store(store, data, original)
        emit(result['coverage'] if args.output else result)
    elif args.command == 'upsert':
        payload = json.loads(sys.stdin.read() if args.input == '-' else Path(args.input).read_text(encoding='utf-8-sig'))
        items = payload if isinstance(payload, list) else [payload]
        entries = [prepare_entry(item, root) for item in items]
        for entry in entries:
            data['entries'][entry['id']] = entry
            data['removed'].pop(entry['id'], None)
        save_store(store, data, original)
        emit({'upserted': list(dict.fromkeys(e['id'] for e in entries)), 'total_entries': len(data['entries'])})
    elif args.command == 'remove':
        reason = compact_string(args.reason, 'reason', 500)
        if args.id not in data['entries']:
            raise ValueError('Unknown entry ID.')
        del data['entries'][args.id]
        data['removed'][args.id] = {'removed_at': now(), 'reason': reason}
        save_store(store, data, original)
        emit({'removed': args.id})
    else:
        cache = {}
        if args.command == 'show':
            entry = data['entries'].get(args.id)
            if entry is None:
                raise ValueError('Unknown entry ID.')
            emit({**entry, 'freshness': freshness(entry, root, cache)})
        elif args.command == 'status':
            rows = [{'id': e['id'], 'symbol': e['symbol'], **freshness(e, root, cache)} for e in data['entries'].values()]
            emit({'entries': rows, 'counts': dict(Counter(r['status'] for r in rows)), 'coverage': data['coverage']})
        elif args.command == 'list':
            emit([{'id': e['id'], 'kind': e['kind'], 'symbol': e['symbol'],
                   'summary': e['summary'], 'freshness': freshness(e, root, cache)} for e in data['entries'].values()])
        elif args.command == 'search':
            if args.limit < 1:
                raise ValueError('--limit must be positive.')
            terms = set(re.findall(r'[\w./-]+', args.query.lower()))
            if not terms:
                raise ValueError('Search requires at least one keyword.')
            results = []
            for entry in data['entries'].values():
                haystack = ' '.join([entry['symbol'], entry['summary'], *entry['tags'],
                                     *entry['relationships'], *(s['path'] for s in entry['sources'])]).lower()
                score = sum(1 + (term in entry['symbol'].lower()) for term in terms if term in haystack)
                if not score:
                    continue
                state = freshness(entry, root, cache)
                if state['status'] == 'stale' and not args.include_stale:
                    continue
                results.append({**entry, 'score': score, 'freshness': state})
            results.sort(key=lambda e: (-e['score'], e['id']))
            emit(results[:args.limit])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'memory: {error}', file=sys.stderr)
        sys.exit(1)
