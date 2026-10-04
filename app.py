"""AF3 Structure Studio - Streamlit front-end (purple & silver theme).

Modes:
  1. AlphaFold3 backend (your GPU server, see backend/server.py)
  2. ESMFold public API (demo, no GPU)
  3. Upload an existing AF3 model (.cif / .pdb)
"""
import io
import json
import re
import string
import time

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from Bio.PDB import MMCIFParser, PDBIO, PDBParser

st.set_page_config(page_title="AF3 Structure Studio", page_icon="🧬", layout="wide")

# --------------------------------------------------------------------------- #
# Purple & silver styling
# --------------------------------------------------------------------------- #
st.markdown(
    """
<style>
.stApp{background:linear-gradient(180deg,#F4F5F8 0%,#D9DCE3 100%);}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#2E1065 0%,#5B21B6 100%);}
section[data-testid="stSidebar"] label p, section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] .stMarkdown p{color:#E5E7EB !important;}
.hero{background:linear-gradient(120deg,#3B0764 0%,#7C3AED 55%,#C0C0C0 100%);
      color:#F8FAFC;padding:1.3rem 1.8rem;border-radius:16px;margin-bottom:1rem;
      border:1px solid #C0C0C0;box-shadow:0 4px 14px rgba(76,29,149,.35);}
.hero h1{margin:0;font-size:1.9rem;color:#F8FAFC;} .hero p{margin:.2rem 0 0;color:#E5E7EB;}
.stButton>button,.stDownloadButton>button{background:linear-gradient(90deg,#6D28D9,#8B5CF6);
      color:#F3F4F6;border:1px solid #C0C0C0;border-radius:10px;font-weight:600;}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:#FFFFFF;color:#FFFFFF;}
[data-testid="stMetric"]{background:#ECEEF3;border:1px solid #C0C0C0;border-radius:12px;padding:.6rem 1rem;}
textarea{font-family:monospace !important;}
</style>
<div class="hero"><h1>🧬 AF3 Structure Studio</h1>
<p>Predict a protein structure from sequence, inspect residues, recolor, resize and export.</p></div>
""",
    unsafe_allow_html=True,
)

AMINO = set("ACDEFGHIKLMNPQRSTVWY")
CHAIN_IDS = string.ascii_uppercase
DEFAULT_COLORS = ["#7C3AED", "#C0C0C0", "#A78BFA", "#6B7280", "#4C1D95", "#E5E7EB"]
ESMFOLD_URL = "https://api.esmatlas.com/foldSequence/v1/pdb/"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_sequences(text: str):
    text = text.strip()
    if not text:
        return []
    if text.startswith(">"):
        raw = ["".join(b.strip().splitlines()[1:]) for b in text.split(">")[1:]]
    else:
        raw = [l for l in text.splitlines() if l.strip()]
    return [re.sub(r"\s+", "", s).upper() for s in raw]


def validate(seqs):
    for i, s in enumerate(seqs):
        bad = set(s) - AMINO
        if not s:
            return f"Sequence {i + 1} is empty."
        if bad:
            return f"Sequence {i + 1} has invalid residues: {', '.join(sorted(bad))}"
    if len(seqs) > len(CHAIN_IDS):
        return "Too many chains."
    return None


def load_structure(text: str, fmt: str):
    parser = MMCIFParser(QUIET=True) if fmt == "cif" else PDBParser(QUIET=True)
    s = parser.get_structure("model_0", io.StringIO(text))
    # ESMFold stores pLDDT as 0-1; AF3 as 0-100. Normalise to 0-100.
    atoms = list(s.get_atoms())
    if atoms and max(a.get_bfactor() for a in atoms) <= 1.0:
        for a in atoms:
            a.set_bfactor(a.get_bfactor() * 100)
    return s


def to_pdb(structure) -> str:
    w = PDBIO()
    w.set_structure(structure)
    buf = io.StringIO()
    w.save(buf)
    return buf.getvalue()


def residue_table(structure) -> pd.DataFrame:
    rows = []
    for chain in structure[0]:
        for res in chain:
            if res.id[0] != " ":
                continue
            p = sum(a.get_bfactor() for a in res) / len(res)
            band = ("Very high (>90)" if p > 90 else "Confident (70-90)" if p > 70
                    else "Low (50-70)" if p > 50 else "Very low (<50)")
            rows.append({"Chain": chain.id, "Residue #": res.id[1],
                         "Residue": res.get_resname(), "pLDDT": round(p, 2), "Confidence": band})
    return pd.DataFrame(rows)


def run_esmfold(seq: str) -> str:
    r = requests.post(ESMFOLD_URL, data=seq, timeout=300, verify=True)
    r.raise_for_status()
    return r.text


def run_af3(url, key, name, seqs, seed, status):
    h = {"X-API-Key": key}
    r = requests.post(f"{url}/predict", headers=h, timeout=60,
                      json={"name": name, "sequences": seqs, "seed": seed})
    r.raise_for_status()
    job = r.json()["job_id"]
    while True:
        s = requests.get(f"{url}/jobs/{job}", headers=h, timeout=60).json()
        status.update(label=f"AlphaFold3 job {job}: {s['status']} ...")
        if s["status"] == "done":
            break
        if s["status"] == "failed":
            raise RuntimeError(s.get("error", "AF3 job failed"))
        time.sleep(10)
    cif = requests.get(f"{url}/jobs/{job}/model", headers=h, timeout=120).text
    summ = requests.get(f"{url}/jobs/{job}/summary", headers=h, timeout=60)
    return cif, (summ.json() if summ.ok else None)


# --------------------------------------------------------------------------- #
# 3D viewer (3Dmol.js): colours, chain colours, resize, zoom, hi-res PNG
# --------------------------------------------------------------------------- #
VIEWER = """
<script src="https://3Dmol.org/build/3Dmol-min.js"></script>
<div id="wrap" style="width:__W__%;margin:auto;height:__H__px;position:relative;overflow:hidden;
     border:2px solid #C0C0C0;border-radius:14px;background:__BG__;">
  <div id="v" style="width:100%;height:100%;position:relative;"></div>
</div>
<div style="text-align:center;margin-top:8px;font-family:sans-serif;">
  <button id="shot" style="background:linear-gradient(90deg,#6D28D9,#8B5CF6);color:#F3F4F6;
   border:1px solid #C0C0C0;border-radius:10px;padding:8px 18px;font-weight:600;cursor:pointer;">
   📸 Save PNG (__S__x resolution)</button>
</div>
<script>
const PDB=__PDB__, STYLE="__STYLE__", MODE="__MODE__", CC=__CC__, SINGLE="__SINGLE__", Z=__Z__, SPIN=__SPIN__, S=__S__;
const v=document.getElementById('v'), wrap=document.getElementById('wrap');
const viewer=$3Dmol.createViewer(v,{backgroundColor:"__BG__",antialias:true});
viewer.addModel(PDB,"pdb");
const plddt=a=>a.b>90?'#0053D6':a.b>70?'#65CBF3':a.b>50?'#FFDB13':'#FF7D45';
function put(sel,c){const s={};s[STYLE]=c;viewer.setStyle(sel,s);}
if(MODE==='chain'){for(const ch in CC){put({chain:ch},{color:CC[ch]});}}
else if(MODE==='plddt'){put({},{colorfunc:plddt});}
else if(MODE==='spectrum'){put({},{color:'spectrum'});}
else if(MODE==='ss'){put({},{colorscheme:'ssPyMol'});}
else{put({},{color:SINGLE});}
viewer.zoomTo(); viewer.zoom(Z); viewer.render();
if(SPIN){viewer.spin(true);}
document.getElementById('shot').onclick=function(){
  const w=wrap.clientWidth,h=wrap.clientHeight;
  viewer.spin(false);
  v.style.width=(w*S)+'px'; v.style.height=(h*S)+'px';
  viewer.resize(); viewer.render();
  const uri=viewer.pngURI();
  v.style.width='100%'; v.style.height='100%';
  viewer.resize(); viewer.render();
  if(SPIN){viewer.spin(true);}
  const a=document.createElement('a'); a.href=uri; a.download='structure_hires.png';
  document.body.appendChild(a); a.click(); a.remove();
};
</script>
"""


def render_viewer(pdb_text, o):
    html = (VIEWER.replace("__PDB__", json.dumps(pdb_text))
            .replace("__STYLE__", o["style"]).replace("__MODE__", o["mode"])
            .replace("__CC__", json.dumps(o["chain_colors"])).replace("__SINGLE__", o["single"])
            .replace("__BG__", o["bg"]).replace("__W__", str(o["width"]))
            .replace("__H__", str(o["height"])).replace("__Z__", str(o["zoom"]))
            .replace("__SPIN__", "true" if o["spin"] else "false").replace("__S__", str(o["scale"])))
    components.html(html, height=o["height"] + 70, scrolling=False)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Prediction")
    engine = st.radio("Engine", ["AlphaFold3 (GPU backend)", "ESMFold (demo, no GPU)",
                                 "Upload AF3 model (.cif/.pdb)"])
    url = key = ""
    if engine.startswith("AlphaFold3"):
        url = st.secrets.get("BACKEND_URL", "") or st.text_input("Backend URL", "https://")
        key = st.secrets.get("API_KEY", "") or st.text_input("API key", type="password")
    seed = st.number_input("Model seed", 1, 10_000, 1)
    job_name = st.text_input("Job name", "my_protein")

    st.header("🎨 Appearance")
    style = st.selectbox("Representation", ["cartoon", "stick", "sphere", "line"])
    mode_label = st.selectbox("Colour by", ["pLDDT confidence", "Chain", "Secondary structure",
                                            "Rainbow (N→C)", "Single colour"])
    mode = {"pLDDT confidence": "plddt", "Chain": "chain", "Secondary structure": "ss",
            "Rainbow (N→C)": "spectrum", "Single colour": "single"}[mode_label]
    single = st.color_picker("Single colour", "#7C3AED") if mode == "single" else "#7C3AED"
    bg = st.color_picker("Background", "#F1F2F6")

    st.header("📐 Size")
    width = st.slider("Viewer width (%)", 30, 100, 100)
    height = st.slider("Viewer height (px)", 300, 1000, 600, 50)
    zoom = st.slider("Zoom", 0.5, 3.0, 1.0, 0.1)
    spin = st.checkbox("Spin", False)
    scale = st.select_slider("Screenshot resolution (×)", [1, 2, 4, 6, 8], value=4)

# --------------------------------------------------------------------------- #
# Input & run
# --------------------------------------------------------------------------- #
ss = st.session_state
if engine.startswith("Upload"):
    up = st.file_uploader("Upload your AF3 model_0 (.cif or .pdb)", type=["cif", "pdb"])
    if up and st.button("Load model"):
        txt = up.getvalue().decode()
        ss["res"] = {"struct": load_structure(txt, up.name.rsplit(".", 1)[-1].lower()),
                     "cif": txt if up.name.endswith("cif") else None, "summary": None}
else:
    text = st.text_area("Protein sequence(s) - raw, one per line, or FASTA (multiple = multiple chains)",
                        height=160, placeholder=">chain_A\nMKTAYIAKQRQISFVKSHFSRQ...")
    if st.button("🚀 Predict structure"):
        seqs = parse_sequences(text)
        err = validate(seqs) if seqs else "Please enter a sequence."
        if not err and engine.startswith("ESMFold") and (len(seqs) > 1 or len(seqs[0]) > 400):
            err = "ESMFold demo supports one chain up to 400 residues."
        if err:
            st.error(err)
        else:
            try:
                with st.status("Predicting ...", expanded=True) as status:
                    if engine.startswith("ESMFold"):
                        pdb_txt = run_esmfold(seqs[0])
                        ss["res"] = {"struct": load_structure(pdb_txt, "pdb"), "cif": None, "summary": None}
                    else:
                        cif, summ = run_af3(url.rstrip("/"), key, job_name, seqs, int(seed), status)
                        ss["res"] = {"struct": load_structure(cif, "cif"), "cif": cif, "summary": summ}
                    status.update(label="Done ✅", state="complete")
            except Exception as e:  # noqa: BLE001
                st.error(f"Prediction failed: {e}")

# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
res = ss.get("res")
if res:
    struct = res["struct"]
    pdb_text = to_pdb(struct)
    table = residue_table(struct)
    chains = sorted(table["Chain"].unique())

    chain_colors = {}
    if mode == "chain":
        with st.sidebar:
            st.subheader("Chain colours")
            for i, c in enumerate(chains):
                chain_colors[c] = st.color_picker(f"Chain {c}", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])

    t1, t2, t3 = st.tabs(["🔮 Structure", "🧬 Residues", "⬇️ Downloads"])
    with t1:
        render_viewer(pdb_text, dict(style=style, mode=mode, chain_colors=chain_colors, single=single,
                                     bg=bg, width=width, height=height, zoom=zoom, spin=spin, scale=scale))
        if mode == "plddt":
            st.caption("🟦 >90 very high · 🟦(light) 70-90 confident · 🟨 50-70 low · 🟧 <50 very low")
    with t2:
        c1, c2, c3 = st.columns(3)
        c1.metric("Residues", len(table))
        c2.metric("Chains", len(chains))
        c3.metric("Mean pLDDT", f"{table['pLDDT'].mean():.1f}")
        if res.get("summary"):
            sm = res["summary"]
            st.write({k: sm[k] for k in ("ptm", "iptm", "ranking_score") if k in sm})
        st.line_chart(table.reset_index(drop=True)["pLDDT"])
        st.dataframe(table, use_container_width=True, height=380)
    with t3:
        st.download_button("⬇️ model_0.pdb", pdb_text, "model_0.pdb", "chemical/x-pdb")
        if res.get("cif"):
            st.download_button("⬇️ model_0.cif (original AF3 mmCIF)", res["cif"], "model_0.cif")
        st.download_button("⬇️ residues.csv", table.to_csv(index=False), "residues.csv", "text/csv")
        st.info("High-resolution PNG: use the 📸 button under the viewer (Structure tab).")
else:
    st.info("Enter a sequence (or upload a model) to get started.")
