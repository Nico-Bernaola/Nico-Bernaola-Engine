import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from pathlib import Path
from dotenv import load_dotenv
import json
import urllib.request
import urllib.error
import os

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY)

FORMATS = {".json"}


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


def load_words(json_path: Path) -> list:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_transcript(words: list) -> str:
    lines = []
    for i, w in enumerate(words):
        if i % 120 == 0:
            lines.append(f"\n[{w['start']:.1f}s]")
        lines.append(w["word"])
    return " ".join(lines)


def build_llm_transcript(words: list) -> str:
    NL = chr(10)
    lines = []
    lines.append("# Transcript (LLM-ready)")
    lines.append("")
    if words:
        lines.append(f"Words: {len(words)} | Duration: {words[-1]['end']:.1f}s")
    lines.append("")
    block = []
    block_start = words[0]["start"] if words else 0
    for w in words:
        if w["start"] - block_start >= 30 and block:
            lines.append(f"[{block_start:.1f}s] " + " ".join(block))
            block = []
            block_start = w["start"]
        block.append(w["word"])
    if block:
        lines.append(f"[{block_start:.1f}s] " + " ".join(block))
    return NL.join(lines)


def normalize_output(text: str) -> str:
    """Spanish output: no accents, Ñ/ñ -> Ni/ni, ASCII only."""
    if not text:
        return text
    # Ñ/ñ -> Ni/ni first
    text = text.replace("Ñ", "Ni").replace("ñ", "ni")
    # strip accents
    import unicodedata
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # keep only printable ASCII
    text = "".join(c for c in text if ord(c) < 128)
    return text

def _call_gemini(prompt: str, temperature: float = 0.3, timeout: int = 120) -> str:
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": temperature}}).encode("utf-8")
    req = urllib.request.Request(GEMINI_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _parse_json(text: str) -> dict:
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def generar_informe(json_path: Path, output_folder: Path, language: str = "en") -> Path:
    words = load_words(json_path)
    transcript = build_transcript(words)

    if language == "es":
        lang_label = "Spanish"
        lang_extra = "Use only ASCII characters: no accents (a,e,i,o,u) and replace any n-tilde with \"Ni\" (or \"ni\")."
    else:
        lang_label = "English"
        lang_extra = "Use standard English."
    prompt = f"""You are an expert meeting analyst and technical writer.

I am giving you the full transcript of a recorded meeting (with timestamps). Produce a structured onboarding/training document a new employee can follow.

TRANSCRIPT:
{transcript}

LANGUAGE INSTRUCTION: Write ALL text fields in {lang_label}. {lang_extra}

Return ONLY a valid JSON object, no markdown, no explanations:
{{
  "intro": "A paragraph introducing what the meeting was about and its main goal.",
  "steps": ["step 1", "step 2", "..."] or null,
  "summary": "A paragraph summarizing the discussion" or null,
  "context": "A paragraph giving context of everything that needs to be done" or null
}}

Rules:
- "intro" is ALWAYS present (non-empty paragraph).
- If the meeting discussed a concrete procedure/process to execute, set "steps" to an ordered array of clear, actionable steps and set "summary" to null. Also set "context" to a paragraph summarizing overall context and action items.
- If the meeting was informational (no concrete procedure to execute), set "steps" to null, "summary" to a paragraph summarizing the talk, and "context" to null.
- Never set both "steps" and "summary" to non-null. Never set "context" when "summary" is set.
- Keep steps concise but complete. Use the same language as the transcript.
"""

    print(f"\nAnalyzing meeting: {json_path.name}...", flush=True)
    raw = _call_gemini(prompt, temperature=0.3, timeout=180)
    data = _parse_json(raw)

    intro = (data.get("intro") or "").strip()
    if language == "es":
        intro = normalize_output(intro)
    steps = data.get("steps")
    if language == "es" and steps:
        steps = [normalize_output(x) for x in steps]
    summary = (data.get("summary") or "").strip() if data.get("summary") else ""
    if language == "es" and summary:
        summary = normalize_output(summary)
    context = (data.get("context") or "").strip() if data.get("context") else ""
    if language == "es" and context:
        context = normalize_output(context)

    if steps:
        summary = ""
    else:
        context = ""

    output_folder.mkdir(parents=True, exist_ok=True)
    dest = output_folder / f"{json_path.stem}_meeting.md"

    lines = []
    lines.append(f"# Meeting Summary - {json_path.stem}")
    lines.append("")
    lines.append(f"- Source transcript: `{json_path.name}`")
    lines.append(f"- Words: {len(words)}")
    lines.append(f"- Duration: {words[-1]['end']:.1f}s" if words else "")
    lines.append("")
    lines.append("## Introduction")
    lines.append("")
    lines.append(intro)
    lines.append("")

    if steps:
        lines.append("## Steps")
        lines.append("")
        for i, step in enumerate(steps, start=1):
            lines.append(f"{i}. {step}")
        lines.append("")
        if context:
            lines.append("## Context")
            lines.append("")
            lines.append(context)
            lines.append("")
    else:
        lines.append("## Summary")
        lines.append("")
        lines.append(summary)
        lines.append("")

    dest.write_text("\n".join(lines), encoding="utf-8")
    print(f"   {dest.name}", flush=True)

    llm_dest = output_folder / f"{json_path.stem}_transcript_llm.txt"
    llm_dest.write_text(build_llm_transcript(words), encoding="utf-8")
    print(f"   {llm_dest.name}", flush=True)

    return dest


if __name__ == "__main__":
    while True:
        print("\n==============================", flush=True)
        print(" Meeting Inference - Meta", flush=True)
        print("==============================", flush=True)
        raw_input = input("\nDrag a transcript JSON here, or type 'exit': ").strip()
        if raw_input.lower() == "exit":
            print("\nClosing...")
            break
        path = clean_path(raw_input)
        if not path.exists():
            print(f"\nNot found: {path}", flush=True)
            continue
        files = resolve_files(path)
        if not files:
            print("\nNo compatible JSON files found.", flush=True)
            continue
        if path.is_dir():
            print(f"\nFolder detected - {len(files)} file(s) to process.", flush=True)
        for i, json_path in enumerate(files, start=1):
            if len(files) > 1:
                print(f"\n[{i}/{len(files)}]", flush=True)
            print(f"\nLoading: {json_path.name}", flush=True)
            output_folder = json_path.parent / f"{json_path.stem}_meeting"
            generar_informe(json_path, output_folder)
            print(f"Folder: {output_folder}", flush=True)
        print(f"\nDone. {len(files)} file(s) processed.", flush=True)
        again = input("\nProcess another file? (Enter to continue / 'exit' to quit): ").strip().lower()
        if again == "exit":
            print("\nClosing...")
            break
