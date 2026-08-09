# Milestone 2.2 — Optional-Dependency Wheel Preflight

**Milestone gate item:** Spec §8 #11 / baseline R-5, R-11 — verify that optional dependencies resolve as installable wheels on the supported platform before the milestone gate is approved.
**Platform:** `cp314-win_amd64` (CPython 3.14.6, `win32` / `win-amd64` ABI, Windows)
**Verification date:** 2026-08-01
**Verified by:** Principal Release Engineer (independent re-verification; packages are not installed in the project environment)

---

## 1. Summary

Both Milestone 2.2 optional dependencies resolve as **pure-Python (`none-any`) wheels** on the target platform. Neither wheel contains compiled extensions, so there is no CPython-3.14 ABI or build-toolchain dependency. The Milestone 2.2 gate item is **✅ verified**.

The packages are optional and declared only in the `intelligence` extra of `pyproject.toml` (`[project.optional-dependencies]`); the system runs fully without them (see §6).

| Package | Version | Wheel | Size | Purelib | Installable on cp314-win_amd64 |
|---|---|---|---|---|---|
| `python-magic` | 0.4.27 | `python_magic-0.4.27-py2.py3-none-any.whl` | 13.5 KB | ✅ `Root-Is-Purelib: true` | ✅ |
| `py3langid` | 0.3.0 | `py3langid-0.3.0-py3-none-any.whl` | 728.6 KB | ✅ `Root-Is-Purelib: true` | ✅ |

## 2. Verification Method

```
python -m pip download --no-deps --only-binary :all: python-magic py3langid -d <temp>
```

- pip 26.1.2, Python 3.14.6 (`cp314-win_amd64`).
- `--only-binary :all:` forces a wheel-only resolve — a package with no wheel available for this platform would **fail** the download, proving resolvability rather than assuming it.
- Wheel metadata read back from the `.dist-info/WHEEL` of each downloaded artifact:

```
== python_magic-0.4.27-py2.py3-none-any.whl ==
Wheel-Version: 1.0
Generator: bdist_wheel (0.37.0)
Root-Is-Purelib: true
Tag: py2-none-any
Tag: py3-none-any

== py3langid-0.3.0-py3-none-any.whl ==
Wheel-Version: 1.0
Generator: bdist_wheel (0.43.0)
Root-Is-Purelib: true
Tag: py3-none-any
```

Download succeeded for both packages; no source-only fallback occurred.

## 3. Package Details

### 3.1 python-magic (MIME detection, ADR-001)

| Field | Value |
|---|---|
| Declared | `python-magic>=0.4.27` (`intelligence` extra, `pyproject.toml:34`) |
| Resolved version | **0.4.27** |
| Wheel | `python_magic-0.4.27-py2.py3-none-any.whl` |
| Wheel type | Universal pure-Python (`py2.py3-none-any`), `Root-Is-Purelib: true` |
| Binary compatibility | ✅ ABI-independent; no compiled extension, no build step |
| Consumed by | `app/infrastructure/document_intelligence/metadata/mime.py` `_magic_from_header` (lazy `import magic`) |

### 3.2 py3langid (language detection, P2-204)

| Field | Value |
|---|---|
| Declared | `py3langid>=0.2.0` (`intelligence` extra, `pyproject.toml:35`) |
| Resolved version | **0.3.0** |
| Wheel | `py3langid-0.3.0-py3-none-any.whl` |
| Wheel type | Pure-Python (`py3-none-any`), `Root-Is-Purelib: true` |
| Binary compatibility | ✅ ABI-independent; no compiled extension, no build step |
| Consumed by | `app/infrastructure/document_intelligence/metadata/language.py` `_Py3LangIdDetector` (lazy `import langid`) |

## 4. Binary Compatibility Analysis

`cp314` is a new CPython ABI; the preflight's purpose is to confirm these optional deps do **not** require an ABI-tagged (`cp314-cp314-win_amd64`) or ABI-agnostic-with-extensions wheel.

- **python-magic 0.4.27** — pure Python (`None`, `any` ABI tags). It *wraps* the native libmagic library at runtime (see §5), but ships no compiled code itself and therefore needs no wheel/tag build for Python 3.14.
- **py3langid 0.3.0** — pure Python including its embedded language model (~700 KB in the wheel). No native runtime dependency.

Both install cleanly on `cp314-win_amd64` with no compiler, no `pip install` build backend, and no sdist fallback.

## 5. Runtime Notes

### python-magic
- The pip package is a thin pure-Python binding. **It requires the native `libmagic` library (`magic1.dll` on Windows) to be present at runtime**; the wheel itself does not bundle the DLL.
- If `magic1.dll` is absent, `magic.from_buffer(header, mime=True)` raises (`OSError`/`FileNotFoundError`) rather than crashing the process — `mime.py` catches it and falls through to the stdlib sniff (see §6).
- python-magic is a **pure enhancement**: detection works without it, so no OS-level install (e.g. chocolatey `libmagic`/MSYS2 `mingw-w64-file`) is required for the milestone to function.

### py3langid
- Pure Python; no native runtime dependency, no external model download (model ships inside the wheel).
- `langid.classify(text)` returns `(lang, log_probability)`; the code converts with `math.exp` to a `[0,1]`-ish confidence.

## 6. Fallback Behavior (when the package is absent)

| Package | Absent → behavior | Where |
|---|---|---|
| `python-magic` | One `logger.warning` (warn-once) — "python-magic is not installed; using the stdlib MIME sniff fallback." Detection continues via the stdlib `_sniff_mime` magic-number table (PDF, zip, PNG/JPEG/GIF/WebP, WAVE/Ogg/MP3, XML, HTML, JSON, Markdown heuristic, plain-text). | `mime.py:70-77` |
| `python-magic` present but `magic1.dll` missing | `magic.from_buffer` raises → caught (`except Exception`) → silent fallthrough to `_sniff_mime`; no crash. | `mime.py:78-82` |
| `py3langid` | Debug-level log; detection falls back to the pure-stdlib `_language_heuristic` (stopword/character-set scoring for en/fr/de/ja). | `language.py:106-112` |
| Both absent | The classifier still populates kind by extension; extensionless files get MIME via `_sniff_mime`; language defaults to the heuristic. No code path imports either package unconditionally (both are lazy imports). | `classifier.py`, `mime.py`, `language.py` |

The 605-unit / 14-integration test suites run with **both packages absent** in the live environment, and the fallback paths are covered by dedicated tests (M2.2 P2-203/P2-204 reviews).

## 7. Risks

| Risk | Severity | Notes |
|---|---|---|
| `cp314` ABI: pip could not resolve a wheel and silently build from sdist | Eliminated | `--only-binary :all:` proved wheel-only resolution; both wheels are pure Python |
| libmagic runtime DLL missing on Windows | Medium | Only affects python-magic; the package is a pure enhancement (ADR-001) |
| Version drift on a future resolve (e.g. 0.4.28 / 0.3.1) | Low | Lower-bound constraints `>=0.4.27` / `>=0.2.0`; any future release must keep the pure-Python wheel property to avoid the build-from-sdist risk |
| Over-wide lower bound allowing an incompatible future release | Low | Both libs are stable and pure-Python; re-run this preflight if bounds change |

## 8. Mitigations

1. **No-build guarantee:** `pip download --no-deps --only-binary :all:` (this record). A future resolve that drops to an sdist would be caught by re-running this command.
2. **Optionality (R-5):** both packages live only in the `intelligence` extra; the base install and the milestone's core features do not require them.
3. **Graceful degradation:** lazy imports plus the stdlib MIME fallback table and the stdlib language heuristic guarantee the system functions with neither package present (verified by the M2.2 test suite, which runs with both absent).
4. **Extension-first detection (ADR-001):** known file extensions resolve without touching content, so MIME sniffing (and its libmagic dependency) is only exercised for extensionless/unknown-extension files.
5. **Re-verification trigger:** re-run this preflight whenever `pyproject.toml` dependency bounds for `python-magic` or `py3langid` change.

## 9. Result

**✅ PASS — `cp314-win_amd64` wheel preflight for `python-magic` and `py3langid` completed and recorded.** No blocking risk for the Milestone 2.2 gate (spec §8 #11 / R-5 / R-11).

---

## 10. References

- `docs/PHASE_2_MILESTONE_2_2_FINAL_APPROVAL.md` — gate finding R2 (this record was the missing evidence).
- `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` — preflight step 0 (line 252), §8 #11.
- `docs/PHASE_2_MILESTONE_2_2_SPECIFICATION_FREEZE.md` — freeze Assumption 1, R-5/R-11.
- `pyproject.toml:29-36` — `intelligence` optional-dependencies extra.
