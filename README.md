# Nico Bernaola Engine `v0.2.0`

A local, open-source automation engine for short-form video content production. Built for creators and agencies who want to move fast without paying for subscriptions.

---

## What it does

Turn a raw video into a publish-ready content package — transcription, silence removal, captions, and platform copy — with a single command.

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
| `captions.py` | JSON | .SRT file |
| `meta.py` | JSON | platform copy (.txt) |
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
├── video_Hormozi.srt
└── meta/
    ├── instagram.txt
    ├── tiktok.txt
    ├── youtube_shorts.txt
    └── linkedin.txt
```

---

## Stack

- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — local transcription, no API needed
- **[auto-editor](https://github.com/WyattBlue/auto-editor)** — silence detection and removal
- **[Gemini 2.5 Flash](https://ai.google.dev/)** — copy generation (free tier)
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
python silence_cutter.py
python captions.py
python meta.py
python splitter.py
```

All scripts support single files and batch processing (drag a folder).

---

## Presets

**Silence Cut**
- `Podcast` — preserves natural pauses
- `Talking-Head` — standard cut for front-facing camera
- `Short-form` — aggressive cut for Reels / TikTok

**Captions**
- `MrBeast` — 1 word per caption
- `Hormozi` — 3 words per caption
- `Podcast` — 5 words per caption
- `Custom` — you choose

---

## License

Apache 2.0 — free to use, modify, and distribute.
