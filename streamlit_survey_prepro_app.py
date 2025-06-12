# streamlit_survey_prepro_app.py — v5 (simple pipeline)
"""
Streamlit Survey Pre‑processing Toolkit  📊  — *Reset to simple pipeline*
======================================================================
* Upload Raw → select cleaning steps (Weight, Missing, Tidy, Label) → Run  → Download Excel (+ Tidy zip)
* **No auto‑question text renaming**
* **No manual label UI** — relies solely on existing `(TEXT)` columns for label encoding.
"""

from __future__ import annotations
import io, zipfile, re
from pathlib import Path
import pandas as pd
import streamlit as st

# ---------- Helper functions ----------

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


def add_weights(df: pd.DataFrame, pop_df: pd.DataFrame, strata: list[str], pop_col='pop_share'):
    df['__key__'] = list(zip(*[df[c] for c in strata]))
    pop_df['__key__'] = list(zip(*[pop_df[c] for c in strata]))
    samp = df['__key__'].value_counts() / len(df)
    samp.name = 'sample_share'
    df = df.merge(samp.to_frame(), left_on='__key__', right_index=True)
    df = df.merge(pop_df[['__key__', pop_col]], on='__key__', how='left')
    df[pop_col] = df[pop_col].fillna(0)
    df['weight'] = df[pop_col] / df['sample_share']
    return df.drop(columns=['__key__', 'sample_share', pop_col])


def label_encode(df: pd.DataFrame, id_var: str):
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


def tidy_zip(df: pd.DataFrame, id_var: str) -> bytes:
    pairs = detect_pairs(df.columns)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        if pairs:
            frames = []
            for code_col, text_col in pairs.items():
                tid = df[[id_var, code_col, text_col]].dropna(subset=[code_col]).rename(
                    columns={code_col:'code_value', text_col:'option_text'})
                tid['option'] = code_col
                frames.append(tid[[id_var,'option','code_value','option_text']])
            zf.writestr('all_tidy.csv', pd.concat(frames).to_csv(index=False, encoding='utf-8-sig'))
    return buf.getvalue()

# ---------- Streamlit UI ----------

st.set_page_config(page_title="Survey Toolkit", page_icon="📊")
st.title("📊 Survey Pre-processing Toolkit")

raw_file = st.sidebar.file_uploader("Raw survey file (Excel/CSV)", type=["xlsx","xls","csv"])
id_var = st.sidebar.text_input("Respondent ID column", value="회원ID")

# Weight options
use_w = st.sidebar.checkbox("Enable weights")
if use_w:
    pop_file = st.sidebar.file_uploader("Population CSV", type=["csv","xlsx","xls"], key='pop')
    pop_col = st.sidebar.text_input("Population share column", value='pop_share')
    strata_cols = st.sidebar.text_input("Strata columns (comma‑sep)")
else:
    pop_file = None

# Steps
miss_ck = st.sidebar.checkbox("Missing-value handling", value=True)
lab_ck  = st.sidebar.checkbox("Label encoding", value=False)
tidy_ck = st.sidebar.checkbox("Tidy export")
run = st.sidebar.button("🚀 Run")

if not run or raw_file is None:
    st.info("📂 Upload Raw file and click *Run*.")
    st.stop()

# Load Raw
suf = Path(raw_file.name).suffix.lower()
df = pd.read_excel(raw_file, header=1) if suf in {'.xlsx','.xls'} else pd.read_csv(raw_file)

# Weight
if use_w:
    if pop_file is None:
        st.error("Population file missing"); st.stop()
    strata = [s.strip() for s in strata_cols.split(',') if s.strip()]
    if not strata:
        st.error("Enter strata column names"); st.stop()
    pop_df = pd.read_csv(pop_file) if Path(pop_file.name).suffix.lower()=='.csv' else pd.read_excel(pop_file)
    df = add_weights(df, pop_df, strata, pop_col=pop_col)
    st.success("Weight column added ✅")

# Missing
if miss_ck:
    df = handle_missing(df, id_var)
    st.success("Missing-value handling done ✅")

# Label
if lab_ck:
    df = label_encode(df, id_var)
    st.success("Label encoding done ✅")

# Tidy
if tidy_ck:
    zbytes = tidy_zip(df, id_var)
    st.download_button("Download tidy zip", zbytes, file_name="tidy_outputs.zip", mime="application/zip")

# Final download
bio = io.BytesIO()
df.to_excel(bio, index=False, engine='openpyxl')
st.download_button("Download processed Excel", bio.getvalue(), file_name="processed.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
