# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A PySide6 (Qt6) desktop GUI that wraps Google's `bundletool.jar` to convert
Android App Bundles (`.aab`) into a signed universal `.apk`, with keystore
validation, ADB device install, and a few bundletool-derived diagnostics.
`resources/bundletool.jar` is vendored directly in the repo (~32MB) so the
packaged app has no external dependency on it at runtime beyond a JVM.

## Commands

```powershell
# Install runtime deps (first time)
python -m pip install -r requirements.txt

# Run from source
python main.py

# Install dev deps (pytest, PyInstaller)
python -m pip install -r requirements-dev.txt

# Run all tests
python -m pytest tests/ -v

# Run a single test file / test
python -m pytest tests/test_bundletool.py -v
python -m pytest tests/test_bundletool.py::test_build_apks_args_signed_uses_file_prefix_never_pass_prefix -v

# Build the distributable (onedir, not onefile — see app.spec comments)
pyinstaller app.spec --noconfirm
# Output: dist/AndroidBuildConverter/AndroidBuildConverter.exe (must ship the
# whole folder, not just the .exe — Qt DLLs and bundletool.jar live in _internal/)
```

There is no lint/format tooling configured in this repo.

## Architecture

**`core/` has no Qt imports except `bundletool.py`** (which needs `QProcess`
for non-blocking subprocess execution). Everything else in `core/` is pure
Python, callable and testable without a `QApplication` instance. `ui/`
depends on `core/`, never the reverse.

- **`core/toolchain.py`** — locates `java`, `keytool`, and `adb` on the host.
  bundletool.jar requires a JVM; bundling the jar doesn't remove that
  requirement, so this module searches `JAVA_HOME` → `PATH` → the JBR
  bundled with Android Studio → other known JDK install locations per OS.
  Everything downstream always receives an absolute resolved path rather
  than relying on env vars, because **bundletool itself only honors
  `ANDROID_HOME`, not `ANDROID_SDK_ROOT`**, and has no PATH search for its
  own `--adb` flag.

- **`core/bundletool.py`** — builds bundletool CLI argument lists
  (`build_apks_args`, `build_install_args`, etc.) as pure functions, and
  runs them via `BundletoolRunner` (a `QObject` wrapping `QProcess`).
  Command construction is deliberately separated from execution so argv
  construction — especially the password-handling invariant below — can be
  unit tested without touching a real process or Qt's event loop.

  **Security-critical invariant, covered by a regression test**: keystore
  and key passwords are never passed as `--ks-pass=pass:<literal>`, because
  that leaks the plaintext into the OS process list (visible via
  `Win32_Process.CommandLine` / Task Manager's command-line column on
  Windows). They're written to a temp file via `TemporaryPasswordFile` (no
  trailing newline — bundletool reads the raw file bytes) and passed as
  `file:<path>`, deleted in a `finally` block. If you add any new bundletool
  invocation that takes a password, follow this pattern — do not pass
  `pass:` on the command line.

  `--key-pass` is always passed explicitly when signing: omitting it makes
  bundletool prompt on a TTY that doesn't exist in a GUI context, hanging
  the process forever. `--overwrite` is always included in `build-apks`
  calls: without it, a second run against the same output path fails
  outright.

- **`core/workflow.py`** — `OutputLayout` computes where all artifacts for
  one conversion job go: everything lands in a single
  `<aab-name>_output/` folder next to the source `.aab`, nothing written
  elsewhere. `extract_universal_apk` reads the `universal.apk` entry
  straight out of the `.apks` zip at the root (confirmed from bundletool's
  `ApkPathManager.class` — no need to shell out to `extract-apks`).
  `check_base_module_size` reads `splits/base-master.apk`'s size from a
  *split-mode* `.apks` and flags it against Google Play's 200MB base-module
  upload limit — this only works on a `--mode=default` build, not universal
  (universal fuses everything into one standalone APK with no
  `base-master.apk` entry).

- **`core/keystore.py`** — pre-validates a keystore's password and lists its
  aliases via `keytool -list` before the long `build-apks` run touches it,
  so a wrong password surfaces instantly instead of after several minutes.
  **`keytool -keypasswd` does not support PKCS12 keystores** (the modern
  default), so only the *store* password and alias list can be
  pre-validated this way — the *key* password can only be confirmed by an
  actual signing run. Also note: unlike bundletool, `keytool` prints its
  errors to stdout, not stderr — both streams are checked.

- **`core/devices.py`** — parses `adb devices -l` for the device picker.

- **`core/manifest.py`** — reads package/version/SDK info out of an `.aab`
  via `bundletool dump manifest --xpath=...`, run synchronously since it's
  fast (unlike `build-apks`, which always goes through `BundletoolRunner`).

- **`core/errors.py`** — maps known bundletool stderr strings (pulled from
  decompiling `SignerConfig.class`) to bilingual (vi/en) friendly messages.

- **`ui/main_window.py`** — the single window; wires every `core/` module
  together. Long-running bundletool calls (convert, size estimation,
  device-spec + device-optimized build) each get their own
  `BundletoolRunner` instance connected via signals — none of them block
  the event loop. `ui/i18n.py` is a flat `{key: (vi, en)}` dict with a
  runtime language toggle (not Qt's `.ts`/`.qm` system — overkill for the
  string count here); raw bundletool log output is deliberately **not**
  translated, so it stays useful for troubleshooting against upstream.
  `ui/drop_zone.py` implements drag-and-drop using Qt's native
  `dragEnterEvent`/`dropEvent` (no external DnD dependency needed).

- **`app.spec`** — PyInstaller spec (not `--add-data` CLI flags, to avoid
  the Windows `;` vs. macOS/Linux `:` path-separator split) building
  `--onedir` rather than `--onefile`: the bundled jar is 32MB and Qt adds
  ~100MB, and onefile re-extracts everything to a temp dir on every launch.
  onedir also keeps PySide6's LGPL-covered libraries as separate,
  user-replaceable files.

## Provenance notes

Several implementation details (exact bundletool flag behavior, the
`.apks` zip layout, `keytool` error text and its stdout-vs-stderr quirk)
were verified by decompiling this repo's actual `resources/bundletool.jar`
(currently bundletool 1.18.3) rather than taken from documentation — the
class names referenced in docstrings (`BuildApksCommand`, `SignerConfig`,
`ApkPathManager`, `Password`, `SdkToolsLocator`, `ModuleSplit$SplitType`)
are pointers back to that verification if bundletool's behavior needs
re-checking after a jar upgrade.
