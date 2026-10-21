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

## 2026-10-21 — Microphone Capture and Local Dialogue (Phase 1.4)

- Decision: add `sounddevice` as minimal dependency for audio input/output handling.
- Decision: manage WSL2 hardware isolation gracefully; when `libportaudio2` is absent in Linux userland, report the exact missing system dependency and provide a fallback mode with audio interventions and a reproducible local setup guide.
- Decision: retain faster-whisper `small` on CPU (`int8`) and Piper `es_ES-davefx-medium` on CPU as verified in Phase 1.3.
- Decision: eliminate unbounded `sd.wait()` calls by isolating microphone capture and audio playback inside dedicated child processes supervised by explicit timeouts. If native PortAudio/WSLg stalls on buffer starvation, the child process is terminated and `MicrophoneNotAvailableError` is raised, preventing process freeze.
- Decision: add explicit `--device` selection in `demo_mic.py` and categorize capture telemetry univoquely as `physical_capture`, `wav_input`, or `fallback`.
- Status: Phase 1.4 robustness hardening implemented; hardware validation with live microphone pending in host environment.


