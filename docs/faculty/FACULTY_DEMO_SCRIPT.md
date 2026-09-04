# PAM — Faculty Demo Script

> Companion to [`../FACULTY_PRESENTATION_GUIDE.md`](../FACULTY_PRESENTATION_GUIDE.md).
> A safe, deterministic demo flow. **Do not invent command output** — run the real
> commands and show the actual output on screen.

## Safety rules

- **Never** run destructive commands against the real corpus.
- Any command that would modify persistent data (ingest, remove, re-ingest) is
  labeled **[DEMO = modifies data]** below. Use a **disposable test source** in an
  isolated test vault for these.
- Prefer read-only commands first (`status`, `sources`, `search`, a system-facts
  `ask`) which cannot damage anything.
- If uncertain whether a command alters data, ask before running.

## Suggested flow

1. **Project structure / documentation.** Show the repo and point to
   `docs/PROJECT_STATUS.md`, `docs/architecture.md`, `docs/TESTING_AND_VERIFICATION.md`.
   (Read-only.)

2. **`pam status`** — show truthful report: processed/skipped/failed ingests, queue
   state, model/Ollama connection. *(Read-only.)*

3. **`pam sources`** — list sources with per-source chunk counts and truthful status.
   *(Read-only.)*

4. **Ingest a small supported document.** **[DEMO = modifies data]** Use a **small,
   disposable test file** (e.g., a short Markdown or TXT note) in an isolated test
   vault, *not* a real document. Example: a small Markdown file whose content you
   already know.

5. **Show duplicate handling.** **[DEMO = modifies data]** Re-run the same ingest on
   the same file and show SHA-256 dedup prevents reprocessing. (Optional; safe in a
   disposable vault.)

6. **Ask a question with a known answer.** `pam ask "..."` where the answer is
   present in your test note. *(Read-only — reading the index.)*

7. **Show source citations.** Highlight the `[SOURCE N]` markers in the answer and
   trace them to the retrieved source. *(Read-only.)*

8. **Demonstrate a system-facts question.** Ask `pam ask` "what is PAM / what model
   do you use / what version" and show the deterministic answer (no retrieval/LLM).
   *(Read-only.)*

9. **`pam remove <test source>`.** **[DEMO = modifies data]** Remove the *disposable
   test source only*. Show that vectors/graph/ledger are de-indexed and that the vault
   note is **not** deleted.

10. **Show status after removal.** `pam sources` / `pam status` to show the test
    source is gone from the index. *(Read-only.)*

11. **Explain limitations.** End with what the system does **not** guarantee: not all
    formats are deep product support, retrieval is frozen, experimental features are
    disabled.

## Which demo commands modify data

| Command | Modifies persistent data? | Guidance |
|---------|---------------------------|----------|
| `pam status` | No | Safe |
| `pam sources` | No | Safe |
| `pam search "..."` | No | Safe |
| `pam ask "..."` | No | Safe |
| `pam ingest ...` | Yes | Use disposable test source |
| `pam remove <source>` | Yes | Use disposable test source only |

> This demo plan is derived from the documented CLI (`pam status/doctor/config/watch/
> search/ask/ingest/sources/remove`). Actual command output must be shown from a real
> run; do not fabricate it.
