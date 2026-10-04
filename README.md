# 🧬 AF3 Structure Studio

A purple-and-silver Streamlit tool for protein structure prediction with **AlphaFold3**.
Paste a sequence, predict, inspect per-residue confidence, recolor, resize, and export.

## Features
- Sequence input (raw or FASTA; multiple sequences = multiple chains)
- Predicts structure and returns **model_0** (top-ranked AF3 model)
- **Download model_0 as PDB** (pLDDT kept in the B-factor column) and original mmCIF
- Per-residue table (chain, residue number, residue name, pLDDT, confidence band) + CSV export
- Colour by pLDDT, chain (individual colour pickers), secondary structure, rainbow, or single colour
- Cartoon / stick / sphere / line styles, background colour
- Resizable viewer (width, height), zoom, optional spin
- **High-resolution PNG screenshot** (up to 8x the on-screen size)

## Architecture
```
Browser -> Streamlit app (streamlit.app, from GitHub) --HTTPS--> FastAPI backend (GPU server) -> AlphaFold3
```
AlphaFold3 cannot run on Streamlit Community Cloud (no GPU, small RAM), so the app calls a backend you host.
Two extra modes work without a GPU: **ESMFold demo** (public API, one chain, up to 400 aa) and
**Upload AF3 model** (load a `model_0.cif` from AlphaFold Server or your own run).

## Project layout
```
app.py                 Streamlit interface
backend/server.py      FastAPI wrapper for AF3
backend/requirements.txt
requirements.txt       Front-end dependencies (used by streamlit.app)
.streamlit/config.toml Purple/silver theme
ROADMAP.md
```

## Quick start (local)
```bash
git clone https://github.com/<you>/af3-structure-studio.git
cd af3-structure-studio
pip install -r requirements.txt
streamlit run app.py
```
Choose **ESMFold (demo)** or **Upload** in the sidebar to try it with no GPU.

## Backend (GPU machine)
1. Request AF3 weights from Google DeepMind and install AlphaFold3 + databases (see the official repository).
2. Install and run the wrapper:
```bash
cd backend && pip install -r requirements.txt
export AF3_API_KEY="choose-a-long-random-string"
export AF3_DIR=/opt/alphafold3 AF3_MODEL_DIR=/data/af3/models AF3_DB_DIR=/data/af3/public_databases
uvicorn server:app --host 0.0.0.0 --port 8000
```
If AF3 runs in Docker, set `AF3_PYTHON` to a wrapper script or edit `cmd` in `run_job()`.
3. Expose it over HTTPS (e.g. `cloudflared tunnel --url http://localhost:8000`).

## Deploy on streamlit.app
1. Push this repo to GitHub.
2. At https://share.streamlit.io choose **New app**, select the repo, branch `main`, main file `app.py`.
3. In **Settings -> Secrets** add:
```toml
BACKEND_URL = "https://your-backend.example.com"
API_KEY = "the-same-string-as-AF3_API_KEY"
```

## Notes
- AF3 names the top model `*_model.cif`; this tool labels it **model_0**.
- The B-factor column holds pLDDT (0-100). ESMFold's 0-1 values are rescaled automatically.
- The AF3 weights/terms of use restrict commercial use and public service hosting. Check them before exposing the app publicly; consider access control.
- Screenshot size is limited by your browser's maximum canvas size; use 4x if 8x fails.
- AlphaFold3: Abramson et al., *Nature* 2024. Viewer: 3Dmol.js. Parsing: Biopython.
