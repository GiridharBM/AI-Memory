# Phase 2 — Milestone 2.5 Remediation Report

Date: 2026-08-04
Scope: Required findings from the Principal Engineering Review of Milestone 2.5.
Mandate: apply every Required remediation; re-run unit/integration tests, ruff, mypy; verify every Required finding resolved; no unrelated changes.

---

## Round 1 — Initial Review (verdict: Needs Remediation)

### R1 — Shared `Preprocessor` not wired into the OCR/vision path (Wired, then re-remediated)

**Verdict (round 1):** `intelligence.images.preprocess` and `intelligence.ocr.preprocess` had zero runtime effect. `get_default_ocr_service` never passed a preprocessor to either engine; the shared `imaging/preprocess.py` `Preprocessor` (P2-104, R-3 single module) was never bridged to the engines' bytes contract.

**Round 1 resolution:** `_shared_preprocessor` bridge added, `preprocess=True` hardcoded in `_extract_via_service`, AC2 wiring tests added.

**Re-review verdict:** R1 incompletely resolved — the hardcoded `preprocess=True` at `processor_impls.py:96` and the unconditional `Preprocessor(enabled=True)` in `_shared_preprocessor` meant both toggles remained dead config. Default config (false/false) triggered preprocessing whenever Pillow was installed — violating frozen §4.5/R-4 "preprocess: false ⇒ Phase-1-identical". AC2 unmet at config level.

### R2 — Config `max_dimensions` / `max_bytes` misaligned with frozen §4.5 (Aligned)

**Resolution (confirmed):**

- `ImageSettings.max_dimensions` → `int | tuple[int, int] = (8192, 8192)`: accepts the frozen two-item pair, a scalar int, and a YAML/JSON list; invalid shapes rejected at parse time.
- `ImageSettings.max_bytes` → `Field(default=20 * 1024 * 1024, ge=1)`.
- `config/default.yaml` updated to `max_dimensions: [8192, 8192]`, `max_bytes: 20971520`.
- `_resolve_dim_guard` normalizes scalar/pair; tests assert frozen-spec values and guard behavior.

### R3 — Documentation gate 8 unmet (Updated)

**Resolution (confirmed):** changelog `[0.6.0]` entry, 01 report rows marked implemented, MEDD version 0.6.0, README image-intelligence note.

---

## Round 2 — Re-review Remediation (verdict: Needs Further Remediation → Resolved)

### R1-R — Dead toggles, default regression, config-level AC2 unmet

**Re-review findings:**

1. `processor_impls.py:96` hardcoded `preprocess=True` inside `_extract_via_service` — the single extraction call site used by all three processors.
2. `_shared_preprocessor` constructed `Preprocessor(enabled=True, ...)` unconditionally — registered into both engines regardless of toggles.
3. `DocumentOcrService.extract` and `OcrEngine.run` protocol defaults were `preprocess=True` — callers omitting the flag got unconfigured preprocessing.
4. Default config (false/false) with Pillow installed: preprocessing ran (engine defaulted True + bridge always registered) — violates frozen §4.5/R-4.
5. Tests drove `engine.run(preprocess=True)` directly or asserted `service.extract(..., preprocess=True)` against dead config keys.
6. Docs (README, ImageSettings docstring, MEDD §7.2) described behavior that didn't match runtime.

**Round 2 resolution — five required fixes:**

#### Fix 1 — Eliminate hardcoded `preprocess=True`

`_extract_via_service` signature gained `preprocess: bool = False`. All three processor constructors gained an explicit `preprocess: bool = False` kwarg (stored as `self._preprocess`), passed through to `_extract_via_service`. No production call site contains a literal `preprocess=True`.

| File | Change |
| --- | --- |
| `app/infrastructure/routing/processor_impls.py` | `_extract_via_service(..., preprocess: bool = False)`; `VisionProcessor`, `OCRProcessor`, `HandwritingProcessor` constructors accept `preprocess: bool = False`; all three pass `preprocess=self._preprocess` to `_extract_via_service` |

#### Fix 2 — Wire per-path config toggles

`ingest_workflow.py` `_run_routed_processor` now reads the per-path toggles from `self._settings` and passes them to the processor constructors:

- `VisionProcessor` ← `images.preprocess`
- `OCRProcessor` ← `ocr.preprocess`
- `HandwritingProcessor` ← `ocr.preprocess`

When `self._settings` is `None` (test environments), both default to `False`.

| File | Change |
| --- | --- |
| `app/pipelines/ingest_workflow.py` | `_run_routed_processor`: `ocr_preprocess`, `images_preprocess` wired into processor constructors |

#### Fix 3 — Restore frozen default behavior

- `OcrEngine.run` protocol default: `preprocess: bool = True` → `False`.
- `DocumentOcrService.extract` default: `preprocess: bool = True` → `False`.
- Both `VisionOcrEngine.run` and `TesseractOcrEngine.run`: default `True` → `False`.
- `_shared_preprocessor`: returns `None` when both `ocr.preprocess` and `images.preprocess` are `False`; builds the bridge only when at least one toggle is enabled. Engines receive `preprocessor=None` in the default case → no transformation possible.
- Default config (false/false): no preprocessing → bytes-identical Phase-1 behavior, even when Pillow is installed.

| File | Change |
| --- | --- |
| `app/infrastructure/document_intelligence/ocr/base.py` | Protocol `run(preprocess=False)`, `extract(preprocess=False)` |
| `app/infrastructure/document_intelligence/ocr/engines.py` | Both engines `run(preprocess=False)` |
| `app/infrastructure/document_intelligence/ocr/__init__.py` | `_shared_preprocessor` returns `None` when both toggles off; bridge type annotations updated to `Callable[[bytes], bytes] | None` |

#### Fix 4 — AC2 regression test through production extract path

New `TestConfigDrivenPreprocess` in `tests/unit/test_ocr_engine.py`:

- **`test_preprocess_off_sends_identical_bytes`**: Default config (`preprocess=False`) through `VisionProcessor.process()` → `_extract_via_service` → `service.extract` → spy engine: asserts raw bytes received, `preprocess` flag `False`.
- **`test_preprocess_on_sends_transformed_bytes`**: Config `images.preprocess=True` + `ocr.preprocess=True` → real shared bridge → spy engine mirrors production engine behavior: asserts bytes differ from original AND output is grayscale L-mode (real Pillow CLAHE transform applied).

Factory test `test_engines_receive_the_shared_preprocessor` rewritten: asserts `None` preprocessor with default config (both toggles off), sentinel when at least one toggle on.

#### Fix 5 — Documentation updated

| File | Change |
| --- | --- |
| `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` | §7.2 protocol + `extract` defaults: `True` → `False` (3 spots) |
| `docs/DOCUMENTATION_VERIFICATION_REPORT.md` | Signature rows updated to `preprocess: bool = False` |
| `docs/MEDD_DOCUMENTATION_SYNCHRONIZATION_REPORT.md` | Protocol + extract signature rows updated |
| `docs/02_Current_Project_Status_Report.md` | OCR protocol signature updated |
| `docs/04_Evaluation_Benchmark_Report.md` | Protocol conformance line updated |
| `docs/changelog.md` | 0.6.0 entry rewritten to reflect config-driven wiring, protocol default flip, and AC2 regression test |

---

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Full suite (default, integration deselected) | `pytest -q` | **823 passed / 28 deselected** |
| Hermetic integration | `pytest tests/integration -m integration` minus live-Ollama smoke | **25 passed, 1 skipped** (Tesseract binary absent; live-Ollama smoke excluded as pre-existing) |
| AC2 regression tests | `pytest tests/unit/test_ocr_engine.py -k "TestConfigDrivenPreprocess" -v` | **2 passed** |
| AC2 wiring tests | `pytest tests/unit/test_ocr_engine.py -k "shared_preprocessor or shared_bridge" -v` | **2 passed** |
| Config alignment tests | `pytest tests/unit/test_config.py -k "frozen_spec or dim_guard"` | **2 passed** |
| Lint | `ruff check` on all changed files | **All checks passed** |
| Types | `mypy` on changed source files | **no new errors**; pre-existing numpy-stub/Python-3.14 environment block unchanged |

## Status

All Required findings resolved and verified across two review rounds. The preprocessing path is now fully config-driven: per-path toggles flow from settings through the workflow → processor constructor → `_extract_via_service` → `service.extract` → engine. Default config (false/false) means no preprocessing, bytes-identical Phase-1 behavior. Recommended (non-blocking) items from the reviews were intentionally not touched.
