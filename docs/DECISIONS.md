# Architecture Decision Log

## 2026-10-20 — Initial workspace

- Decision: use pnpm for the TypeScript workspace.
- Decision: use Next.js and TypeScript for the web application.
- Decision: isolate voice experimentation in Python using uv.
- Decision: begin with local voice validation.
- Decision: defer the CRM database, telephony and SaaS infrastructure
  until the relevant phase requires them.
- Status: initial setup; runtime verification still required.

## 2026-10-21 — Voice Stack Benchmark (Phase 1.2)

- Decision: select Piper (`es_ES-davefx-medium`, CC0) as primary local TTS running on CPU (RTF 0.0209, 0 MB VRAM).
- Decision: select faster-whisper `small` over `base` for Spanish STT; `base` was rejected due to acoustic hallucinations on dates, times and commercial terms.
- Decision: run STT on CPU (`int8`) as default baseline; CTranslate2 GPU execution in WSL2 requires explicit `libcublas.so.12` runtime libraries.
- Status: STT and TTS benchmark completed and verified; awaiting user audio review before proceeding to Phase 1.3.

## 2026-10-21 — Single-Turn Conversation Cycle (Phase 1.3)

- Decision: adopt Piper `es_ES-davefx-medium` (CC0) as the definitive primary TTS voice for the prototype, based on human listening validation by the user (preference over `sharvard`, not an assertion of universal objective superiority).
- Decision: retain the verified Piper CPU configuration and faster-whisper `small` on CPU (`int8`).
- Decision: implement commercial conversational responses via deterministic rules and templates without an LLM for Phase 1.3.
- Status: Phase 1.3 execution approved; single-turn turnaround pipeline implementation underway.

