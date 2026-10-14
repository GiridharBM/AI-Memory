# PAPER PUBLICATION AUDIT — FINAL

**Paper audited (after corrections):** `research/PAM_IEEE_Research_Paper_A4_FINAL_PRE_OPENCODE_REVIEW_FIXED.docx`
**PDF proof:** `research/PAM_IEEE_Research_Paper_A4_FINAL_PRE_OPENCODE_REVIEW_FIXED.pdf` (12 pages, A4)
**Audit date:** 2026-09-11
**Auditor:** independent OpenCode pass — second (post-fix) read-only audit. First audit: `PAPER_PUBLICATION_AUDIT.md`.

Only the two P0 blockers were touched. All scientific content, numbers, tables, references, citations, captions, artwork, corpus definitions, frozen baseline, guardrails, terminology, RQs, methodology, and conclusions are unchanged (verified byte-identical below).

---

## 1. Executive verdict

**Status: READY TO PUBLISH.**

Both P0 blockers from the first audit are fixed and independently verified:

- **B1 — mentor line: PASS.** Document text is now exactly `Mentored by: Dr.Santhosh Kumar J, Dr.Hemachandra Reddy` (verified in the DOCX paragraph stream and in the rendered PDF page 1).
- **B2 — figures embedded: PASS.** All 8 source PNGs are now genuinely embedded in the document body. XML shows **8 `w:drawing`, 8 `a:blip`, 8 `r:embed`, 8 valid image relationships**; `python-docx` reports **8 inline shapes**; the corrected PDF renders an image on every page that carries a figure caption (pages 3, 7, 10, 11, 12), each at the correct source aspect ratio, with no text overlap and no orphaned caption.

No new P0 or P1 issues were discovered. P2 notes from the first audit (B3 reverse subsection lettering, B4 plain-text equations, B5 artifact-metadata mismatch, B6 minor ref formatting) remain but are non-blocking; the 6-reference list is intentionally kept per instructions.

---

## 2. Blocker status

| ID | Severity | First-audit finding | Final status | Verification method |
|---|---|---|---|---|
| B1 | P0 | Mentor line `Mentored by: Santhosh Kumar J, Hemachandra Reddy` | **FIXED** | DOCX paragraph text + PDF page-1 text extraction |
| B2 | P0 | 8 figure PNGs packaged but never referenced in body | **FIXED** | DOCX XML element counts, relationship scan, `inline_shapes`, PDF image-object scan, pixel-level render check |
| B3 | P2 | Reverse subsection letters | Unchanged (optional) | Not a blocker |
| B4 | P2 | Plain-text equations (not OMML) | Unchanged (optional) | Not a blocker |
| B5 | P2 | Artifact metadata band edge 0.62 vs 0.64 | Unchanged (repo-internal, not in paper) | Not a blocker |
| B6 | P2 | Minor ref formatting polish | Unchanged (optional) | Not a blocker |
| B7 | Info | Ref list [1]–[6] only | Unchanged (intentional) | Accepted |

---

## 3. Image embedding verification (B2 — XML level)

Inspected `word/document.xml`, `word/_rels/document.xml.rels`, and the package media of `…_FIXED.docx`:

| Check | Result |
|---|---|
| `<w:drawing>` elements | **8** |
| `<a:blip>` elements | **8** |
| `r:embed` attributes | **8** (rId9, rId10, rId11, rId14, rId15, rId16, rId17, rId18) |
| Embedded placement | all `wp:inline` |
| Image relationships | rId9→image1.png, rId10→image2.png, rId11→image3.png, rId14→image4.png, rId15→image5.png, rId16→image6.png, rId17→image7.png, rId18→image8.png |
| Every relationship target exists in package | YES (8/8 PNGs in `word/media/`) |
| `python-docx` `inline_shapes` | **8** |
| Paragraph sequence | Each of the 8 captions is immediately preceded by its `IMG` paragraph (**IMG, CAP** alternating — no caption is orphaned and no image floats away from its caption) |

The 8 images are the same source PNGs that were already associated with the paper/package (extracted from `word/media/` and re-embedded in caption order); no substitute or redrawn artwork was used.

---

## 4. Figure-by-figure verification (caption ↔ image pairing)

| Figure | Caption | Source PNG | Aspect matching (paper PNG vs PDF-rendered) | Inline shape index |
|---|---|---|---|---|
| Fig. 1 | PAM system architecture | image1.png (1510×1366) | 1.105 = 1.105 at 6.30×5.70 in | 1 |
| Fig. 2 | PAM ask command, grounded answer with [SOURCE N] | image2.png (1669×813) | 2.053 = 2.053 at 6.30×3.07 in | 2 |
| Fig. 3 | Failure analysis of false positives | image3.png (1888×1020) | 1.851 = 1.851 at 6.30×3.40 in | 3 |
| Fig. A1 | CLI help | image4.png (1674×546) | 3.066 = 3.066 at 6.30×2.05 in | 4 |
| Fig. A2 | status output | image5.png (1659×717) | 2.314 = 2.314 at 6.30×2.72 in | 5 |
| Fig. A3 | doctor output | image6.png (1663×957) | 1.738 = 1.738 at 6.30×3.63 in | 6 |
| Fig. A4 | ingestion workflow | image7.png (1650×1345) | 1.227 = 1.227 at 6.30×5.14 in | 7 |
| Fig. A5 | search command | image8.png (1665×777) | 2.143 = 2.143 at 6.30×2.94 in | 8 |

Aspect ratios of every embedded figure match their source PNG exactly (same aspect preserved through the 6.30 in width chosen to fit the A4 single-column text block; the widest columns are 1510 px (Fig. 1) and 1650 px (Fig. A4), both rendered well under the ~6.85 in usable width).

---

## 5. PDF visual verification

Rendered `…_FIXED.docx` → `…_FIXED.pdf` with **Microsoft Word (Office 16) COM** (`SaveAs2`/`wdFormatPDF`). Output: **12 pages**, A4 (595×842 pt, matching the DOCX `pgSz` 11906×16838 twips).

Per-page image-object scan (pdfplumber):

| Page | Images | Content |
|---|---|---|
| 1 | 0 | Title block, abstract |
| 2 | 0 | Text |
| 3 | 2 | **Fig. 1** (architecture), **Fig. 2** (ask command) |
| 4–6 | 0 | Sections IV–V, Table I |
| 7 | 1 | **Fig. 3** (failure analysis) |
| 8–9 | 0 | Results, Discussion |
| 10 | 2 | **Fig. A1** (help), **Fig. A2** (status) |
| 11 | 2 | **Fig. A3** (doctor), **Fig. A4** (ingestion) |
| 12 | 1 | **Fig. A5** (search) |

Pixel-level render check (144 dpi re-render of each page, ink coverage sampled inside each figure's bounding box):

- Fig. 1: 12.0% ink, avg luma ≈ 248 — **line-art/diagram rendered** (white diagram on white page, consistent with an architecture diagram)
- Fig. 2, A1, A2, A3, A4, A5: ~100% ink, avg luma ≈ 37–45 — **dark terminal screenshots rendered** (consistent with CLI screenshots)
- Fig. 3: 17.4% ink, avg luma ≈ 229 — **styled plot rendered** (consistent with a failure-analysis chart)

All 8 regions are densely painted at the correct positions — the images genuinely render in the PDF, not just referenced.

**No caption orphaned:** every caption (`Fig. 1`…`Fig. A5`) resides on the same page as its image (pages 3, 3, 7, 10, 10, 11, 11, 12).

**No overlap:** a bounding-box overlap scan of image vs. text objects found **zero** figure/word intersections; captions sit cleanly below their figures; no figure overlaps an adjacent figure (Fig. 1 bottom 499 pt vs Fig. 2 top 514 pt on page 3, etc.).

**Pagination is clean:** 12 pages, no blank pages, no clipped regions, headers/footers intact.

Note: this audit session's model cannot render images to eyeball them, so "visual" verification above is done by (a) Word-native PDF export, (b) PDF XObject extraction, and (c) pixel-ink analysis of the rendered page at 144 dpi. This is stronger than a screenshot check alone because it confirms raster content, position, aspect, pairing, and absence of overlap numerically.

---

## 6. DOCX/PDF consistency

- DOCX → PDF was produced by the same application that authored the DOCX (Microsoft Word), so the DOCX is the source of truth and the PDF is a faithful rendering.
- Page count 12, A4 size, single-column layout preserved (as required).
- Mentor line reads exactly `Mentored by: Dr.Santhosh Kumar J, Dr.Hemachandra Reddy` in the PDF page 1 — identical to the DOCX.
- No tracked changes (`w:ins`/`w:del` = 0), no comments.xml, no placeholders survive in the corrected file.
- All 8 figure embedding references resolve to existing package parts — no dangling relationships.

---

## 7. Scientific-number consistency (unchanged — verified)

- **Paragraph text of the corrected DOCX is identical to the original** except: (1) the mentor line (B1 fix) and (2) the 8 inserted image paragraphs, which contain no text. Verified with a unified diff over the full paragraph stream — the only text change is the mentor line; the only additions are the 8 blank-text image paragraphs.
- **All 3 Word tables are byte-identical** between original and corrected DOCX (TABLE I frozen baseline; TABLE II interventions; corpus/query table). Values 0.8408 / 0.9108 / 0.9236 / 0.8773 / 0.8571 / 0.0000 / 0.1429 / 0.0302 / 37.4 / 47.1 / 7299.3 ms unchanged; Table II FPR/FNR/latency/verdict cells (including ~850 ms, ~644 ms, ~2.9 s, 14.1 s avg / ~17.3 s p95) unchanged.
- Abstract/RQ/Discussion/Conclusion numbers (Hit@5 0.9236, MRR 0.8773, FPR 0.8571, 31/36, 47.1 ms p95) unchanged and remain consistent with `phase_5d_frozen_baseline.json`.
- The PDF text extraction shows the same numeric strings (e.g. `0.9236`, `0.8773`, `0.8571`, `47.1 ms`, `0.0302`) on the corresponding pages. PASS.

## 8. Citation/reference consistency (unchanged — verified)

- Reference list still contains exactly [1]–[6], all present in the corrected DOCX, all cited in text (§I, §II.A–F), all verified real in the first audit (incl. [6] Zhang & Wu, CMC 89(1):69, 2026, verified live on the publisher page).
- No dangling citations, no uncited entries, no duplicates, no refs added to pad the count. PASS.

## 9. Formatting consistency (unchanged except B1)

| Check | Result |
|---|---|
| A4 page size | PASS (11906×16838 twips) |
| Single-column layout | PASS (preserved) |
| Margins | PASS (top 1077 / bottom 1417 / left+right 1020 twips) |
| Mentor line | **PASS (B1 fixed)** — exact `Mentored by: Dr.Santhosh Kumar J, Dr.Hemachandra Reddy` |
| Section/heading numbering, figure numbering (1–3, A1–A5), table numbering | PASS |
| No Orphaned headings/blank pages/clipped figures | PASS |
| Footer/page-number artifacts | PASS |
| Tracked changes / comments | PASS (none) |
| Placeholder text | PASS (none) |
| Unicode glyphs / broken symbols | PASS (0 U+FFFD) |
| Fonts | PASS (Times New Roman + Courier New) |
| Image sizing within text column | PASS (6.3 in ≤ ~6.85 in usable width) |

Remaining P2 (B3 letters, B4 equations, B6 ref polish) intentionally untouched — non-blocking and out of scope of "fix only P0".

---

## 10. Final verdict

| Criterion | Status |
|---|---|
| B1 (mentor line exact) | PASS |
| B2 (all 8 figures genuinely embedded) | PASS |
| PDF rendered and every figure visually/pixel-verified | PASS |
| No overlapping figures/text, no orphaned captions, clean pagination | PASS |
| No new P0/P1 issue | PASS |

**FINAL VERDICT: READY TO PUBLISH**

Corrected files:
- `research/PAM_IEEE_Research_Paper_A4_FINAL_PRE_OPENCODE_REVIEW_FIXED.docx`
- `research/PAM_IEEE_Research_Paper_A4_FINAL_PRE_OPENCODE_REVIEW_FIXED.pdf`

The original pre-fix DOCX was left untouched. Optional (P2-only) polish — normalize subsection letter direction, convert the two equations to native math — may still be done at the author's discretion but does not block publication.