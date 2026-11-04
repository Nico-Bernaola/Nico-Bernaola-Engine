import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import json
import uuid
import threading
import queue
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_ROOT = BASE_DIR / "ui_outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_ROOT.mkdir(exist_ok=True)

app = FastAPI(title="Nico Bernaola Engine")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "ui" / "static")), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_ROOT)), name="outputs")

# Lazy whisper model
_whisper_model = None
_model_lock = threading.Lock()

def get_whisper_model():
    global _whisper_model
    with _model_lock:
        if _whisper_model is None:
            from transcribe import cargar_modelo
            _whisper_model = cargar_modelo()
    return _whisper_model

JOBS = {}
JOB_LOCK = threading.Lock()


class QueueWriter:
    def __init__(self, q):
        self.q = q
    def write(self, s):
        if s:
            for line in s.splitlines(keepends=True):
                self.q.put(line)
        return len(s) if s else 0
    def flush(self):
        pass


def run_job(job_id, config):
    q = JOBS[job_id]["queue"]
    old_stdout, old_stderr = sys.stdout, sys.stderr
    writer = QueueWriter(q)
    sys.stdout = writer
    sys.stderr = writer
    try:
        from pathlib import Path as P
        import questionary  # noqa: not used but ensure import

        files = [P(p) for p in config["files"]]
        modules = config.get("modules", [])
        silence_preset_key = config.get("silence_preset", "2")
        clip_sequence = bool(config.get("clip_sequence", False))
        captions_preset_key = config.get("captions_preset", "2")
        captions_words = config.get("captions_words")
        export_clips = bool(config.get("export_clips", False))

        from silence_cutter import PRESETS as PRESETS_SILENCE, procesar as cut
        from captions import PRESETS as PRESETS_CAPTIONS, generar_captions
        from splitter import split
        from transcribe import transcribir, FORMATS
        from meta import generar_informe
        from clipper import extraer_momentos_clave

        whisper_model = None

        for video_path in files:
            print(f"\n=== Processing: {video_path.name} ===", flush=True)
            output_folder = video_path.parent / f"{video_path.stem}_output"
            output_folder.mkdir(exist_ok=True)
            json_path = None

            if "split" in modules:
                print("\n-- SPLIT --", flush=True)
                split(video_path, output_folder)

            if "transcribe" in modules:
                print("\n-- TRANSCRIBE --", flush=True)
                if whisper_model is None:
                    whisper_model = get_whisper_model()
                dest = output_folder / f"{video_path.stem}_transcript.json"
                json_path = transcribir(video_path, whisper_model, output_path=dest)
                if not json_path:
                    print("Transcription failed. Skipping file.", flush=True)
                    continue

            if "infer" in modules:
                print("\n-- INFER --", flush=True)
                if json_path:
                    generar_informe(json_path, output_folder)
                else:
                    print("No JSON available.", flush=True)

            if "clips" in modules:
                print("\n-- KEY MOMENTS --", flush=True)
                if json_path:
                    extraer_momentos_clave(json_path, video_path, output_folder, export_clips_choice=export_clips)
                else:
                    print("No JSON available.", flush=True)

            if "cut" in modules:
                print("\n-- SILENCE CUT --", flush=True)
                preset = PRESETS_SILENCE.get(silence_preset_key, PRESETS_SILENCE["2"])
                cut(video_path, preset, clip_sequence, output_folder=output_folder)

            if "captions" in modules:
                print("\n-- CAPTIONS --", flush=True)
                if json_path:
                    preset = PRESETS_CAPTIONS.get(captions_preset_key, PRESETS_CAPTIONS["2"])
                    if captions_words:
                        preset = {**preset, "words": max(1, int(captions_words))}
                    if preset["words"] is None:
                        preset = {**preset, "words": 3}
                    dest = output_folder / f"{video_path.stem}_{preset['name']}.srt"
                    generar_captions(json_path, preset, output_path=dest)
                else:
                    print("No JSON available.", flush=True)

            print(f"\nDone: {video_path.name}", flush=True)
            print(f"Output: {output_folder}", flush=True)

        JOBS[job_id]["output_folder"] = str(output_folder)
        JOBS[job_id]["status"] = "done"
        print("\n=== PIPELINE COMPLETE ===", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(e)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        q.put(None)  # sentinel


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(str(BASE_DIR / "ui" / "index.html"))


@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    saved = []
    for f in files:
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex}_{f.filename}"
        with open(dest, "wb") as out:
            out.write(await f.read())
        saved.append(str(dest))
    return {"paths": saved, "names": [f.filename for f in files]}


@app.post("/run")
async def run(payload: dict):
    job_id = uuid.uuid4().hex
    q = queue.Queue()
    JOBS[job_id] = {"queue": q, "status": "running", "output_folder": None}
    threading.Thread(target=run_job, args=(job_id, payload), daemon=True).start()
    return {"job_id": job_id}


@app.get("/logs/{job_id}")
def logs(job_id: str):
    q = JOBS[job_id]["queue"]
    def gen():
        while True:
            item = q.get()
            if item is None:
                yield "data: [DONE]\n\n"
                break
            for line in item.splitlines():
                yield f"data: {line}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/status/{job_id}")
def status(job_id: str):
    j = JOBS.get(job_id, {})
    return {"status": j.get("status"), "output_folder": j.get("output_folder"), "error": j.get("error")}


@app.get("/outputs_list/{job_id}")
def outputs_list(job_id: str):
    j = JOBS.get(job_id, {})
    folder = j.get("output_folder")
    if not folder:
        return {"files": []}
    p = Path(folder)
    files = []
    for root, _, fs in os.walk(p):
        for fn in fs:
            rel = Path(root).relative_to(OUTPUT_ROOT) if Path(root).is_relative_to(OUTPUT_ROOT) else None
            # store under outputs mount: need files inside OUTPUT_ROOT
            pass
    # Instead, copy output folder into OUTPUT_ROOT for serving
    import shutil
    dest = OUTPUT_ROOT / job_id
    if not dest.exists() and Path(folder).exists():
        shutil.copytree(folder, dest)
    result = []
    for root, _, fs in os.walk(dest):
        for fn in fs:
            full = Path(root) / fn
            rel = full.relative_to(OUTPUT_ROOT).as_posix()
            result.append({"name": fn, "url": f"/outputs/{rel}"})
    return {"files": result}


@app.post("/shutdown")
def shutdown():
    """Stops the server. The user decides when it runs and when it stops."""
    def _exit():
        import time
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=False)
