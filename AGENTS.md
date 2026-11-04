# AGENTS.md — Nico Bernaola Engine

This file documents the project state and conventions for AI agents working on this repo.

## Project pivot (important)

This repo started as a short-form video editing engine (silence cut, viral clips, social copy). It has been pivoted to a **meeting inference engine**: turn recorded meetings into structured onboarding/training documents, extract key moments, and keep a record of what was said and the steps to follow.

The pivot is on branch `dev`. `main` still reflects the old focus plus two remote commits (rename to "Nico Bernaola Engine" and a Rappi use-case section in README).

## Branches

- `main` — tracks `origin/main` (remote). Contains README use-case section.
- `dev` — working branch with the pivot changes (untracked local files now tracked-ish here; still untracked in git status).

## Modules and responsibilities

- `transcribe.py` — core. Whisper (faster-whisper) -> word-level JSON. Performance-optimized (see below).
- `meta.py` — meeting inference. Reads word JSON, calls Gemini, produces a Markdown doc with: Introduction (always), then either Steps (actionable procedure) OR Summary (informational talk), and a Context paragraph only when Steps were produced. Also emits a timestamped `_transcript_llm.txt` for LLM consumption. Function: `generar_informe(json_path, output_folder)`.
- `clipper.py` — key moments extraction. Chunks transcript, asks Gemini for key moments per chunk, editor pass ranks, writes `key_moments.txt`, optionally exports video clips. Pipeline entry: `extraer_momentos_clave(json_path, video_path, output_folder)`.
- `splitter.py` — splits audio/video (optional, speeds up transcription).
- `silence_cutter.py` — optional silence removal (legacy, kept but not central).
- `pipeline.py` — orchestrator with module selection via questionary.
- `version.py` — VERSION = "0.2.0".

## Key design decisions

1. The JSON transcript is the shared data format. Every downstream module consumes `*_transcript.json`.
2. `meta.py` is now the core value module (was social copy). It performs conditional rendering: steps XOR summary, and context only with steps.
3. `clipper.py` is optional and asks the user at runtime whether to export video clips.
4. Pipeline auto-resolves dependencies: infer/clips require transcribe.
5. Performance: transcription is the bottleneck. Optimizations in `transcribe.py`:
   - device auto-detect (CUDA float16 else CPU int8) via ctranslate2
   - configurable model size via `WHISPER_MODEL` env (default small)
   - configurable beam size via `WHISPER_BEAM` (default 2)
   - pre-extracts 16kHz mono WAV from video (faster decode)
   - VAD filter enabled (min_silence_duration_ms=500)
   - condition_on_previous_text=False
6. Gemini calls use urllib (no SDK). Free tier assumed.

## Conventions

- All modules expose `clean_path`, `resolve_files` where applicable.
- Functions accept `Path` objects.
- Output folders: `{stem}_output` for pipeline, `{stem}_meeting` for meta, `{stem}_clips`/`{stem}_moments` for clips.
- Print progress with flush=True.
- Spanish UI strings mixed with English code/comments (legacy). New code comments in English preferred.

## What changed in this pivot (for other agents)

- `transcribe.py`: added performance optimizations (audio extraction, VAD, device detection, env config). Added `.m4a` to FORMATS.
- `meta.py`: fully reworked from social-copy generator to meeting inference. New function `generar_informe`. Also emits `_transcript_llm.txt`. Removed `PLATAFORMAS`/`generar_meta`.
- `captions.py`: removed entirely (viral caption presets not relevant to meetings).
- `clipper.py`: reworked prompts from "viral moments" to "key moments" (decisions, action items). Added `extraer_momentos_clave` pipeline entry. Report renamed to `key_moments.txt`.
- `pipeline.py`: new STEPS focused on meetings (split, transcribe, infer, clips). Imports updated. Removed social platform selection. Added `infer` and `clips` steps.
- `README.md`: updated to reflect meeting inference focus and performance notes.
- `AGENTS.md`: this file.

## Known gaps / TODO for other agents

- `pipeline.py` still references `PRESETS_SILENCE` when silence cut is selected; silence cutter is legacy and may be removed.
- No tests. Consider adding smoke tests for transcript parsing.
- clipper optional clip export depends on ffmpeg and video presence.
- Gemini rate limiting: 5s sleep between chunks; editor pass single call.

## How to run

```bash
pip install -r requirements.txt
# .env with GEMINI_API_KEY
python pipeline.py
```

Env overrides:
- `WHISPER_MODEL` (tiny/base/small/medium/large-v3)
- `WHISPER_BEAM` (int)

## Git state

- Remote: origin = https://github.com/Nico-Bernaola/Nico-Digitals-Engine.git
- Branch dev created from main after git pull.
- Untracked files present: .python-version, main.py, pyproject.toml, uv.lock, videoplayback.json, videoplayback.mp4 (local artifacts).
