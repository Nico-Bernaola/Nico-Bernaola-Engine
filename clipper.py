import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
from pathlib import Path
from dotenv import load_dotenv
import json
import urllib.request
import urllib.error
import subprocess
import os
import time

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

MIN_CLIP_DURATION = 20
CLIP_MARGIN = 1.5
MAX_CLIP_DURATION = 120
MAX_CLIPS = 8
CHUNK_DURATION = 900
CLIPS_PER_CHUNK = 3


def clean_path(raw: str) -> Path:
    raw = raw.strip().replace('"', "").replace("'", "")
    if raw.startswith("/") and len(raw) > 2 and raw[2] == "/":
        raw = f"{raw[1].upper()}:{raw[2:]}"
    return Path(raw)


def load_words(json_path: Path) -> list:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_gemini() -> bool:
    body = json.dumps({
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 5}
    }).encode("utf-8")
    req = urllib.request.Request(GEMINI_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception:
        return False


def split_into_chunks(words: list, chunk_duration: float) -> list[list]:
    chunks = []
    current_chunk = []
    chunk_start = words[0]["start"]
    for word in words:
        current_chunk.append(word)
        if word["end"] - chunk_start >= chunk_duration:
            chunks.append(current_chunk)
            current_chunk = []
            chunk_start = word["end"]
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def build_transcript(words: list) -> str:
    lines = []
    for i, w in enumerate(words):
        if i % 30 == 0:
            lines.append(f"[{w['start']:.1f}s]")
        lines.append(w["word"])
    return " ".join(lines)


def _call_gemini(prompt: str, temperature: float = 0.3, timeout: int = 60) -> str:
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }).encode("utf-8")
    req = urllib.request.Request(GEMINI_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def ask_gemini_chunk(words: list, chunk_index: int, total_chunks: int, language: str = "en") -> list[dict]:
    lang_label = "Spanish (ASCII only, no accents, n-tilde as ni)" if language == "es" else "English"
    transcript = build_transcript(words)
    start_time = words[0]["start"]
    end_time = words[-1]["end"]
    prompt = f"""You are an expert meeting analyst. This is chunk {chunk_index} of {total_chunks} from a recorded meeting transcript.
Chunk covers: {start_time:.0f}s to {end_time:.0f}s

Find the {CLIPS_PER_CHUNK} most important moments in THIS chunk only.
Prioritize: key decisions, action items, critical instructions, important topics, Q&A that clarify execution.

CRITERIA:
- Each moment must be a complete, self-contained idea, no cut-off sentences
- Minimum duration: {MIN_CLIP_DURATION} seconds
- Maximum duration: {MAX_CLIP_DURATION} seconds
- Use the exact timestamps from the transcript

Write title and reason in {lang_label}.

TRANSCRIPT:
{transcript}

Reply ONLY with a valid JSON array, no explanations or markdown:
[
  {{
    "start": 0.0,
    "end": 45.0,
    "title": "short moment title",
    "reason": "why this moment matters"
  }}
]
"""
    text = _call_gemini(prompt, temperature=0.4, timeout=60)
    return json.loads(text)


def editor_pass(candidates: list, language: str = "en") -> list[dict]:
    lang_label = "Spanish (ASCII only, no accents, n-tilde as ni)" if language == "es" else "English"
    candidates_text = json.dumps(candidates, indent=2)
    prompt = f"""You are a meeting analyst and editor. I have {len(candidates)} key-moment candidates from a meeting.
Rank them by importance for onboarding/training and return ONLY the top {MAX_CLIPS}.

RANKING CRITERIA:
1. Actionability, does it contain a decision or instruction someone must follow?
2. Clarity, is the moment self-contained and easy to understand?
3. Relevance, is it central to the meeting's goal?
4. Duration, prefer moments between {MIN_CLIP_DURATION}s and {MAX_CLIP_DURATION}s

Write title and reason in {lang_label}.

CANDIDATES:
{candidates_text}

Reply ONLY with a valid JSON array of the top {MAX_CLIPS} moments, ranked most to least important.
Keep the exact same fields (start, end, title, reason). No explanations or markdown.
"""
    text = _call_gemini(prompt, temperature=0.2, timeout=60)
    return json.loads(text)


def preview_clips(clips: list):
    print(f"\n{'─'*52}", flush=True)
    print(f"  {len(clips)} key moment(s) selected:", flush=True)
    print(f"{'─'*52}", flush=True)
    for i, clip in enumerate(clips, start=1):
        duration = round(clip["end"] - clip["start"], 1)
        print(f"\n  Moment {i:02d} - {duration}s [{clip['start']:.1f}s -> {clip['end']:.1f}s]", flush=True)
        print(f"  {clip['title']}", flush=True)
        print(f"  {clip['reason']}", flush=True)
    print(f"\n{'─'*52}", flush=True)


def export_report(clips: list, json_path: Path, output_folder: Path):
    lines = []
    lines.append("NICO BERNAOLA ENGINE - KEY MOMENTS REPORT")
    lines.append("=" * 52)
    lines.append(f"Source: {json_path.name}")
    lines.append(f"Total moments selected: {len(clips)}")
    lines.append("")
    lines.append("SELECTED MOMENTS")
    lines.append("-" * 52)
    for i, clip in enumerate(clips, start=1):
        duration = round(clip["end"] - clip["start"], 1)
        lines.append("")
        lines.append(f"Moment {i:02d} - {clip['title']}")
        lines.append(f"Timestamp: {clip['start']:.1f}s -> {clip['end']:.1f}s ({duration}s)")
        lines.append(f"Why: {clip['reason']}")
    report_path = output_folder / "key_moments.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"   key_moments.txt", flush=True)
    return report_path


def export_clips(video_path: Path, clips: list, output_folder: Path):
    output_folder.mkdir(parents=True, exist_ok=True)
    for i, clip in enumerate(clips, start=1):
        start = max(0, clip["start"] - CLIP_MARGIN)
        end = clip["end"] + CLIP_MARGIN
        safe = "".join(c for c in clip["title"] if c.isalnum() or c in " -_")[:40].strip().replace(" ", "_")
        out_file = output_folder / f"moment_{i:02d}_{safe}.mp4"
        cmd = ["ffmpeg", "-ss", str(start), "-to", str(end), "-i", str(video_path),
               "-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "make_zero", "-y", str(out_file)]
        print(f"\nClip {i:02d} [{start:.1f}s -> {end:.1f}s] - {clip['title']}", flush=True)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"   {out_file.name}", flush=True)


def normalize_output(text: str) -> str:
    if not text:
        return text
    text = text.replace("Ñ", "Ni").replace("ñ", "ni")
    import unicodedata
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = "".join(c for c in text if ord(c) < 128)
    return text

def extraer_momentos_clave(json_path: Path, video_path: Path, output_folder: Path, export_clips_choice=None, language: str = "en"):
    print(f"\nLoading: {json_path.name}", flush=True)
    words = load_words(json_path)
    total_duration = words[-1]["end"]
    print(f"   {len(words)} words | {total_duration:.1f}s ({total_duration/60:.1f} min)", flush=True)

    print("\nChecking Gemini availability...", flush=True)
    if not check_gemini():
        print("   Gemini unavailable. Skipping.", flush=True)
        return
    print("   Gemini online.", flush=True)

    chunks = split_into_chunks(words, CHUNK_DURATION)
    print(f"   {len(chunks)} chunk(s) of ~{CHUNK_DURATION//60} min each", flush=True)

    all_clips = []
    errors = 0
    for i, chunk in enumerate(chunks, start=1):
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]
        print(f"\nAnalyzing chunk {i}/{len(chunks)} [{chunk_start:.0f}s -> {chunk_end:.0f}s]...", flush=True)
        try:
            clips = ask_gemini_chunk(chunk, i, len(chunks), language=language)
            all_clips.extend(clips)
            print(f"   {len(clips)} moment(s) found", flush=True)
        except Exception as e:
            print(f"   Chunk {i} failed: {e}", flush=True)
            errors += 1
        if i < len(chunks):
            time.sleep(5)

    if not all_clips:
        print("\nNo moments found.", flush=True)
        return

    print(f"\nChunk analysis complete. {len(all_clips)} candidate(s).", flush=True)
    if errors:
        print(f"{errors} chunk(s) failed.", flush=True)

    print(f"\nRunning editor pass - ranking {len(all_clips)} candidates...", flush=True)
    try:
        top_clips = editor_pass(all_clips, language=language)
        print(f"   Top {len(top_clips)} moments selected.", flush=True)
    except Exception as e:
        print(f"   Editor pass failed ({e}). Falling back to chronological order.", flush=True)
        top_clips = all_clips[:MAX_CLIPS]

    if language == "es":
        for c in top_clips:
            c["title"] = normalize_output(c.get("title", ""))
            c["reason"] = normalize_output(c.get("reason", ""))
    preview_clips(top_clips)

    export_report(top_clips, json_path, output_folder)

    if export_clips_choice is None:
        export_choice = input("\nExport video clips for these moments? (y/n): ").strip().lower()
        do_export = export_choice == "y"
    else:
        do_export = bool(export_clips_choice)
    if do_export:
        if video_path and Path(video_path).exists():
            clips_folder = output_folder / f"{json_path.stem}_moments"
            export_clips(Path(video_path), top_clips, clips_folder)
            print(f"\nClips exported to: {clips_folder}", flush=True)
        else:
            print("\nVideo not found. Skipping clip export.", flush=True)

    print(f"\nDone. {len(top_clips)} key moments extracted.", flush=True)


if __name__ == "__main__":
    while True:
        print("\n==============================", flush=True)
        print(" Clipper - Key Moments (Meetings)", flush=True)
        print("==============================", flush=True)

        json_input = input("\nDrag the transcript JSON here, or type 'exit': ").strip()
        if json_input.lower() == "exit":
            print("\nClosing...")
            break

        json_path = clean_path(json_input)
        if not json_path.exists():
            print(f"\nNot found: {json_path}", flush=True)
            continue
        if json_path.suffix.lower() != ".json":
            print("\nFile must be a .json generated by transcribe.py.", flush=True)
            continue

        video_path = None
        for ext in [".mp4", ".mov", ".avi", ".mkv"]:
            candidate = json_path.with_suffix(ext)
            if candidate.exists():
                video_path = candidate
                break

        extraer_momentos_clave(json_path, video_path, json_path.parent, export_clips_choice=None)
