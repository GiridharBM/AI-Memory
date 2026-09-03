# Phase 6F-D — Make Ollama Context Length 8192 Permanent

**Date:** 2026-08-31
**HEAD:** 9f282b41b6c558b0dbea857c95e24beb3ff63f9a (unchanged, frozen — no code touched this phase)
**Scope:** runtime/host configuration only. No repository code, prompts, dataset, corpus, or pipeline changes.

---

## 1. Previous automatic context behavior

- Ollama 0.33.2 was running with no `OLLAMA_CONTEXT_LENGTH` anywhere (no env var, no Modelfile `num_ctx`). Under that condition Ollama **auto-sizes the context** based on model (+ available memory) and loaded `qwen3:8b` at **`num_ctx=40960`**.
- Consequences measured in phases 6E/6B/6C:
  - Model graph ~**11 GB**, offloaded only **48% CPU / 52% GPU**.
  - Every decode token paid a large KV-attention cost → ~5x slower generation than at 8192.
  - Free RAM during QA sessions fell to **1.4–3.0 GB** (tail as low as ~1 GB), the pressure blamed for 6D instability/hangs under parallel load.
  - Slow tail pre-dated the wall-clock guardrail: 6D max 466.2s / p95 244.2s.

## 2. Why 40960 was rejected

- 6F-B controlled experiment (5 queries; only `num_ctx` varied): mean wall 70.3s vs 16.8s at 8192 (**4.2x slower**), per-token decode penalty ~5x despite an identical total output-token budget (2424 vs 2423 tokens).
- Memory pressure: free RAM 1.4–3.0 GB during runs vs 6.3–8.5 GB at 8192.
- Requires unbounded wall-clock time to serve the tail; with 6F-A's 120s guardrail in place it would turn slow-but-answerable queries into hard failures.
- **Rejected.**

## 3. Why 4096 was rejected

- 6F-B: at 4096 the long-answer comparison query **q027 lost all 5 citations** (2→0) while 8192/40960 kept them; output also grew (1088 tokens), consistent with squeeze at the context boundary.
- No latency advantage over 8192 (18.2s vs 16.8s mean — noise).
- Prompt + long output (~3.3–3.5k tokens) leaves too little headroom; risk of truncation/citation dropout on the largest answers.
- **Rejected.**

## 4. Why 8192 was accepted

- 6F-B: **4.2x** faster than automatic on the 5-query sample; identical citation sets; RAM relief.
- 6F-C validation (35-query real-corpus sample, same composition as 6D):
  - latency mean **91.0s → 33.4s**, p50 **63.0 → 31.3s**, p95 **244.2 → 64.8s**, max **466.2 → 81.6s** (2.0–5.7x).
  - **35/35 answered, 0 failures, 0 timeouts** (max 81.6s, well under the 120s wall-clock guardrail).
  - citation rate **85.7% → 88.6%**; invalid citations **0**; empty answers **0**; no truncation (answer lengths 547 mean / 1742 max, context usage <40%).
  - memory footprint **~11 GB → ~5.2 GB**, full **100% GPU** offload.
  - Max 6F-C latency is inside one wall-clock quantum; the guardrail becomes emergency-only.
- **Accepted** (6F-C decision, per STEP 7).

## 5. Permanent configuration method

Chosen: **persistent user-level Windows environment variable** — the least-invasive mechanism matching Ollama's existing startup path. No project code or scripts.

```powershell
# Set persistently (writes to HKCU:\Environment)
[Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', '8192', 'User')
```

Verified in the registry:

```
[Environment]::GetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH','User')  # -> 8192
(Get-ItemProperty 'HKCU:\Environment').OLLAMA_CONTEXT_LENGTH            # -> 8192
```

How it is delivered to the server (Ollama's normal startup mechanism on this machine):

1. Ollama is **not a Windows service**; it runs as a tray app. Startup-folder entry `Ollama.lnk` launches `ollama app.exe` at login, which spawns `ollama serve`.
2. Per-login shells/Explorer build their environment from the registry (machine + user), so after the next logon the tray app → `ollama serve` inherit `OLLAMA_CONTEXT_LENGTH=8192` automatically.
3. Immediate application without re-login: relaunch the server with the variable present in its process environment (equivalent to the logon state):
   ```powershell
   $psi = New-Object System.Diagnostics.ProcessStartInfo
   $psi.FileName = 'C:\Users\girid\AppData\Local\Programs\Ollama\ollama.exe'
   $psi.Arguments = 'serve'
   $psi.UseShellExecute = $false
   $psi.Environment['OLLAMA_CONTEXT_LENGTH'] = '8192'
   [System.Diagnostics.Process]::Start($psi)
   ```
   (The interactive shell's own environment predates the registry change, so the immediate relaunch injects the same value the logon path will supply.)

Nothing was added to the repository; the value is **not** hard-coded in PAM application logic (it remains a server-side runtime default, as intended).

## 6. Verification via `ollama ps`

After relaunching the server and forcing a load of `qwen3:8b`:

```
NAME        ID              SIZE      PROCESSOR    CONTEXT    UNTIL
qwen3:8b    500a1f067a9f    5.2 GB    100% GPU     8192       4 minutes from now
```

- **CONTEXT = 8192** (confirmed on the permanent-config run; also matches 6F-C's measurement-time verification).
- SIZE 5.2 GB, 100% GPU — the small-context footprint from validation.
- (An earlier relaunch through the tray app did not yet carry the variable because the current interactive session's environment predates the registry edit; that is expected and resolves at next logon via the Startup link.)

## 7. One QA smoke test

Full CLI ask through `entry.cli` (real Ollama server, real retrieval+citation pipeline):

```
query:        "When was Utthunga founded?"
exit_code:    0
wall:         30.8s
verified:     SOURCES VERIFIED label present
citations:    [SOURCE …] references present in output
timeout:      none
failure:      none
```

Latency 30.8s ≈ factoid-class expectation at 8192 (6F-C factoid mean 19.5s / max 44.7s).

## 8. Rollback procedure

1. Delete the persistent variable:
   ```powershell
   [Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', $null, 'User')
   ```
2. Reload/relaunch Ollama (restart the tray app or `ollama serve`). Without the variable, Ollama resumes context auto-sizing (back to `num_ctx=40960` for qwen3:8b on this host).
3. Verify rollback: `ollama ps` on a freshly loaded `qwen3:8b` should show CONTEXT 40960 (SIZE ~11 GB, 48%/52% CPU/GPU).
4. No repository change needs to be undone (there is none).

## 9. Safety audit (STEP 5)

- `git rev-parse HEAD` → `9f282b41b6c558b0dbea857c95e24beb3ff63f9a` (unchanged).
- `git status --short` → 104 working-tree entries, identical to end of 6F-C; this phase adds **no** tracked modifications.
- `git diff --stat` → 33 files, all pre-existing cumulative working-copy state from earlier phases; production diffs limited to 6F-A's intended `qa_workflow.py` / `test_qa_workflow.py` / `test_cli.py`.
- Entries cached for staging: **0**. Nothing staged, committed, or pushed.
- No production code, prompts, dataset, or corpus files were changed by 6F-D. The only configuration outside the repo is the user-level environment variable.

## 10. STOP

Phase 6F-D complete. 8192 is now permanent at the host level. Awaiting explicit approval to begin Phase 6G.