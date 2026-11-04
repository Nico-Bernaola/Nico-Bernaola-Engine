import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
from version import VERSION
from pathlib import Path
import questionary

# Suite imports — each script exposes its functions
from splitter       import split
from transcribe     import transcribir, cargar_modelo, FORMATS
from silence_cutter import procesar as cut, PRESETS as PRESETS_SILENCE
from captions       import generar_captions, PRESETS as PRESETS_CAPTIONS
from meta           import generar_informe
from clipper        import extraer_momentos_clave

# =========================
# CONFIG
# =========================

STEPS = [
    {"key": "split",      "label": "Split          — separate audio and video (optional)"},
    {"key": "transcribe", "label": "Transcribe     — generate word-level JSON with Whisper"},
    {"key": "infer",      "label": "Infer         — meeting summary (intro + steps/summary + context)"},
    {"key": "clips",      "label": "Key Moments    — extract important moments (optional)"},
    {"key": "captions",   "label": "Captions       — generate .SRT (optional)"},
]

# =========================
# HELPERS
# =========================

def clean_path(raw: str) -> Path:
    raw = raw.strip().replace('"', "").replace("'", "")
    if raw.startswith("/") and len(raw) > 2 and raw[2] == "/":
        raw = f"{raw[1].upper()}:{raw[2:]}"
    return Path(raw)


def section(title: str):
    print(f"\n{'─'*50}", flush=True)
    print(f"  {title}",  flush=True)
    print(f"{'─'*50}",   flush=True)


# =========================
# MAIN LOOP
# =========================

whisper_model = None  # lazy loading — reused across batch files

while True:

    print("\n══════════════════════════════════════", flush=True)
    print(f"  Nico Bernaola Engine | v{VERSION}",   flush=True)
    print(  "  Meeting Inference Pipeline",           flush=True)
    print(  "══════════════════════════════════════", flush=True)
    print(  "  ℹ️  For help, read the README.md\n",  flush=True)

    # ── Module selection ───────────────────────────────────────────────────
    active = questionary.checkbox(
        "Which modules do you want to run?",
        choices=[s["label"] for s in STEPS]
    ).ask()

    if not active:
        print("\n⚠️  No modules selected.", flush=True)
        continue

    active_keys = [s["key"] for s in STEPS if s["label"] in active]

    # ── Auto-resolve dependencies ──────────────────────────────────────────
    for dep in ["infer", "clips", "captions"]:
        if dep in active_keys and "transcribe" not in active_keys:
            print(f"\n⚠️  '{dep}' requires Transcribe. Enabling it automatically.", flush=True)
            active_keys.insert(active_keys.index(dep), "transcribe")

    # ── Configure optional modules ─────────────────────────────────────────
    preset_silence  = None
    clip_sequence   = False
    preset_captions = None

    if "cut" in active_keys:
        print("\n  Silence Cut presets:")
        for k, v in PRESETS_SILENCE.items():
            print(f"  [{k}] {v['name']} — {v['description']}")
        op = input("  Choose preset (1/2/3): ").strip()
        preset_silence = PRESETS_SILENCE.get(op, PRESETS_SILENCE["2"])

        cut_mode = questionary.select(
            "How do you want the output?",
            choices=["Single file", "Clip sequence"]
        ).ask()
        clip_sequence = cut_mode == "Clip sequence"

    if "captions" in active_keys:
        print("\n  Captions presets:")
        for k, v in PRESETS_CAPTIONS.items():
            print(f"  [{k}] {v['name']} — {v['description']}")
        op = input("  Choose preset (1/2/3/4): ").strip()
        preset_captions = PRESETS_CAPTIONS.get(op, PRESETS_CAPTIONS["2"])
        if preset_captions["words"] is None:
            try:
                n = int(input("  How many words per caption? ").strip())
                preset_captions = {**preset_captions, "words": max(1, n)}
            except ValueError:
                preset_captions = PRESETS_CAPTIONS["2"]

    # ── Input: video or folder ─────────────────────────────────────────────
    video_input = input("\nDrag a video or folder here, or type 'exit': ").strip()

    if video_input.lower() == "exit":
        print("\nClosing...")
        break

    input_path = clean_path(video_input)

    if not input_path.exists():
        print(f"\nNot found: {input_path}", flush=True)
        continue

    if input_path.is_dir():
        files = sorted([f for f in input_path.iterdir() if f.suffix.lower() in FORMATS])
        if not files:
            print("\nNo compatible video files found in folder.", flush=True)
            continue
        print(f"\nFolder detected — {len(files)} file(s) to process.", flush=True)
    elif input_path.suffix.lower() in FORMATS:
        files = [input_path]
    else:
        print("\nUnsupported format.", flush=True)
        continue

    # ── Process each file ──────────────────────────────────────────────────
    for file_idx, video_path in enumerate(files, start=1):

        if len(files) > 1:
            print(f"\n{'═'*38}", flush=True)
            print(f"  [{file_idx}/{len(files)}] {video_path.name}", flush=True)
            print(f"{'═'*38}", flush=True)

        output_folder = video_path.parent / f"{video_path.stem}_output"
        output_folder.mkdir(exist_ok=True)
        print(f"\nOutput: {output_folder}", flush=True)

        json_path = None

        for key in active_keys:

            if key == "split":
                section("SPLIT — Separating audio and video")
                split(video_path, output_folder)

            elif key == "transcribe":
                section("TRANSCRIBE — Generating JSON with Whisper")
                if whisper_model is None:
                    whisper_model = cargar_modelo()
                dest      = output_folder / f"{video_path.stem}_transcript.json"
                json_path = transcribir(video_path, whisper_model, output_path=dest)
                if not json_path:
                    print("\nTranscription failed. Skipping file.", flush=True)
                    break

            elif key == "infer":
                section("INFER — Meeting summary")
                if json_path:
                    generar_informe(json_path, output_folder)
                else:
                    print("\nNo JSON available for inference.", flush=True)

            elif key == "clips":
                section("KEY MOMENTS — Extracting important moments")
                if json_path:
                    extraer_momentos_clave(json_path, video_path, output_folder)
                else:
                    print("\nNo JSON available for key moments.", flush=True)

            elif key == "cut":
                section(f"SILENCE CUT — Preset: {preset_silence['name']}")
                cut(video_path, preset_silence, clip_sequence, output_folder=output_folder)

            elif key == "captions":
                section(f"CAPTIONS — Preset: {preset_captions['name']}")
                if json_path:
                    dest = output_folder / f"{video_path.stem}_{preset_captions['name']}.srt"
                    generar_captions(json_path, preset_captions, output_path=dest)
                else:
                    print("\nNo JSON available for captions.", flush=True)

        print(f"\n  Done: {video_path.name}", flush=True)
        print(f"  {output_folder}",          flush=True)

    print(f"\n{'═'*38}",                                        flush=True)
    print(f"  Pipeline complete. {len(files)} file(s).",     flush=True)
    print(f"{'═'*38}",                                         flush=True)

    again = input("\nProcess another batch? (Enter to continue / 'exit' to quit): ").strip().lower()
    if again == "exit":
        print("\nClosing...")
        break
