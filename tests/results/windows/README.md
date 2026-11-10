# Windows test plan and results

Run date: 2026-11-09 (America/Denver).
Branch: `windows-test`, created from local `main` at
`f0ba04a0a2250de982aed67eec625008dcef1f51`.
Code, tests, and this report are left uncommitted; no commit was created.

## Environment and reproduction

- Native Windows 11, build `10.0.26300`, AMD64.
- CPython 3.12.10, MSC v.1943, 64 bit; SQLite 3.49.1; Unicode database 15.0.0.
- Default text encoding: `cp936`; UTF-8 mode was not forced.
- The installed system Python was 3.10. An official Python 3.12.10 embeddable
  runtime was downloaded to the ignored `.venv/windows-python/` directory.
  Its `python312._pth` includes the repository root so subprocess tests can
  import the source checkout. System Python and global Git settings were unchanged.
- Runtime source: `https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip`.
  Archive SHA-256: `4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3`.

From the repository root in PowerShell, using this runtime:

```powershell
& ./.venv/windows-python/python.exe -m unittest discover -s tests -t . -v
```

With a normal Python 3.12 installation, `python -m unittest discover -s tests -t . -v`
is equivalent. For just the workspace and subprocess concurrency coverage:

```powershell
python -m unittest tests.test_workspace tests.test_interfaces.ConcurrencyTests -v
```

The final log was captured as raw subprocess stdout/stderr bytes, avoiding
PowerShell's formatting of native stderr as error records.

## Results

| Run | Tests run | Passed | Failures | Errors | Skips | Time | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unmodified main baseline | 184 | 176 | 3 | 3 | 2 | 45.389 s | 1 |
| Workspace + concurrency after adding coverage, before engine fix | 48 | 45 | 0 | 1 | 2 | 7.912 s | 1 |
| Final complete suite | 192 | 189 | 0 | 0 | 3 | 57.491 s | 0 |

Logs: [baseline.log](baseline.log), [targeted.log](targeted.log),
[full-suite.log](full-suite.log). The baseline retains PowerShell's original
line wrapping and native-stderr annotations, converted from UTF-16 to UTF-8
with trailing whitespace removed.

Final skips:

1. POSIX shared-lock coexistence: Windows `msvcrt` locks are exclusive-only.
   The new native test verifies that readers serialize and nested upgrades retain exclusion.
2. Directory symlink loop: this account lacks symlink privilege / Developer Mode
   (`WinError 1314`). The test now skips only that specific Windows error and
   still runs where directory symlinks are available.
3. External dataset/parquet test: benchmark downloads are absent. The synthetic
   external-evaluation regressions ran successfully.

## Completed TODO coverage

| Risk | Evidence and observed behavior |
| --- | --- |
| `msvcrt` locks | A separate process holds shared/exclusive workspace locks; both reads and writes time out. After release, reads succeed. Nested shared/exclusive acquisition stays exclusive against another holder and releases correctly. |
| Atomic replacement and deletion with open files | A child process holds an overlay file open. Replace/delete raise `PermissionError`, preserve the original bytes, and leave no atomic-write temp files. Both operations succeed after release. |
| Interrupted `apply()` with open files | Replace and delete fail while a child owns the destination handle. The journal and staging manifest remain; a reopened workspace completes recovery after release and clears staging. |
| `pack()` and open files | Directory, ZIP, and tar.gz exports succeed with an open source. An existing open destination is refused without modifying bytes; temporary export directories are removed. Existing deterministic archive tests also pass. |
| Recovery with best-effort directory flushing | A subprocess calls `os._exit(77)` immediately after the first durable move in a create/modify/delete batch. A fresh workspace replays the surviving journal, completes the batch, and remains correct after another reopen. Existing scenario tests cover other replay boundaries and intervening human edits. |
| CRLF and hashes | Parsing normalizes CRLF, but `sha256` and `if_match` use raw bytes. A normalized-text hash is rejected. Live/staged edits accept the correct raw hash; a newline-only overlay edit invalidates a staged precondition without overwriting the editor's bytes. |
| Windows mount paths | Drive-letter paths, backslashes, spaces, and Chinese names round-trip through `Workspace.mount()` and TOML. Internal paths serialize with forward slashes, external paths retain native syntax, and a hand-written TOML literal path resolves. |
| Subprocess concurrency | Both `ConcurrencyTests` pass: simultaneous writers lose no appends, and competing readers/writers finish an in-flight apply without losing writes. |
| Entire suite | Functional journeys, CLI/MCP, multilingual search, retrieval regressions, workspace operations, and the available external-evaluation tests pass in the final run. |

The three portable regression tests and five native Windows tests live in
`tests/test_workspace.py`, replacing the pending TODO.

## Baseline failures resolved

- **Corrupt SQLite cache:** `_open()` leaked its connection when initialization
  raised, preventing Windows from unlinking the corrupt database. Close failed
  connections before rebuilding, including schema-inspection failures.
- **Hand-written mounts fixture:** escape native backslashes in the TOML basic string.
- **Symlink fixture:** explicitly request a directory link and skip only missing
  Windows symlink privilege.
- **Journey determinism:** normalize both short (8.3) and resolved long temporary
  paths in transcripts; validation resolves the path to its long spelling.
- **Bulk evaluation ingestion:** write LF explicitly so bulk cards are byte-identical
  to `Workspace.write()` on Windows.
- **Frozen corpus digests:** Git's CRLF checkout conversion changed raw hashes.
  CI now disables `core.autocrlf` before checkout to preserve LF. The local checkout
  uses an untracked `.gitattributes`, excluded through `.git/info/exclude`.
  The existing checkout's 186 data files were restored to LF and verified
  byte-identical to their indexed Git blobs. No dataset content or frozen digest
  values changed.

CI now includes `windows-2025` (Windows Server 2025, x64) alongside `ubuntu-24.04`,
both using Python 3.12. The explicit label pins the OS release; runner tools still
receive updates. This differs from the local Windows 11 environment recorded above.
The hosted CI jobs have not been run in this session. `git diff --check` passed.

## Limits

`fsync_dir()` is best effort and may not flush Windows directory metadata. These
tests establish recovery after process exit and sharing violations while the OS
remains running. They do **not** establish durability after power loss or an OS
crash; the original TODO's power-loss assurance remains unproven. No real power
cut, other filesystem, network share, alternate drive, or Windows version was tested.
The symlink test must still run on a Windows account with the required capability.
