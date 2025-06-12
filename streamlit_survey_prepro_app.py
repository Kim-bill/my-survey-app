# streamlit_survey_prepro_app.py — v6 (adds codebook sheet)
"""
Survey Pre‑processing Toolkit  📊 (Streamlit, minimal)
----------------------------------------------------
* Raw → (Weights) → Missing → (Label) → (Tidy) → Excel + optional ZIP
* **Codebook**: second sheet named `codebook` lists `variable | code | label`.
  - Built from any `<var>(TEXT)` pairs that exist in the uploaded file.
  - For binary multi‑response columns we include a single row `code=1 label=Selected`.
* No auto/manual renaming; relies on existing `(TEXT)` columns for value labels.
"""
from __future__ import annotations
import io, zipfile, re
from pathlib import Path
import pandas as pd
import streamlit as st

# ---------- Helper ------------------

def detect_pairs(cols):
    return {c[:-6]: c for c in cols if str(c).endswith('(TEXT)') and str(c)[:-6] in cols}

def detect_multiresp(code_cols):
    groups = {}
    for c in code_cols:
        m = re.match(r'(.*?)_', str(c))
        if m:
            groups.setdefault(m.group(1), []).append(c)
    return {g: v for g, v in groups.items() if len(v) >= 2}


def handle_missing(df: pd.DataFrame, id_var: str):
    mresp_flat = {c for cols in detect_multiresp(list(detect_pairs(df.columns).keys())).values() for c in cols}
    for col in mresp_flat:
        df[col] = df[col].notna().astype(int)
    for col in df.columns:
        if col in mresp_flat or col == id_var:
            continue
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_integer_dtype(df[col]):
            if df[col].nunique(dropna=True) <= 20:
                df[col] = df[col].fillna('스킵(해당 없음)')
    return df


def add_weights(df: pd.DataFrame, pop_df: pd.DataFrame, strata, pop_col='pop_share'):
    df['__key__'] = list(zip(*[df[c] for c in strata]))
    pop_df['__key__'] = list(zip(*[pop_df[c] for c in strata]))
    samp = df['__key__'].value_counts() / len(df)
    samp.name = 'sample_share'
    df = df.merge(samp.to_frame(), left_on='__key__', right_index=True)
    df = df.merge(pop_df[['__key__', pop_col]], on='__key__', how='left')
    df[pop_col] = df[pop_col].fillna(0)
    df['weight'] = df[pop_col] / df['sample_share']
    return df.drop(columns=['__key__', 'sample_share', pop_col])


def label_encode(df: pd.DataFrame):
    pairs = detect_pairs(df.columns)
    mresp_flat = {c for cols in detect_multiresp(list(pairs.keys())).values() for c in cols}
    used = set(df.columns)
    for code_col, text_col in pairs.items():
        if code_col in mresp_flat:
            lbl = df[text_col].dropna().astype(str).unique()
            lbl = lbl[0] if len(lbl) else code_col
            base, i = lbl, 1
            while lbl in used:
                lbl = f"{base}_{i}"; i += 1
            df.rename(columns={code_col: lbl}, inplace=True)
            used.add(lbl)
        else:
            df[code_col] = df[text_col]
        df.drop(columns=text_col, inplace=True)
    return df


def build_codebook(orig_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    pairs = detect_pairs(orig_df.columns)
    for code_col, text_col in pairs.items():
        subset = orig_df[[code_col, text_col]].dropna().drop_duplicates()
        if subset.empty:
            continue
        for code, label in subset.values:
            rows.append({'variable': code_col, 'code': code, 'label': label})
    # Add binary MR columns without TEXT
    mresp_flat = {c for cols in detect_multiresp(list(pairs.keys())).values() for c in cols}
    for col in mresp_flat:
        if col not in pairs:
            rows.append({'variable': col, 'code': 1, 'label': 'Selected'})
    return pd.DataFrame(rows)


def tidy_zip(df: pd.DataFrame, id_var: str) -> bytes:
    pairs = detect_pairs(df.columns)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        if pairs:
            frames = []
            for code_col, text_col in pairs.items():
                tid = df[[id_var, code_col, text_col]].dropna(subset=[code_col]).rename(
                    columns={code_col:'code_value', text_col:'label'})
                tid['variable'] = code_col
                frames.append(tid[[id_var,'variable','code_value','label']])
            zf.writestr('all_tidy.csv', pd.concat(frames).to_csv(index=False, encoding='utf-8-sig'))
    return buf.getvalue()

# ---------- Streamlit UI ----------

st.set_page_config(page_title="Survey Toolkit", page_icon="📊")
st.title("📊 Survey Pre-processing Toolkit – v6")

raw = st.sidebar.file_uploader("Raw survey file", type=["xlsx", "xls", "csv"])
id_var = st.sidebar.text_input("ID column", value="회원ID")

# weight options
use_w = st.sidebar.checkbox("Enable weights")
if use_w:
    pop_f = st.sidebar.file_uploader("Population CSV", type=["csv","xlsx","xls"], key='pop')
    strata_cols = st.sidebar.text_input("Strata columns (comma-sep)")
    pop_col = st.sidebar.text_input("Population share column", value='pop_share')
else:
    pop_f = None

# processing toggles
miss_ck = st.sidebar.checkbox("Missing-value handling", value=True)
lab_ck  = st.sidebar.checkbox("Label encoding")
tidy_ck = st.sidebar.checkbox("Tidy export (zip)")
run     = st.sidebar.button("🚀 Run")

if not run or raw is None:
    st.info("Upload Raw file and click Run.")
    st.stop()

# Load raw + keep a copy for codebook
suf = Path(raw.name).suffix.lower()
orig_df = pd.read_excel(raw, header=1) if suf in {'.xlsx', '.xls'} else pd.read_csv(raw)
proc_df = orig_df.copy()

# Weights
if use_w:
    if pop_f is None:
        st.error("Population file missing"); st.stop()
    strata = [s.strip() for s in strata_cols.split(',') if s.strip()]
    if not strata:
        st.error("Enter strata columns and rerun"); st.stop()
    pop_df = pd.read_csv(pop_f) if Path(pop_f.name).suffix.lower()=='.csv' else pd.read_excel(pop_f)
    proc_df = add_weights(proc_df, pop_df, strata, pop_col=pop_col)
    st.success("Weights added ✅")

# Missing
if miss_ck:
    proc_df = handle_missing(proc_df, id_var)
    st.success("Missing handling done ✅")

# Label
if lab_ck:
    proc_df = label_encode(proc_df)
    st.success("Label encoding done ✅")

# Codebook sheet
codebook_df = build_codebook(orig_df)

# Tidy zip
if tidy_ck:
    zbytes = tidy_zip(orig_df, id_var)
    st.download_button("Download tidy zip", zbytes, file_name="tidy_outputs.zip", mime="application/zip")

# Final Excel with codebook
bio = io.BytesIO()
with pd.ExcelWriter(bio, engine='openpyxl') as xl:
    proc_df.to_excel(xl, index=False, sheet_name='data')
    if not codebook_df.empty:
        codebook_df.to_excel(xl, index=False, sheet_name='codebook')

st.download_button("Download processed Excel (+ codebook)", bio.getvalue(), file_name="processed.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
