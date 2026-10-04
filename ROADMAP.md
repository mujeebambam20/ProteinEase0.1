# Roadmap

## Phase 0 - Access & licensing (do first)
- [ ] Request AF3 weights from Google DeepMind and read the Terms of Use (non-commercial; restrictions on offering it as a service).
- [ ] Decide who may use your public app (private repo / password / institution only).

## Phase 1 - GPU backend
- [ ] Machine: NVIDIA GPU with >= 40 GB (A100/H100), ~1 TB SSD for genetic databases.
- [ ] Install AF3 following the official repo (Docker recommended); download databases.
- [ ] Test from the CLI: `python run_alphafold.py --json_path=fold_input.json ...` and confirm `*_model.cif` appears.

## Phase 2 - Wrap with API
- [ ] `cd backend && pip install -r requirements.txt`
- [ ] Set env vars (AF3_API_KEY, AF3_DIR, AF3_MODEL_DIR, AF3_DB_DIR), run `uvicorn server:app --port 8000`.
- [ ] `curl -X POST localhost:8000/predict -H "X-API-Key: ..." -H "Content-Type: application/json" -d '{"sequences":["MKTAYIAKQRQISFVKSHFSRQ"]}'`
- [ ] Expose via HTTPS (Cloudflare Tunnel / nginx + Let's Encrypt).

## Phase 3 - Front-end
- [ ] Run locally: `pip install -r requirements.txt && streamlit run app.py`.
- [ ] Test all 3 modes (upload a known `model_0.cif` first - no GPU needed).
- [ ] Verify PDB download, residue table, colour/size controls, 4x PNG.

## Phase 4 - Deploy
- [ ] Push to GitHub, deploy on share.streamlit.io (main file `app.py`).
- [ ] Add `BACKEND_URL` and `API_KEY` in app Settings > Secrets.

## Phase 5 - Hardening / extras
- [ ] Per-user auth, job queue persistence, request size limits.
- [ ] Ligands/DNA/RNA inputs (extend `server.py` JSON builder), PAE heatmap, multi-seed ranking dropdown.
- [ ] Optional: replace in-browser screenshot with server-side rendering.
