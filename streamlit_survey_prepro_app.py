# streamlit_survey_prepro_app.py — v3.1 (download fix)
"""
Streamlit Survey Pre‑processing Toolkit  📊
=========================================
*Fix*: Always show **Download processed Excel** button even when only a subset of
steps is selected. (Previous cut‑off prevented the button from rendering.)
"""
from __future__ import annotations
import io, zipfile, re
from pathlib import Path
import pandas as pd
import streamlit as st

# ---------------- Helper Routines (unchanged) ---------------- #

def detect_pairs(columns):
    pairs = {}
    for col in columns:
        col_str = str(col)
        if col_str.endswith('(TEXT)'):
            code_col = col_str[:-6]
            if code_col in columns or code_col in [str(c) for c in columns]:
                pairs[code_col] = col
    return pairs

def detect_multiresp(code_cols):
    groups: dict[str, list[str]] = {}
    for c in code_cols:
        m = re.match(r'(.*?)_', str(c))
        if m:
            groups.setdefault(m.group(1), []).append(c)
    return {g: cols for g, cols in groups.items() if len(cols) >= 2}


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

def add_weights(df: pd.DataFrame, pop_df: pd.DataFrame, strata: list[str], pop_col: str='pop_share'):
    df['__key__'] = list(zip(*[df[c] for c in strata]))
    pop_df['__key__'] = list(zip(*[pop_df[c] for c in strata]))
    samp_share = df['__key__'].value_counts() / len(df)
    samp_share.name = 'sample_share'
    df = df.merge(samp_share.to_frame(), left_on='__key__', right_index=True)
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
    mresp_groups = detect_multiresp(list(pairs.keys()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        all_frames = []
        for code_col, text_col in pairs.items():
            tidy = (df[[id_var, code_col, text_col]].dropna(subset=[code_col])
                    .rename(columns={code_col:'code_value', text_col:'option_text'}))
            tidy['option'] = code_col
            tidy = tidy[[id_var,'option','code_value','option_text']]
            all_frames.append(tidy)
        if all_frames:
            zf.writestr('all_tidy.csv', pd.concat(all_frames).to_csv(index=False, encoding='utf-8-sig'))
        for g, cols in mresp_groups.items():
            frames = []
            for c in cols:
                t = df[[id_var, c, pairs[c]]].dropna(subset=[c])
                t = t.rename(columns={c:'code_value', pairs[c]:'option_text'})
                t['option'] = c
                frames.append(t[[id_var,'option','code_value','option_text']])
            if frames:
                zf.writestr(f'{g}_tidy.csv', pd.concat(frames).to_csv(index=False, encoding='utf-8-sig'))
    return buf.getvalue()

# ---------------- Streamlit UI ---------------- #

st.set_page_config(page_title="Survey Toolkit", page_icon="📊", layout="centered")
st.title("📊 Survey Pre-processing Toolkit")

raw_file = st.sidebar.file_uploader("Raw survey file", type=["xlsx","xls","csv"])
use_auto = st.sidebar.checkbox("Use question text as column label", value=True)
id_col = st.sidebar.text_input("ID column", value="회원ID")

use_wgt = st.sidebar.checkbox("Enable weights")
if use_wgt:
    pop_file = st.sidebar.file_uploader("Population CSV", type=["csv","xlsx","xls"], key='pop')
    pop_col = st.sidebar.text_input("Population share column", value='pop_share')
else:
    pop_file = None

step_miss = st.sidebar.checkbox("Missing-value handling", value=True)
step_tidy = st.sidebar.checkbox("Tidy export")
step_lab  = st.sidebar.checkbox("Label encoding", value=True)
run = st.sidebar.button("🚀 Run")

if not run or raw_file is None:
    st.info("Upload a Raw file and click Run.")
    st.stop()

# ---------- Load Raw ----------
suf = Path(raw_file.name).suffix.lower()
if suf in {'.xlsx','.xls'}:
    df = pd.read_excel(raw_file, header=1)
    top_two = pd.read_excel(raw_file, header=None, nrows=2) if use_auto else None
else:
    df = pd.read_csv(raw_file)
    top_two = pd.read_csv(raw_file, header=None, nrows=2) if use_auto else None

# ---------- Auto-label ----------
if use_auto and top_two is not None:
    q_row, code_row = top_two.iloc[0], top_two.iloc[1]
    mapping = {str(code): str(q) for q, code in zip(q_row, code_row) if pd.notna(code)}
    rename = {}
    used = set()
    for col in df.columns:
        new = mapping.get(str(col), str(col))
        if new in used:
            new = f"{new} ({col})"
        rename[col] = new
        used.add(new)
    df.rename(columns=rename, inplace=True)
    st.success(f"Auto-labeled {len(rename)} columns ✅")

# ---------- Weight ----------
if use_wgt:
    if pop_file is None:
        st.error("Population file missing"); st.stop()
    pop_df = pd.read_csv(pop_file) if Path(pop_file.name).suffix.lower()=='.csv' else pd.read_excel(pop_file)
    strata_cols = st.multiselect("Strata columns", options=df.columns.tolist())
    if not strata_cols:
        st.error("Select strata columns"); st.stop()
    df = add_weights(df, pop_df, strata_cols, pop_col=pop_col)
    st.success("Weight column added ✅")

# ---------- Missing ----------
if step_miss:
    df = handle_missing(df, id_col)
    st.success("Missing handling done ✅")

# ---------- Tidy ----------
if step_tidy:
    tidy_zip_bytes = tidy_zip(df, id_col)
    st.download_button("Download tidy CSVs", tidy_zip_bytes, file_name="tidy_outputs.zip", mime="application/zip")

# ---------- Label ----------
if step_lab:
    df = label_encode(df, id_col)
    st.success("Label encoding done ✅")

# ---------- Final Excel download (always shown) ----------
excel_io = io.BytesIO()
df.to_excel(excel_io, index=False, engine='openpyxl')
st.download_button("Download processed Excel", data=excel_io.getvalue(), file_name="processed.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
