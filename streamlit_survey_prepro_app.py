# streamlit_survey_prepro_app.py
"""
Streamlit web‑app — Survey Pre‑processing Toolkit
=================================================
Upload a raw (or partially processed) survey file and choose which processing step(s)
you want to run. The app wraps the modular scripts we built earlier and runs them
in‑memory, returning a processed file for download.

Main features
-------------
1. **Missing‑value handling**  (binary encode multi‑response, fill NA=스킵)
2. **Weight calculation**      (requires population CSV and strata columns)
3. **Label encoding**          (code→label, MR column rename)
4. **Tidy long export**        (per MR group + master) – as zip file

Prerequisites
-------------
```bash
pip install streamlit pandas openpyxl
```
Then run:
```bash
streamlit run streamlit_survey_prepro_app.py
```
"""

import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------- helper routines (taken from previous scripts) ---------------- #

def detect_pairs(columns):
    """Safely detect code/TEXT column pairs even when column names are not strings."""
    pairs = {}
    for col in columns:
        col_str = str(col)
        if col_str.endswith('(TEXT)'):
            code_col = col_str[:-6]
            # find matching original column object (string or otherwise)
            if code_col in columns or code_col in [str(c) for c in columns]:
                pairs[code_col] = col
    return pairs

def detect_multiresp(code_cols):
    import re
    groups = {}
    for c in code_cols:
        m = re.match(r'(.*?)_', c)
        if m:
            groups.setdefault(m.group(1), []).append(c)
    return {g: cols for g, cols in groups.items() if len(cols) >= 2}

# --- Missing handling

def handle_missing(df: pd.DataFrame, id_var: str):
    pairs = detect_pairs(df.columns)
    multiresp_cols = detect_multiresp(list(pairs.keys()))
    multiresp_flat = {c for cols in multiresp_cols.values() for c in cols}
    # binary encode
    for col in multiresp_flat:
        df[col] = df[col].notna().astype(int)
    # conditional single response
    for col in df.columns:
        if col in multiresp_flat or col == id_var:
            continue
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_integer_dtype(df[col]):
            if df[col].nunique(dropna=True) <= 20:
                df[col] = df[col].fillna('스킵(해당 없음)')
    return df

# --- Weight calc

def add_weights(df: pd.DataFrame, pop_df: pd.DataFrame, strata: list[str], pop_col: str = 'pop_share'):
    df['__key__'] = list(zip(*[df[c] for c in strata]))
    pop_df['__key__'] = list(zip(*[pop_df[c] for c in strata]))
    samp_share = df['__key__'].value_counts() / len(df)
    samp_share.name = 'sample_share'
    df = df.merge(samp_share.to_frame(), left_on='__key__', right_index=True)
    df = df.merge(pop_df[['__key__', pop_col]], on='__key__', how='left')
    df[pop_col] = df[pop_col].fillna(0)
    df['weight'] = df[pop_col] / df['sample_share']
    return df.drop(columns=['__key__', 'sample_share', pop_col])

# --- Label encode

def label_encode(df: pd.DataFrame, id_var: str):
    pairs = detect_pairs(df.columns)
    mresp = detect_multiresp(list(pairs.keys()))
    mresp_flat = {c for cols in mresp.values() for c in cols}
    used = set(df.columns)
    for code_col, text_col in pairs.items():
        if code_col in mresp_flat:
            label = df[text_col].dropna().astype(str).unique()
            label = label[0] if len(label) else code_col
            base, i = label, 1
            while label in used:
                label = f"{base}_{i}"; i += 1
            df.rename(columns={code_col: label}, inplace=True)
            used.add(label)
        else:
            df[code_col] = df[text_col]
        df.drop(columns=text_col, inplace=True)
    return df

# --- Tidy export

def tidy_zip(df: pd.DataFrame, id_var: str) -> bytes:
    pairs = detect_pairs(df.columns)
    mresp_groups = detect_multiresp(list(pairs.keys()))
    all_frames = []
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for code_col, text_col in pairs.items():
            tidy = (df[[id_var, code_col, text_col]].dropna(subset=[code_col])
                    .rename(columns={code_col:'code_value', text_col:'option_text'}))
            tidy['option'] = code_col
            tidy = tidy[[id_var,'option','code_value','option_text']]
            all_frames.append(tidy)
        if all_frames:
            all_df = pd.concat(all_frames)
            csv_bytes = all_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            zf.writestr('all_tidy.csv', csv_bytes)
        for g, cols in mresp_groups.items():
            frames = []
            for c in cols:
                t = df[[id_var, c, pairs[c]]].dropna(subset=[c])
                t = t.rename(columns={c:'code_value', pairs[c]:'option_text'})
                t['option'] = c
                frames.append(t[[id_var,'option','code_value','option_text']])
            if frames:
                csv_bytes = pd.concat(frames).to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                zf.writestr(f'{g}_tidy.csv', csv_bytes)
    return zip_buffer.getvalue()

# ---------------- Streamlit UI ---------------- #

st.title("📊 Survey Pre‑processing Toolkit")

st.sidebar.header("1️⃣ Upload Files")
raw_file = st.sidebar.file_uploader("Raw survey Excel/CSV", type=["xlsx","xls","csv"])
id_var = st.sidebar.text_input("Respondent ID column", value="회원ID")

st.sidebar.markdown("---")
st.sidebar.header("2️⃣ Optional: Population CSV (for weights)")
use_weight = st.sidebar.checkbox("Enable Weight Calculation")
if use_weight:
    pop_file = st.sidebar.file_uploader("Population CSV", type=["csv","xlsx","xls"], key="pop")
    strata_cols = st.sidebar.text_input("Strata column names (comma‑sep)")
    pop_col_name = st.sidebar.text_input("Population share column", value="pop_share")
else:
    pop_file = None

st.sidebar.markdown("---")
st.sidebar.header("3️⃣ Select Steps")
do_missing = st.sidebar.checkbox("Missing‑value handling", value=True)
do_tidy   = st.sidebar.checkbox("Tidy(long) export")
do_label  = st.sidebar.checkbox("Label encoding", value=True)
run_btn = st.sidebar.button("🚀 Run Processing")

# result placeholders
if run_btn and raw_file is not None:
    # read input
    suf = Path(raw_file.name).suffix.lower()
    if suf in {'.xlsx', '.xls'}:
        df = pd.read_excel(raw_file, header=1)
    else:
        df = pd.read_csv(raw_file)

    if use_weight:
        if pop_file is None or not strata_cols:
            st.error("Population file & strata must be provided for weights.")
            st.stop()
        pop_df = pd.read_csv(pop_file) if Path(pop_file.name).suffix.lower() == '.csv' else pd.read_excel(pop_file)
        strata = [c.strip() for c in strata_cols.split(',') if c.strip()]
        df = add_weights(df, pop_df, strata, pop_col=pop_col_name)
        st.success("Weight column added ✅")

    if do_missing:
        df = handle_missing(df, id_var)
        st.success("Missing‑value handling complete ✅")

    if do_tidy:
        zip_bytes = tidy_zip(df, id_var)
        st.download_button("Download tidy CSVs (zip)", data=zip_bytes, file_name="tidy_outputs.zip", mime="application/zip")

    if do_label:
        df = label_encode(df, id_var)
        st.success("Label encoding complete ✅")

    # Prepare final download
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False, engine='openpyxl')
    st.download_button("Download processed file (Excel)", data=towrite.getvalue(), file_name="processed.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("📂 먼저 Raw 파일을 업로드하고, 왼쪽 사이드바에서 처리 단계를 선택한 뒤 ‘Run Processing’ 버튼을 눌러 주세요.")
