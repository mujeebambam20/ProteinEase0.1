"""FastAPI wrapper around a local AlphaFold3 installation (run on your GPU machine).

Run:  uvicorn server:app --host 0.0.0.0 --port 8000
Env:  AF3_API_KEY, AF3_DIR, AF3_MODEL_DIR, AF3_DB_DIR, JOBS_DIR, AF3_PYTHON
Put it behind HTTPS (Cloudflare Tunnel, nginx, ...) so streamlit.app can reach it.
"""
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, field_validator

API_KEY = os.getenv("AF3_API_KEY", "")
AF3_DIR = os.getenv("AF3_DIR", "/opt/alphafold3")
MODEL_DIR = os.getenv("AF3_MODEL_DIR", "/data/af3/models")
DB_DIR = os.getenv("AF3_DB_DIR", "/data/af3/public_databases")
JOBS = Path(os.getenv("JOBS_DIR", "./jobs"))
PY = os.getenv("AF3_PYTHON", sys.executable)
JOBS.mkdir(parents=True, exist_ok=True)

GPU_LOCK = threading.Lock()  # one AF3 job at a time per GPU
app = FastAPI(title="AF3 backend")


class Req(BaseModel):
    name: str = "job"
    sequences: list[str]
    seed: int = 1

    @field_validator("sequences")
    @classmethod
    def check(cls, v):
        if not v or len(v) > 26:
            raise ValueError("1-26 sequences required")
        for s in v:
            if not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", s):
                raise ValueError("invalid amino-acid sequence")
        return v


def auth(key: str):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad API key")


def set_status(d: Path, status: str, error: str = ""):
    (d / "status.json").write_text(json.dumps({"status": status, "error": error}))


def run_job(jid: str, req: Req):
    d = JOBS / jid
    set_status(d, "queued")
    with GPU_LOCK:
        set_status(d, "running")
        # AF3 input format (dialect alphafold3, version 1)
        af3_input = {
            "name": f"job_{jid[:8]}",
            "modelSeeds": [req.seed],
            "sequences": [{"protein": {"id": string.ascii_uppercase[i], "sequence": s}}
                          for i, s in enumerate(req.sequences)],
            "dialect": "alphafold3",
            "version": 1,
        }
        inp = d / "input.json"
        inp.write_text(json.dumps(af3_input))
        cmd = [PY, f"{AF3_DIR}/run_alphafold.py", f"--json_path={inp}",
               f"--model_dir={MODEL_DIR}", f"--db_dir={DB_DIR}", f"--output_dir={d / 'out'}"]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            set_status(d, "failed", p.stderr[-1500:])
        else:
            set_status(d, "done")


import string  # noqa: E402  (used above)


@app.post("/predict")
def predict(req: Req, x_api_key: str = Header("")):
    auth(x_api_key)
    jid = uuid.uuid4().hex
    (JOBS / jid).mkdir()
    threading.Thread(target=run_job, args=(jid, req), daemon=True).start()
    return {"job_id": jid}


def job_dir(jid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", jid) or not (JOBS / jid).exists():
        raise HTTPException(404, "unknown job")
    return JOBS / jid


@app.get("/jobs/{jid}")
def status(jid: str, x_api_key: str = Header("")):
    auth(x_api_key)
    return json.loads((job_dir(jid) / "status.json").read_text())


@app.get("/jobs/{jid}/model")
def model(jid: str, x_api_key: str = Header("")):
    """Top-ranked model (this is what the UI calls model_0)."""
    auth(x_api_key)
    hits = list((job_dir(jid) / "out").glob("*/*_model.cif"))
    if not hits:
        raise HTTPException(404, "model not ready")
    return PlainTextResponse(hits[0].read_text())


@app.get("/jobs/{jid}/summary")
def summary(jid: str, x_api_key: str = Header("")):
    auth(x_api_key)
    hits = list((job_dir(jid) / "out").glob("*/*_summary_confidences.json"))
    if not hits:
        raise HTTPException(404, "not ready")
    return JSONResponse(json.loads(hits[0].read_text()))
