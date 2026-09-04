# PAM — Viva Questions and Answers

> Companion to [`../FACULTY_PRESENTATION_GUIDE.md`](../FACULTY_PRESENTATION_GUIDE.md).
> 25+ likely viva questions with concise, project-grounded answers.

---

1. **Why RAG instead of a normal chatbot?**
   A normal chatbot answers from pretrained knowledge and lacks your private context.
   RAG grounds every answer in chunks retrieved from your own corpus, with citations,
   and abstains when evidence is insufficient — so answers are about *your* documents.

2. **Why local inference?**
   Privacy and offline use. Personal material never leaves the machine; all embedding
   and QA calls go to a local Ollama server. No cloud calls.

3. **Why Ollama?**
   Ollama is the documented local runtime that serves both the QA model (`qwen3:8b`)
   and the embedding model (`nomic-embed-text`) on the user's own machine.

4. **Why qwen3:8b?**
   It is the documented default local QA model — small enough to run locally while
   providing usable generation for grounded answers.

5. **Why nomic-embed-text?**
   It is the documented default local embedding model used to embed chunks for
   semantic (dense) retrieval.

6. **What is semantic chunking?**
   Splitting a document into coherent, meaning-preserving units rather than fixed
   byte blocks. PAM uses sentence segmentation plus heading-hierarchy structure so
   each chunk is semantically self-contained for embedding and retrieval.

7. **What is hybrid retrieval?**
   Combining two signals: dense semantic similarity (cosine over local embeddings)
   and BM25 lexical matching, to find conceptually-related content as well as exact
   keyword matches.

8. **Why use BM25?**
   It handles exact lexical match and terminology that semantic vectors may miss; it
   is simple, fast, and offline. Hybrid fusion gets the strengths of both.

9. **What is RRF?**
   Reciprocal Rank Fusion — a way to combine ranked lists from dense and BM25
   retrieval into one fused ranking. PAM uses RRF with `k=60`.

10. **Why is abstention needed?**
   To avoid hallucination. When retrieved context is insufficient to support an
   answer, the system abstains instead of fabricating.

11. **What happens when evidence is insufficient?**
   The system declines/abstains rather than guessing. (The dedicated
   answerability/evidence verifier is implemented but disabled in V1.1.0 production.)

12. **How are citations generated?**
   Answers are built from retrieved chunks and carry `[SOURCE N]` markers that
   resolve to the specific retrieved sources, so every claim is traceable.

13. **How is hallucination reduced?**
   By grounding answers in retrieved chunks, requiring citations, and abstaining when
   context is insufficient. "About the tool" questions are answered deterministically
   via system facts (no LLM).

14. **How does deduplication work?**
   Each file is identified by its SHA-256 hash and tracked in a manifest/durable
   ledger, so the same source is not processed repeatedly.

15. **What happens during re-ingestion failure?**
   Prior data is preserved. Old chunks are removed only after a full successful
   re-embed/re-index — no unsafe partial replacement.

16. **What happens when a source is removed?**
   `pam remove <source>` de-indexes vectors, knowledge-graph nodes/edges, and
   ledger/manifest entries. It deliberately does **not** delete the vault note (to
   avoid data loss); full removal requires also deleting the note manually.

17. **What security protections exist?**
   Local-first (no cloud path), secret-bearing files blocked from ingestion, failure
   containment (structured errors, `failed/` folder), and corruption quarantine (a
   corrupted manifest is quarantined and rebuilt).

18. **Why are experiments disabled?**
   Reranker, HyDE, and answerability are implemented but did not meet production
   quality/latency guardrails, so they default to `enabled=false` in V1.1.0. They are
   retained for research, not deleted.

19. **Why freeze retrieval?**
   Experiments showed that changing retrieval alone did not reliably solve the
   answerability/content-sufficiency problem. The frozen setup (`min_cosine` 0.25,
   embed model, RRF) is the verified production baseline.

20. **What does FPR 0.857 actually mean?**
   In the frozen historical evaluation, 31 of 36 false positives were
   content-sufficiency misses: retrieved chunks were on-topic but lacked the exact
   required fact. It does **not** mean 85.7% "wrong answers," and it does not mean
   retrieval accuracy is 85.7%.

21. **What are the project's limitations?**
   Local single-user/single-worker pipeline; retrieval frozen; not every format is
   deep product support (PPTX/XLSX/OCR/images/audio/video not uniformly guaranteed);
   experimental features disabled; remote GitHub CI not independently verified.

22. **What did you build vs. use from libraries?**
   Built/integrated: ingestion lifecycle, routing, chunking, dedup, durable ledger,
   re-ingestion safety, removal, hybrid-retrieval orchestration, abstention-aware QA,
   citation contract, system-facts routing, CLI, security guards, testing/eval
   infrastructure. Used as infrastructure (documented): Ollama runtime, `qwen3:8b`,
   `nomic-embed-text`, optional Tesseract. The project did not implement the models
   or foundational inference libraries.

23. **How was the system tested?**
   Full suite: 1712 passed / 57 integration-deselected / 0 failed; Ruff pass; `mypy
   app/` 0 production/CI-visible errors; plus 32 evaluation-contract tests. Historical
   retrieval evaluation recorded (Hit@5 ≈ 0.924, MRR ≈ 0.877, FNR = 0.0, p95 ≈ 47 ms,
   FPR ≈ 0.857).

24. **Why are some tests deselected?**
   57 tests are `integration`-marked and excluded from the default run because they
   hit live/external services (e.g., a running Ollama); they run explicitly when
   required.

25. **What is future work?**
   Validate and enable experimental retrieval features (reranker, HyDE,
   answerability), broaden verified ingestion support, and improve parallelism /
   performance — see the development roadmap.

26. **Is the project cloud-based / does it send data anywhere?**
   No. PAM is local-first; embeddings and QA run against local Ollama. No cloud calls.

27. **How is retrieval different from keyword search?**
   It is hybrid: dense semantic similarity fused with BM25 via RRF, so it finds
   conceptually-related content, not just exact keywords, with filters.

28. **Is this just a chatbot?**
   No. It is a full ingestion + indexing + retrieval + grounded-QA pipeline over your
   own corpus, with citations, source management, dedup, and local-only execution.

29. **Did you write the models?**
   No. The project integrates local models (`qwen3:8b`, `nomic-embed-text`) via Ollama
   and builds all the surrounding system itself. This is documented honestly.
