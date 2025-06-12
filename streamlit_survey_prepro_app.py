# streamlit_survey_prepro_app.py — v4 (Manual label mapping)
"""
Streamlit Survey Pre-processing Toolkit  📊
=========================================
This version **removes the automatic question-text renaming** and instead lets
users manually map variable codes to human‑readable labels *after* cleaning.

Workflow
--------
1. Upload Raw survey Excel/CSV (header row 2).
2. Choose processing steps: Weight, Missing, Tidy, etc.
3. Click **Run** → the cleaned DataFrame appears with editable label inputs.
4. Enter/modify labels → Click **Apply labels & download** to get final Excel.

Advantages
~~~~~~~~~~
* Users see the cleaned file first, then decide which columns need meaningful
  names.
* Works even when the original file lacks `(TEXT)` label columns.
"""
from __future__ import annotations
import io, zipfile, re
from pathlib import Path
import pandas as pd
import streamlit as st

# ------- helper routines (same as before) ------- #

def detect_pairs(columns):
    return {col[:-6]: col for col in columns if str(col).endswith('(TEXT)') and str(col)[:-6] in columns}

def detect_multiresp(code_cols):
    groups = {}
    for c in code_cols:
        m = re.match(r'(.*?)_', str(c))
        if m:
            groups.setdefault(m.group(1), []).append(c)
    return {g: cols for g, cols in groups.items() if len(cols) >= 2}


def handle_missing(df, id_var):
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


def add_weights(df, pop_df, strata, pop_col='pop_share'):
    df['__key__'] = list(zip(*[df[c] for c in strata]))
    pop_df['__key__'] = list(zip(*[pop_df[c] for c in strata]))
    samp_share = df['__key__'].value_counts() / len(df)
    samp_share.name = 'sample_share'
    df = df.merge(samp_share.to_frame(), left_on='__key__', right_index=True)
    df = df.merge(pop_df[['__key__', pop_col]], on='__key__', how='left')
    df[pop_col] = df[pop_col].fillna(0)
    df['weight'] = df[pop_col] / df['sample_share']
    return df.drop(columns=['__key__', 'sample_share', pop_col])


# ------- Streamlit UI ------- #

st.set_page_config(page_title="Survey Toolkit", page_icon="📊", layout="wide")
st.title("📊 Survey Pre-processing Toolkit — Manual label mapping")

raw = st.sidebar.file_uploader("Raw survey file (Excel/CSV)", type=["xlsx", "xls", "csv"])
id_var = st.sidebar.text_input("ID column", value="회원ID")

# weight
use_w = st.sidebar.checkbox("Enable weights")
if use_w:
    pop_f = st.sidebar.file_uploader("Population CSV", type=["csv", "xlsx", "xls"], key='pop')
    pop_col = st.sidebar.text_input("Population share column", value='pop_share')
else:
    pop_f = None

# steps
miss_ck = st.sidebar.checkbox("Missing-value handling", value=True)
tidy_ck = st.sidebar.checkbox("Tidy export (zip)")
run_btn = st.sidebar.button("🚀 Run cleaning")

if not run_btn or raw is None:
    st.info("Upload Raw file > select steps > Run cleaning.")
    st.stop()

# load raw
suf = Path(raw.name).suffix.lower()
if suf in {'.xlsx', '.xls'}:
    df = pd.read_excel(raw, header=1)
else:
    df = pd.read_csv(raw)

# weight
if use_w:
    if pop_f is None:
        st.error("Population file required"); st.stop()
    pop_df = pd.read_csv(pop_f) if Path(pop_f.name).suffix.lower()=='.csv' else pd.read_excel(pop_f)
    strata = st.sidebar.multiselect("Strata columns", options=df.columns.tolist())
    if not strata:
        st.error("Pick strata columns in sidebar then rerun"); st.stop()
    df = add_weights(df, pop_df, strata, pop_col=pop_col)
    st.sidebar.success("Weights added")

# missing
df_clean = handle_missing(df, id_var) if miss_ck else df.copy()

# tidy zip
if tidy_ck:
    def tidy_zip_bytes(df):
        # minimalist: all cols melted
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('clean_wide.csv', df.to_csv(index=False, encoding='utf-8-sig'))
        return buf.getvalue()
    st.download_button("Download tidy zip", tidy_zip_bytes(df_clean), file_name="tidy.zip", mime="application/zip")

# -------------- Manual label mapping UI -----------------

st.subheader("✏️ Manual variable labeling")
cols = st.multiselect("Choose columns to label", options=df_clean.columns.tolist())

new_labels = {}
if cols:
    for c in cols:
        new_lbl = st.text_input(f"{c} →", key=f"lbl_{c}")
        if new_lbl:
            new_labels[c] = new_lbl
else:
    st.write("Select columns to rename above.")

if st.button("Apply labels & download Excel"):
    df_final = df_clean.rename(columns=new_labels)
    excel_io = io.BytesIO()
    df_final.to_excel(excel_io, index=False, engine='openpyxl')
    st.download_button("Download labeled Excel", excel_io.getvalue(), file_name="processed_labeled.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.success("Labels applied + file ready for download ✅")
