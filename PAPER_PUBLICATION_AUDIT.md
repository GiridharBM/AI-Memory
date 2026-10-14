# PAPER PUBLICATION AUDIT

**Paper audited:** `research/PAM_IEEE_Research_Paper_A4_FINAL_PRE_OPENCODE_REVIEW.docx`
**Audit date:** 2026-09-11
**Auditor:** independent read-only OpenCode pass
**Scope:** full claim → evidence verification against the live PAM repository, frozen evaluation artifacts, and the DOCX itself. Nothing in the repo or paper was modified.

---

## 1. Executive verdict

**Status: NOT READY TO PUBLISH.**

The paper's scientific content is accurate: **every numerical claim verified against the frozen artifacts, every implementation claim verified against the code, every citation verified as real, relevant, and correctly placed, and all scoping caveats are present and correctly worded.** No number was found wrong, and no unsupported overclaim was found.

However, two blockers remain:

- **P0 metadata blocker:** The mentor line reads `Mentored by: Santhosh Kumar J, Hemachandra Reddy` — the requested final wording `Mentored by: Dr.Santhosh Kumar J, Dr.Hemachandra Reddy` is not matched (`Dr.` prefixes missing).
- **P0 formatting blocker:** The DOCX package contains 8 figure PNGs, but **none of them is referenced anywhere in the document body** (zero `w:drawing` / `a:blip` / `r:embed` / `wp:inline` / `wp:anchor` elements in `document.xml`, header, or footer; `python-docx` reports 0 inline shapes; image relationship IDs `rId9–rId11, rId14–rId18` are never referenced by any XML part). The figure captions (Fig. 1–3, Fig. A1–A5) exist as text, but **the images will not render** when the DOCX is opened or converted to PDF.

Both must be fixed before the paper is publication-ready.

---

## 2. P0 / P1 / P2 blocker list

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| B1 | **P0** | Mentor line lacks `Dr.` prefixes; does not match `Mentored by: Dr.Santhosh Kumar J, Dr.Hemachandra Reddy` | Edit line 6 of the DOCX |
| B2 | **P0** | All 8 figures are present in `word/media/` but never embedded/referenced in the document body; captions render without images | Re-insert the 8 PNGs at their captions and re-export |
| B3 | P2 | Subsection letters run in reverse within every section (e.g. Related Work: G, F, E, D, C, B, A) | Re-letter subsections A→… for standard IEEE order (optional) |
| B4 | P2 | Equations (RRF formula, cosine-similarity formula) are plain text with Unicode glyphs, not OMML equation objects | Convert to native equations if the venue requires it (optional) |
| B5 | P2 | Repo-internal inconsistency (does **not** affect the paper): Phase 5F headline band `[0.45, 0.62)` in the report vs `[0.45, 0.64]` in `phase_5f_experiment_b.json` metadata; `phase_5f_experiment_a.json`/`b.json` store only `metadata`+`queries` (no `metrics` key) — FPR/FNR values live in the report, not the JSON | Harmonize artifact metadata (optional) |
| B6 | P2 | Reference [1] cites `in Proc. NeurIPS, 2020`; [5] cites an arXiv preprint — both accurate, but consider tightening venue/year formatting for consistency | Optional |
| B7 | Info | Reference list has only [1]–[6]. Per instructions, this is **acceptable**: all 6 are real, relevant, and cited in text. Do **not** pad to 15. | No action |

---

## 3. Claim → evidence table

Every claim below was verified against the artifact in the right-hand column. All PASS.

| # | Paper claim | Evidence | Verdict |
|---|---|---|---|
| C1 | Frozen corpus: 24 sources, 195 chunks, 199 queries (157 pos / 42 neg) | `phase_5d_frozen_baseline.json` metadata + metrics; `dataset.json` (199 queries, metadata version 3.0) | PASS |
| C2 | Hit@1 = 0.8408 | `phase_5d_frozen_baseline.json` metrics `hit_rate@1: 0.840764…` | PASS |
| C3 | Hit@3 = 0.9108 | JSON `hit_rate@3: 0.910828…` | PASS |
| C4 | Hit@5 = 0.9236 | JSON `hit_rate@5: 0.923566…` | PASS |
| C5 | Hit@10 = 0.9236 | JSON `hit_rate@10: 0.923566…` | PASS |
| C6 | MRR = 0.8773 | JSON `mrr: 0.877282…` | PASS |
| C7 | FPR = 0.8571 (36/42) | JSON `false_positive_rate: 0.857142…`; FP inventory in Phase 5E §6 | PASS |
| C8 | FNR = 0.0000 | JSON `false_negative_rate: 0.0` | PASS |
| C9 | Negative rejection = 0.1429 (6/42) | JSON `negative_rejection_rate: 0.142857…` | PASS |
| C10 | Abstention rate = 0.0302 | JSON `abstention_rate: 0.030150…` | PASS |
| C11 | Latency p50 = 37.4 ms | JSON `retrieval_latency_ms.p50: 37.4` | PASS |
| C12 | Latency p95 = 47.1 ms | JSON `retrieval_latency_ms.p95: 47.1` | PASS |
| C13 | Latency max = 7299.3 ms | JSON `retrieval_latency_ms.max: 7299.3` | PASS |
| C14 | top_k = 5 for frozen baseline | JSON config `top_k: 5` | PASS |
| C15 | min_cosine = 0.45 (academic) | JSON config `min_cosine: 0.45` | PASS |
| C16 | Reranker, HyDE, answerability disabled for baseline | JSON config all `false`/disable | PASS |
| C17 | BM25 k1=1.5, b=0.75 | `app/infrastructure/bm25.py:33-34` | PASS |
| C18 | RRF k=60 | `app/infrastructure/search.py:67,153` | PASS |
| C19 | nomic-embed-text, 768-dimensional | `app/core/config.py:200`; docs `02_...`: dimensions 768 | PASS |
| C20 | qwen3:8b is the local QA model | `app/core/config.py:70,194` | PASS |
| C21 | Runtime default min_cosine is lower than 0.45 | `app/application/qa_workflow.py:287,385,450` = 0.25; paper explicitly states the academic threshold ≠ shipped default | PASS |
| C22 | Knowledge graph stored but NOT in evaluated retrieval path | `app/infrastructure/search.py` RRF(dense+BM25) only; no KG reference in search/qa_workflow | PASS |
| C23 | Context limit 8 chunks / 12,000 characters | `app/application/qa_workflow.py:48-49` (`MAX_CONTEXT_CHUNKS=8`, `MAX_CONTEXT_CHARS=12_000`) | PASS |
| C24 | GitHub/YouTube are explicit network-source operations | `app/cli/entry.py:134-145` (`ingest github` / `ingest youtube`) | PASS |
| C25 | No absolute "nothing leaves the machine" claim | Paper §III.E states "local-first rather than universally offline" | PASS |
| C26 | Reranker experiments NOT on final 199-query corpus | Paper §III.E, §VLE, §VIII.C; verified: v1=50q, v2=160q | PASS |
| C27 | v1 reranker: Hit@1 0.907→0.837, Hit@5 0.953, MRR 0.940→0.895 | `16_PHASE_3C_RERANKING_IMPLEMENTATION_RESULTS.md` §12 table (rows 175-178) | PASS |
| C28 | v2 threshold sweep t=0.125: FPR ~0.351, FNR ~0.203 | `reranker_eval.json`: FPR 0.3514, FNR 0.2033; metadata min_rerank_score=0.125 | PASS |
| C29 | Reranker latency ~850 ms (no gate, v1) | `16_PHASE_3C...` §14/§18: ~22 ms → ~850 ms | PASS |
| C30 | Reranker gate t=0.125 latency ~644 ms | `reranker_eval.json` metrics `avg_query_time_ms: 643.8` | PASS |
| C31 | Strict verifier: v2/160q, FPR ~0.243, FNR ~0.098, ~2.9–3.0 s | `answerability_eval.json`: FPR 0.2432, FNR 0.0976, avg_query 2898.7 ms, answerability 3005.8 ms | PASS |
| C32 | Banded verifier: frozen 199q, FPR 0.405, FNR 0.070, ~14.1 s avg, ~17.3 s p95 | `32_PHASE_5F_...` §9-10 (0.4048 / 0.0701); `phase_5f_experiment_b.json` verifier latency avg 14110.8 / p95 17296.9 ms | PASS |
| C33 | Frozen baseline reproduced in later experiment (199/199) | `32_PHASE_5F_...` §5: Experiment A matches Phase 5D on all 199/199, mismatch 0 | PASS |
| C34 | 31/36 false positives are content-sufficiency failures | Phase 5E §6 table: A=5, B=16, C=2, E=2, F=11 → B+C+E+F = 16+2+2+11 = 31 | PASS |
| C35 | 6 negatives correctly rejected, all Category A, cos < 0.45 (q032, q116, q117, q136, q138, q139) | Phase 5E §6/5F §4 | PASS |
| C36 | Live corpus drift: 30 sources / 299 entries vs frozen 24/195 | `data/manifests/vector_store.json`: 299 entries, 30 unique sources | PASS |
| C37 | Three queries flagged unreliable (q033, q036, q050) | `dataset.json` `ground_truth_reliable=false` for q033, q036, q050; Phase 5 doc §... | PASS |
| C38 | Guardrails existed pre-hoc (FNR ≤ 0.033, Hit@5 ≥ 0.93, MRR ≥ 0.88, FPR materially < 0.811 target ≤ 0.5, p95 < 500 ms) | `33_PHASE_5G_V1_RETRIEVAL_DECISION.md` line 24: "Guardrails (NOT relaxed) … user mandate" | PASS |

---

## 4. Numerical consistency table

All values in the paper's Table I and the Results table match `phase_5d_frozen_baseline.json` exactly (see C1–C13). Table II rows:

| Table II row | Paper value | Artifact | Verdict |
|---|---|---|---|
| Frozen hybrid + cosine gate (199q) | FPR 0.8571, FNR 0.000, 47.1 ms p95 | `phase_5d_frozen_baseline.json` | PASS |
| Cross-encoder no gate (50q v1) | FPR 1.000, FNR 0.000, ~850 ms | `16_PHASE_3C…` (§12, §18) | PASS |
| Cross-encoder gate t=0.125 (160q v2) | FPR 0.351, FNR 0.203, ~644 ms | `reranker_eval.json` | PASS |
| Strict evidence verifier (160q v2) | FPR ~0.243, FNR ~0.098, ~2.9 s | `answerability_eval.json` | PASS |
| Banded evidence verifier (199q) | FPR 0.405, FNR 0.070, 14.1 s avg / 17.3 s p95 | `32_PHASE_5F_…` + `phase_5f_experiment_b.json` | PASS |

Abstract/RQ/Discussion/Conclusion numbers (Hit@5 0.9236, MRR 0.8773, FPR 0.8571, 31/36, 47.1 ms p95, 37.4 ms p50, 0.0302 abstention) are internally consistent across all sections and match the frozen artifact.

---

## 5. Experiment / dataset matrix (staging verified)

| Experiment | Dataset | Corpus | Paper states correctly? |
|---|---|---|---|
| Frozen baseline / reproduction | v3.0 frozen (199q = 157/42) | 24 sources / 195 chunks | YES |
| Reranker (3C) | v1 (50q = 43/7) | 12 docs / 101 chunks | YES — not presented as final-corpus result |
| Reranker threshold sweep | v2 (160q, 37 neg) | 101 chunks | YES |
| Strict evidence verifier (3G-B) | v2 (160q) | 101 chunks | YES |
| Banded evidence verifier (5F) | v3.0 frozen (199q) | 24/195 | YES |
| Live runtime (post-freeze) | — | 30 sources / 299 entries | YES — reported separately from academic baseline |

The paper never merges these into a single head-to-head leaderboard (explicit language in §I.J, §VI, §VII.E, §VIII.C). PASS.

---

## 6. Citation → source table

| Ref | Claim it supports in paper | Bibliographic identity | Cited in text? | Verdict |
|---|---|---|---|---|
| [1] | RAG = LLM + external memory, retrieval-conditioned generation | Lewis et al., NeurIPS 2020, arXiv:2005.11401 | YES (§I, §II.A) | PASS — real, relevant |
| [2] | Dense retrieval / embedding similarity | Karpukhin et al., EMNLP 2020, pp. 6769-6781, DOI 10.18653/v1/2020.emnlp-main.550 | YES (§I, §II.B) | PASS |
| [3] | BM25 lexical retrieval | Robertson & Zaragoza, FnTIR 3(4), 2009, DOI 10.1561/1500000019 | YES (§I, §II.C, §IV.B) | PASS |
| [4] | RRF rank fusion | Cormack, Clarke, Büttcher, SIGIR 2009, pp. 758-759, DOI 10.1145/1571941.1572114 | YES (§I, §II.D, §IV.C) | PASS |
| [5] | Neural/BERT passage reranking | Nogueira & Cho, arXiv:1901.04085, 2019 | YES (§II.E) | PASS |
| [6] | Evidence sufficiency / answer-abstention calibration | Zhang & Wu, CMC 89(1):69, 2026, DOI 10.32604/cmc.2026.086343 | YES (§II.F) | **PASS — verified live against publisher page (article 68467)** |

No dangling citations, no uncited bibliography entries, no duplicate references, no incorrect DOIs, no incorrect author names, no incorrect venues/years.

---

## 7. Wording / banned-phrase scan

Scanned full extracted text. **None** of the banned phrases appear:
- ✗ "PAM achieves 92.36% accuracy" → paper uses `Hit@5 = 0.9236` ✓
- ✗ "PAM has 85.71% error" → paper uses `FPR = 0.8571` on negative set ✓
- ✗ "reranking improves PAM" → paper says it "did not establish a reliable improvement" ✓
- ✗ "answerability verification solves false positives" → paper says it trades FPR for FNR/latency and fails §ir guardrails ✓
- ✗ "nothing leaves the machine" → paper says "local-first rather than universally offline" ✓
- ✗ "the knowledge graph improves retrieval" → paper says KG "is not queried by the evaluated retrieval path" ✓
- ✗ "reranker validated on final 199-query dataset" → paper explicitly excludes this ✓
- ✗ "all experiments use the same corpus" → paper explicitly disclaims per-dataset measurement ✓
- ✗ "PAM completely prevents hallucination" → no such claim ✓

Overclaim audit: conclusions are bounded ("The findings suggest…", "should be interpreted as evidence for this controlled evaluation"). FPR is not characterized as an answering-layer defect in absolute terms; it is framed as a measured reliability failure at the evidence-sufficiency boundary, which the artifacts support (B+C+E+F = 31/36). PASS.

---

## 8. Figure / table audit

| Item | Caption in paper | Image present in package? | Image embedded in body? | Verdict |
|---|---|---|---|---|
| Fig. 1 | PAM system architecture | YES (image1.png) | **NO — not referenced** | **FAIL (B2)** |
| Fig. 2 | PAM ask command, grounded answer with [SOURCE N] | YES (image2.png) | **NO** | **FAIL (B2)** |
| Fig. 3 | Failure analysis of FPs | YES (image3.png) | **NO** | **FAIL (B2)** |
| Fig. A1 | CLI help | YES (image4.png) | **NO** | **FAIL (B2)** |
| Fig. A2 | status output | YES (image5.png) | **NO** | **FAIL (B2)** |
| Fig. A3 | doctor output | YES (image6.png) | **NO** | **FAIL (B2)** |
| Fig. A4 | ingestion workflow | YES (image7.png) | **NO** | **FAIL (B2)** |
| Fig. A5 | search command | YES (image8.png) | **NO** | **FAIL (B2)** |
| Table I | Frozen baseline results | — | Values match JSON exactly | PASS |
| Table II | Reliability interventions | — | Values match artifacts exactly | PASS |

The appendix explicitly states screenshots are "demonstrations of the current runtime and are not used to compute the frozen academic evaluation metrics," so there is no figure-as-evaluation-evidence overclaim. Captions correspond to intended images (by content description). The only defect is that the images are not actually embedded.

---

## 9. Formatting audit

| Check | Result |
|---|---|
| A4 page size | PASS (pgSz 11906×16838 twips) |
| Single-column layout | PASS (as intentionally requested) |
| Margins | PASS (top 1077 / bottom 1417 / left+right 1020 twips — consistent) |
| Title/author/affiliation/email block | PASS (present, readable) |
| Mentor line | **FAIL (B1)** — missing `Dr.` prefixes |
| Section numbering (I–IX + appendices) | PASS |
| Subsection numbering | P2 — letters run in reverse order within each section (B3) |
| Figure numbering | PASS (Fig. 1–3, A1–A5 in order) |
| Table numbering | PASS (TABLE I, TABLE II, captioned) |
| Orphaned headings | Not detected |
| Blank pages / clipped figures | Figures absent entirely (B2) — no clipping |
| References formatting | PASS (hanging indent, no split entries) |
| Footer/page-number artifacts | PASS (footer empty, no artifacts) |
| Tracked changes / comments | PASS (0 `w:ins`, 0 `w:del`, no comments.xml) |
| Placeholder text | PASS (none found) |
| Broken equations/symbols | PASS — all unicode glyphs (≤ ≥ Σ ∈ ·  — "" ü) correctly encoded; **0 replacement chars (U+FFFD)** |
| Font substitution | PASS — Times New Roman + Courier New only |
| PDF vs DOCX consistency | **Cannot verify** — no PDF provided, no Word/LibreOffice renderer available; DOCX internal state audited directly |

---

## 10. Publication integrity audit

- Unsupported claims: none found.
- Claims without citations: none found (all substantive literature claims are cited).
- Citations without entries / entries never cited: none.
- Duplicate references: none.
- Incorrect author names / venues / years / DOIs: none (all 6 verified).
- Inconsistent terminology: none (FPR/FNR/abstention/guardrail terminology consistent).
- Unexplained acronyms: none (all defined at first use).
- Numerical contradictions: none found within the paper or vs artifacts.
- Conclusions stronger than experiments: no — appropriately scoped to controlled personal-memory corpus.

---

## 11. Reproducibility / corpus-drift audit

Searched the paper for "299", "195", "24", "199", "0.9236", "0.8773", "0.8571", "0.25", "0.45":
- "299" only as the **live** corpus (30 sources / 299 entries), explicitly contrasted with frozen state — PASS.
- "195"/"24"/"199" always refer to the frozen academic state — PASS.
- "0.9236"/"0.8773"/"0.8571" always the frozen baseline values — PASS.
- "0.45" is always the academic evaluation threshold; "0.25" never appears as a production claim (paper only says the shipped default is a "lower min_cosine value" — accurate; does not over-specify) — PASS.
- Paper explicitly separates frozen baseline reproducibility from live runtime drift (§IV.E, §VI.B, §VIII.D) — PASS.

---

## 12. Guardrail audit

- FNR ≤ 0.033; Hit@5 ≥ 0.93; MRR ≥ 0.88; FPR materially < 0.811 (target ≤ 0.5); p95 < 500 ms — verified pre-existing in `33_PHASE_5G_V1_RETRIEVAL_DECISION.md` (explicitly labeled "NOT relaxed … user mandate"), not invented retrospectively. PASS.
- Comparisons respect the dataset each experiment ran on. PASS.
- No intervention is declared successful just because it improves one metric (reranker and both verifiers are marked Rejected). PASS.

---

## 13. Verification of the two "reference list completeness" concerns from the brief

- **Reference list [1]–[6] only:** Confirmed as the paper's actual state. Per explicit instruction, references are **not** inflated to 15; all six are real, verified, and cited at their supported claims. **Not a blocker.**
- **Mentor line:** Confirmed mismatch (B1). **Blocker.**

---

## 14. Final OpenCode acceptance checklist

- [x] Repository facts independently verified
- [x] Frozen baseline independently verified
- [x] Every numerical result verified
- [x] Every experiment's dataset identified
- [x] Reranker limitation preserved
- [x] Verifier limitation preserved
- [x] Failure taxonomy verified (A5+B16+C2+E2+F11 = 36; content-sufficiency 31/36)
- [x] 31/36 calculation verified
- [x] Runtime/frozen corpus distinction verified
- [x] Academic threshold/runtime default distinction verified
- [x] Privacy claims verified (local-first, not universally offline)
- [x] Knowledge-graph non-use verified
- [x] All citations mapped to actual supporting claims
- [x] All bibliography entries verified (6/6)
- [x] No dangling citations
- [ ] ~~No uncited major literature claims~~ (nothing found)
- [x] No overclaiming
- [ ] Figures verified visually — **FAIL**: figures not embedded (B2)
- [x] Tables verified numerically
- [ ] DOCX/PDF consistency — cannot verify (no PDF); DOCX internals audit clean except B2
- [ ] Mentor metadata verified — **FAIL** (B1)
- [x] Final formatting verified (except B3/B4 optional items)
- [x] No tracked changes/comments/placeholders
- [ ] **Final verdict = READY TO PUBLISH — NOT YET (B1 and B2 block)**

---

## 15. Required corrections before publication

1. **B1 (P0):** Change line 6 to `Mentored by: Dr.Santhosh Kumar J, Dr.Hemachandra Reddy`.
2. **B2 (P0):** Re-insert the 8 figure images (present in the DOCX package) at their captions so they render, then re-export.
3. Optionally: normalize subsection letters to forward order (B3) and convert equations to native math (B4).
4. Re-run a PDF render after fixes to confirm figures and pagination.

After B1 and B2 are fixed and visually confirmed, the paper is publication-ready on all audited scientific and integrity dimensions.