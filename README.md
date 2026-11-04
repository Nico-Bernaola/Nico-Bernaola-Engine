# Nico Bernaola Engine `v0.2.0`

A local, open-source automation engine that turns recorded meetings into structured onboarding/training documents. Built for teams who want to capture what was said, extract the steps, and onboard new employees without re-watching 40-minute videos.

---

## What it does

Turn a raw meeting video into a publish-ready knowledge package — transcription, meeting summary (intro + steps or summary + context), and key moments — with a single command.

```
python pipeline.py
```

---

## Modules

| Script | Input | Output |
|---|---|---|
| `transcribe.py` | video / audio | word-level JSON with timestamps |
| `splitter.py` | video | footage.mp4 + audio.mp3 |
| `silence_cutter.py` | video | cleaned video or individual clips |
| `meta.py` | JSON | meeting summary document (.md) |
| `clipper.py` | JSON | key moments report + optional clips |
| `pipeline.py` | video / folder | everything above, organized |

All modules work standalone or together through the pipeline. The JSON transcript is the shared data format between them.

---

## Pipeline output

```
video_output/
├── split/
│   ├── video_footage.mp4
│   ├── video_audio.mp3
│   └── README.txt
├── video_transcript.json
├── video_meeting.md
├── key_moments.txt
```

---

## Stack

- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — local transcription, no API needed
- **[auto-editor](https://github.com/WyattBlue/auto-editor)** — silence detection and removal (optional)
- **[Gemini 2.5 Flash](https://ai.google.dev/)** — meeting inference and key-moment extraction (free tier)
- **[questionary](https://github.com/tmbo/questionary)** — interactive CLI
- **ffmpeg** — audio/video processing

---

## Requirements

- Python 3.10+
- ffmpeg installed and in PATH

```bash
pip install -r requirements.txt
```

---

## Setup

1. Clone the repo
2. Install dependencies
3. Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com).

---

## Usage

**Pipeline (recommended):**
```bash
python pipeline.py
```
Select which modules to run, choose presets, drag your video or folder.

**Individual modules:**
```bash
python transcribe.py
python meta.py
python clipper.py
```

All scripts support single files and batch processing (drag a folder).

---

## Performance notes

Transcription is the bottleneck. For long meetings the engine now:
- auto-detects CUDA and uses float16 when available, otherwise CPU int8
- extracts a 16kHz mono WAV before transcribing (faster decode)
- enables VAD filtering to skip silences
- lowers beam size (configurable via `WHISPER_BEAM`, default 2)
- disables conditioning on previous text

Model size is configurable via `WHISPER_MODEL` (tiny/base/small/medium/large-v3). Default `small`.

---

## Use Cases

### Operational Data Extraction (Rappi / Quick Pass)

While the engine was designed for short-form video, its core logic (video -> word-level JSON) acts as a universal business intelligence adapter. It solves a common problem: "I have a recorded meeting, but I need the exact technical data to execute a task immediately."

**The scenario:** A supervisor received a 40-minute training session on bulk-uploading employee shifts in Quick Pass (Rappi's HR platform). Despite attending the meeting, he couldn't resolve critical load errors. I had zero prior experience with the HR system.

**How the engine solved it:**

1.  `video_conference.mp4` -> `transcribe.py` -> `word-level JSON with timestamps`.
2.  Parsed the JSON to extract exact verbal instructions: date formatting (apostrophe trick), mandatory "Lote" field, and time syntax.
3.  Applied the extracted rules directly to the Google Sheets template.
4.  The bulk upload succeeded without trial-and-error guesswork.

---

## License

Apache 2.0 — free to use, modify, and distribute.
