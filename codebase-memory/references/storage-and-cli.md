# Storage and commands

The design combines a readable filesystem store with curated relationship text. It uses no embeddings, external APIs, database, or runtime project imports. Lexical retrieval is explainable and inexpensive, but synonyms may require another query. This is project knowledge, not personal/chat memory.

`_memoryStorage` is UTF-8, indented JSON with `version`, absolute `root`, `updated_at`, `files`, `coverage`, `entries`, and `removed`. The file manifest tracks source hashes and extraction status; `coverage` records the most recent scan's globs, exclusion rules, ignore engine, and counts. Coverage is explicitly partial when includes/excludes narrow it. Each durable entry contains an ID, kind, qualified symbol, compact summary, evidence level, tags, optional relationships/note, source locations/hashes, and update time. IDs derive from kind, symbol, and primary path, so line shifts do not create duplicates. Hashes cover entire source files; a harmless file edit can conservatively mark a memory stale.

## Entry input

Use a JSON array (or one object) containing entries in this format:

```json
[
  {
    "kind": "function",
    "symbol": "client.build_payload",
    "summary": "Constructs the chat request from CLI options and the user prompt, adding optional system text and sampling controls.",
    "evidence": "observed",
    "tags": ["cli", "request"],
    "relationships": ["Called by main before sending the HTTP request."],
    "sources": [
      {"path": "client.py", "start_line": 38, "end_line": 57},
      {"path": "client.py", "start_line": 119, "end_line": 139}
    ]
  }
]
```

Supported kinds: `architecture`, `flow`, `function`, `class`, `method`, `route`, `config`, `export`, `relationship`, and `module`. `evidence` is `observed` or `inferred`. Paths are relative to the selected root; ranges are one-based and inclusive. At least one valid source is required. Put the defining file first; other sources provide relationship/caller evidence. Hashes and IDs are computed by the helper, not supplied by the author. Summaries have a 2,000-character limit; tags, relationship statements, notes, and entry counts should remain compact. Do not include source bodies or secret values.

For a correction, use the same kind/symbol/primary path and a new summary, optionally with `note`. The helper does not modify source code. Correcting source code is separate work and requires the applicable task authorization.

## CLI examples

Global options precede the command. Quote all paths with spaces. Use the current shell's syntax for glob literals; glob matching uses normalized forward-slash relative paths. Includes and excludes match files; exclusions also match directory ancestors. `*.py` matches Python basenames anywhere, while `ui/**` restricts selection to that subtree. `**` includes all candidates.

```text
python <helper> --root <repo> scan --include '*.py' --exclude 'vendor' --output <temporary-candidates.json>
python <helper> --root <repo> --store <repo>/_memoryStorage upsert --input <temporary-entries.json>
python <helper> --root <repo> search 'stream response'
python <helper> --root <repo> search 'OldHandler' --include-stale --limit 10
python <helper> --root <repo> list
python <helper> --root <repo> show <id>
python <helper> --root <repo> status
python <helper> --root <repo> remove <id> --reason 'Replaced by the new handler.'
```

`scan` creates a store if absent. Without `--output`, it prints candidates as JSON; with an output path, it saves candidates and prints compact scan counts. The default scan budget is 5,000 selected files and 1 MiB per file; adjust `--max-files` and `--max-bytes` explicitly when appropriate. Exceeding the file budget fails before writing, so reduce the scope. File-level parse/read/size failures become diagnostics. `upsert` accepts `--input -` for stdin. `search`, `list`, `show`, and `status` are read-only; missing stores fail clearly.

## Extraction and exclusions

Python uses `ast`, including nested qualified names, class methods, imports, top-level constants, decorators, and call expressions. Call targets are syntactic strings, not proven resolved graph edges. Python syntax errors are reported. Other recognized text formats (`.js`, `.jsx`, `.ts`, `.tsx`, `.rb`, `.go`, `.rs`, `.java`, `.kt`, `.c`, `.h`, `.cpp`, `.cs`, `.php`, `.swift`, `.sh`, `.ps1`, `.sql`, `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.md`, and common extensionless build manifests) require agent extraction. Binary/non-UTF-8 and unsupported formats are skipped with counts/status; no fabricated parse results.

The traversal excludes Git metadata, dependency/cache/build/output directories, symlinks, `.env` files, common private key/certificate/credential filenames, lockfiles, `_memoryStorage`, and temporary store files. `rg --files --hidden --no-require-git` respects ignore files and adds explicit exclusions. Without `rg`, a standard-library walker uses explicit exclusions but does not implement Git ignore semantics; coverage records that limitation. Sensitive values can still exist inside otherwise valid source files: the scanner outputs names/locations rather than bodies or assignment values, and the agent must redact them when writing summaries.

Changed hashes, missing files, and unreadable sources make an entry stale immediately, without another scan. Scanning does not revalidate old statements or delete entries from unscanned scopes. A source rename is initially a deletion; inspect the new location and replace the entry. Duplicates are merged by stable identity, preserving distinct symbols in different files. Each upsert validates all inputs before changing the store, then writes through a same-directory temporary file and atomic replace. An optimistic change check catches ordinary concurrent edits, but writers must still be serialized because a final check/replace race remains possible.
