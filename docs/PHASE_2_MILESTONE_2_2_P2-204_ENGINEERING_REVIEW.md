# P2-204 Engineering Review — Language Detection Service

**Task:** P2-204 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-204 (lines 138–156) + §2 Normative Interfaces (lines 40–46) + §3 Normative Configuration (lines 48–66)
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01
**Review scope:** P2-204 implementation only (`metadata/language.py`, `metadata/__init__.py` export, `pyproject.toml` extra, `tests/unit/test_language_detection.py`, implementation report). No code modified.

---

## 1. Specification Compliance

| Frozen requirement (§P2-204 / §2 / §3) | Status | Evidence |
|---|---|---|
| `detect_language(text: str) -> tuple[str, float]` (§2 Public APIs, Objective) | ✅ | `language.py:69` — exact signature; real outputs verified: `en` 0.667, `fr` 0.556, `de` 0.5, `ja` 0.95, empty/no-stopword → `("en", 0.0)` |
| `LanguageDetector` Protocol `detect(text) -> tuple[str, float]` (§2, exact) | ✅ | `language.py:60-66` — `@runtime_checkable`; `isinstance(_Py3LangIdDetector(), LanguageDetector)` verified `True` |
| Internal API `_language_heuristic(text)` (§2 Internal APIs, exact name) | ✅ | `language.py:85` — name matches frozen §2 exactly |
| Lazy `py3langid` import; absent → fallback + debug log (step 1) | ✅ | `_try_import_langid()` (`language.py:115-121`) per `detect()` (`language.py:107`); `ImportError` → `None` → `logger.debug` + `_language_heuristic`. No package-import-time dependency |
| `_language_heuristic`: stopword/character-set for en/fr/de/ja, pure stdlib (step 2) | ✅ | `_STOPWORDS` frozensets (`language.py:33-57`), `_JAPANESE_KANA` (`language.py:30`); only `re`/`math` used |
| Confidence below threshold → `("en", 0.0)` + warning, R7 (step 3) | ✅ | `language.py:77-81` — `confidence < _CONFIDENCE_THRESHOLD` (0.5); boundary semantics `0.5 < 0.5 == False` keeps exactly-at-threshold results (verified `de` 0.5 passes through) |
| Expose `detect_language` + register-able detector per §2 Protocol (step 4) | ✅ | `get_default_language_detector()` lazy singleton + `register_language_detector()` (`language.py:127-138`); `detect_language` exported (`__init__.py:15`, `__all__`:141) — resolves the P2-201 line-63 deferral like P2-203 |
| First ≤ 10 KB only, performance ceiling (step 5) | ⚠️ | Ceiling enforced at the public boundary for every detector (`language.py:76`), `_MAX_TEXT_BYTES = 10_000`; tested (30 KB input → 10 000 units). **Units are characters, not bytes** (O1) |
| Configuration: `language_detection_enabled` (§P2-204 Config row) | ⚠️ | Key exists (`config.py:277`; §3). Gate not consumed here — **correctly owned by P2-205 frozen step 1** ("Classifier calls `detect_language` … when `language_detection_enabled`"), where §P2-205's Config row and §3 rollback ("language detection independently disableable") are enforced. No wired consumer exists today, so no dead-config state (unlike P2-203's F1) — see §5 |
| Testing strategy + DoD: fr/de/ja; short/technical → `en`; absent-`py3langid` still correct; low-confidence → `en` + warning | ✅ | All four covered by distinct tests (§6); fallback proven with `py3langid` genuinely not installed |

## 2. Language Detection Correctness

- **Stopword-density metric** (`best / len(words)`) — deterministic, explainable 0–1 score; ties break to `en` (dict insertion order en/fr/de). ✅
- **Character coverage** — `_WORD` `[a-zà-öø-ÿœæ]+` covers ASCII, Latin-1 diacritics, `ß` (U+00DF), `œ`; text lowercased before matching. Verified umlaut text (`vögel sind auf dem baum …`) → `("de", 0.5)`. ✅
- **Japanese** — kana `[\u3040-\u30ff]` → hardcoded `("ja", 0.95)` per frozen character-set detection. ✅
- **Empty/whitespace/no-word input** → `("en", 0.0)`; no crash; no divide-by-zero (`words` empty → early return `language.py:91`). ✅
- **Langid normalization** — `math.exp(float(log_confidence))` converts langid's log-probability to a probability comparable with the heuristic. ✅
- **Short/technical text** — no stopwords → `("en", 0.0)`, the intended R7 mitigation. ✅
- **O2 — Mixed-language sensitivity:** a single kana character anywhere (even English/technical text) forces `ja` at 0.95, above threshold, so R7 cannot rescue it. Inherent to the frozen character-set approach; P2-205 should be aware kana-punctuated English can misclassify.

## 3. Optional Dependency Handling

- **Truly optional and lazy** — `import langid` only inside `_try_import_langid()`, per `detect()`; the module imports only stdlib + `app.core.logging`. Importing the metadata package never requires py3langid. ✅
- **`py3langid>=0.2.0` added to the `intelligence` extra** (`pyproject.toml:35`) per frozen "Files likely affected"; TOML parse verified valid. Not installed here — heuristic is the tested default, matching frozen intent. ✅
- **Per-call import cost** — after first import, `import langid` is a `sys.modules` dict hit; no re-import. Negligible. ✅
- **O3 — `classify` exceptions propagate.** Only `ImportError` is handled (frozen step 1). A raising `classify` surfaces out of `detect_language`. Frozen scope doesn't mandate catching, and swallowing could mask real failures — acceptable; a `try/except → heuristic` hardening could follow if P2-205 observes flakiness.

## 4. Error Handling & Logging

- `ImportError` → fallback + `logger.debug` sentinel (frozen step 1). ✅
- Empty/blank/no-stopword input → `("en", 0.0)`; never raises. ✅
- Low-confidence path is explicit and loud: `logger.warning` containing "below threshold" (frozen step 3, tested). ✅
- **O4 — Warning noise risk:** every low-confidence call warns, including empty/short documents — common once P2-205 wires ingestion. Spec-mandated, compliant; P2-205 may temper with a warn-once/debug guard for the degenerate empty case.
- `_default_detector` lazy singleton: benign double-create race at worst (equivalent instances); same pattern already accepted for P2-203's `_default_service`. Non-issue.

## 5. Backward Compatibility

- **Additive only** — one new module, one new public export, one additive optional-dependency line. No existing signature, model, or default changed. ✅
- **Zero blast radius today** — `detect_language` has no callers in `app/` (verified by grep); P2-205 is the only frozen consumer and is not yet implemented. ✅
- **Import-cycle safety** — `language.py` imports only stdlib + `app.core.logging`; package import verified clean; full unit suite (which imports the package) passes. ✅
- **Rollback contract (R-4 / §3)** — `language_detection_enabled: false` remains effective once P2-205 lands, because P2-205's step 1 applies the gate at the call site. Unlike P2-203 (classifier wire landed without the gate → F1), P2-204 ships no wire, so there is no dead-config state to remediate. ✅ (note)

## 6. Test Coverage

`tests/unit/test_language_detection.py` — 14 tests, all passing; isolation fixture resets `_default_detector` and drops fake `langid` between tests.

- Heuristic accuracy: en/fr/de (≥ 0.5) + Japanese kana → `("ja", 0.95)`. ✅
- Fallback: empty, whitespace, no-stopword → `("en", 0.0)`. ✅
- Threshold: low-density text → `("en", 0.0)` + "below threshold" warning (caplog). ✅
- 10 KB ceiling: 30 KB input → exactly `_MAX_TEXT_BYTES` units delivered to mocked `classify`. ✅
- py3langid path: mocked `langid` (`("fr", -0.3)`) → `("fr", ≈0.74)`; absent-langid → debug log + heuristic. ✅
- Registry: lazy singleton identity; `register_language_detector` swap; `__all__` pinned. ✅

Gaps (non-blocking): protocol conformance verified manually but not pinned by a test; mixed-language/kana-in-English inputs untested; registered-detector slice untested; the exactly-0.5 boundary is covered only incidentally (German test passes through at 0.5). The frozen testing strategy is fully covered.

## 7. Documentation

- Implementation report (`PHASE_2_MILESTONE_2_2_P2-204_IMPLEMENTATION_REPORT.md`) — Summary/Files/Tests/Results/Gates verified against fresh runs; accurate. ✅
- **No repeat of the P2-203 mislabel:** "Next Recommended Task" correctly names **P2-205 — Language propagation + prompt adaptation**, matching frozen §P2-205. ✅
- Report claims verified: `py3langid` not installed; integration 10 passed / 6 deselected (smoke excluded); ruff 64 baseline; mypy 4 baseline. ✅

## 8. Regression Safety

| Gate | Result |
|---|---|
| `python -m pytest tests/unit -q` | **577 passed / 0 deselected** (baseline 563 + 14 new; 0 regressions) |
| `python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py` | 10 passed / 6 deselected (smoke excluded per convention) |
| `python -m ruff check app tests` | 64 errors — pre-existing baseline; **zero** in changed files |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); changed files clean |
| Import cycles / TOML validity | clean import + full suite pass; `pyproject.toml` parses |

---

## Findings (remediation required)

None.

## Observations (non-blocking)

1. **O1 — 10 KB ceiling is character-based, not byte-based.** `text[:_MAX_TEXT_BYTES]` slices 10 000 *characters*; for CJK UTF-8 that is up to ~30 KB inspected. The bounded-work intent of the frozen "performance ceiling" is fully met (≤ 10 000 units regardless of input length), and char-slicing avoids mid-codepoint corruption, so the literal "10 KB" overage is cosmetic. Either keep as-is and note the semantics, or rename the constant (e.g. `_MAX_TEXT_CHARS`) for honesty.
2. **O2 — Mixed-language sensitivity:** a single kana character forces `ja` at 0.95 regardless of surrounding language. Inherent to frozen character-set detection; R7 threshold cannot intervene. Consider a kana-density guard in P2-205 if misclassification is observed.
3. **O3 — `classify` exceptions are unhandled** beyond `ImportError`. Per frozen step 1; a future `try/except → heuristic` hardening is optional.
4. **O4 — Per-call warning noise:** low-confidence warning fires for every empty/short document once P2-205 wires ingestion. Spec-mandated; temper in P2-205 if noisy.
5. **O5 — Minor test gaps:** protocol conformance, mixed-language input, registered-detector slicing, and the exact 0.5 boundary are not pinned as named tests.

---

## Verdict

✅ **Approved**

P2-204 is fully compliant with the frozen contract: the `detect_language`/`LanguageDetector` interfaces match §2 exactly, the lazy optional `py3langid` path and the pure-stdlib `_language_heuristic` (en/fr/de/ja) implement frozen steps 1–5, the 0.5-confidence threshold returns `("en", 0.0)` with a warning as the R7 mitigation, and the module is exported additively with zero blast radius (no callers yet; P2-205 owns the `language_detection_enabled` gate and propagation per its frozen step 1). Detection correctness is verified with real executions (en 0.667 / fr 0.556 / de 0.5 / ja 0.95 / empty → en 0.0) and the frozen testing strategy plus DoD (fr/de/ja tests, fallback proven with py3langid absent) are fully covered. Regression safety is clean: 577 unit tests pass (563 baseline preserved), integration unaffected, ruff (64) and mypy (4) at pre-existing baselines with zero new findings. The remaining items are minor observations (char-vs-byte ceiling semantics, kana sensitivity, warning noise), none of which block the task; the two ⚠️ rows in the compliance table are resolved by cross-reference to P2-205's frozen gate ownership and by the bounded-work intent of the ceiling. No remediation required.
