import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
from pathlib import Path
from tqdm import tqdm
import json
import os
import subprocess
import tempfile

# =========================
# CONFIG
# =========================
MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
BEAM_SIZE = int(os.getenv("WHISPER_BEAM", "2"))
FORMATS = {".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".m4a"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}


def clean_path(raw: str) -> Path:
    raw = raw.strip().replace('"', "").replace("'", "")
    if raw.startswith("/") and len(raw) > 2 and raw[2] == "/":
        raw = f"{raw[1].upper()}:{raw[2:]}"
    return Path(raw)


def resolve_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted([f for f in path.iterdir() if f.suffix.lower() in FORMATS])
    elif path.suffix.lower() in FORMATS:
        return [path]
    return []


def _detect_device() -> tuple[str, str]:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _extract_audio(video_path: Path) -> Path | None:
    try:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        tmp_path = Path(tmp)
        cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(tmp_path)]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
            return tmp_path
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def transcribir(video_path: Path, model, output_path: Path = None) -> Path:
    print(f"\n{video_path.name}", flush=True)

    audio_path = video_path
    tmp_wav = None
    if video_path.suffix.lower() in VIDEO_EXTS:
        tmp_wav = _extract_audio(video_path)
        if tmp_wav is not None:
            audio_path = tmp_wav
            print("   Audio extracted to 16kHz mono WAV (faster decode).", flush=True)

    try:
        segments, info = model.transcribe(
            str(audio_path),
            beam_size=BEAM_SIZE,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        print(f"   Language: {info.language} ({info.language_probability:.0%}) | Duration: {info.duration:.2f}s", flush=True)

        pbar = tqdm(total=info.duration, unit="s", desc="   Processing", bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')

        words = []
        last_pos = 0
        for segment in segments:
            pbar.update(segment.end - last_pos)
            last_pos = segment.end
            if segment.words:
                for word in segment.words:
                    words.append({"word": word.word.strip(), "start": round(word.start, 3), "end": round(word.end, 3)})
        pbar.close()
    finally:
        if tmp_wav is not None:
            try:
                tmp_wav.unlink(missing_ok=True)
            except Exception:
                pass

    dest = output_path if output_path else video_path.with_suffix(".json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

    print(f"   {len(words)} words -> {dest.name}", flush=True)
    return dest


def cargar_modelo():
    from faster_whisper import WhisperModel
    device, compute_type = _detect_device()
    print(f"\nLoading Whisper model ({MODEL_SIZE}) on {device} ({compute_type})...", flush=True)
    model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute_type)
    print("   Model ready.\n", flush=True)
    return model


if __name__ == "__main__":
    model = None
    while True:
        print("\n==============================", flush=True)
        print(f" Transcriber - Whisper {MODEL_SIZE}", flush=True)
        print("==============================", flush=True)
        raw_input = input("\nDrag a video or folder here, or type 'exit': ").strip()
        if raw_input.lower() == "exit":
            print("\nClosing...")
            break
        path = clean_path(raw_input)
        if not path.exists():
            print(f"\nNot found: {path}", flush=True)
            continue
        files = resolve_files(path)
        if not files:
            print("\nNo compatible media files found.", flush=True)
            continue
        if path.is_dir():
            print(f"\nFolder detected - {len(files)} file(s) to process.", flush=True)
        if model is None:
            model = cargar_modelo()
        for i, file in enumerate(files, start=1):
            if len(files) > 1:
                print(f"\n[{i}/{len(files)}]", flush=True)
            transcribir(file, model)
        print(f"\nSession complete. {len(files)} file(s) processed.", flush=True)
