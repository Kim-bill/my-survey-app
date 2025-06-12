# streamlit_survey_prepro_app.py — v3
"""
Streamlit web‑app — Survey Pre‑processing Toolkit  📊
====================================================
이번 버전은 **Raw 파일 1행의 질문 문장**을 자동으로 읽어
변수 코드(Q1, Q2_1 …)를 질문 텍스트로 교체합니다.

* 다중응답(Q2_1, Q2_2 …)처럼 질문이 같은 열이 여러 개면
  중복을 막기 위해 텍스트 뒤에 원래 코드명을 붙입니다.
* 사용자는 사이드바 체크박스로 Auto‑label 기능을 켜거나 끌 수 있습니다.

기타 파이프라인(가중치, 미싱, tidy, 라벨링)은 이전 버전과 동일합니다.
"""
from __future__ import annotations
import io, zipfile, re
from pathlib import Path
import pandas as pd
import streamlit as st

# ---------------- Helper Routines ---------------- #

def detect_pairs(columns):
    """detect <code, code(TEXT)> column pairs"""
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

# --- Missing handling

def handle_missing(df: pd.DataFrame, id_var: str):
    pairs = detect_pairs(df.columns)
    mresp_flat = {c for cols in detect_multiresp(list(pairs.keys())).values() for c in cols}
    for col in mresp_flat:
        df[col] = df[col].notna().astype(int)
    for col in df.columns:
        if col in mresp_flat or col == id_var:
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

# --- Label encode (code→label, MR rename)

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

# --- Tidy export (zip)

def tidy_zip(df: pd.DataFrame, id_var: str) -> bytes:
    pairs = detect_pairs(df.columns)
    mresp_groups = detect_multiresp(list(pairs.keys()))
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
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
    return zip_buf.getvalue()

# ---------------- Streamlit UI ---------------- #

st.set_page_config(page_title="Survey Toolkit", page_icon="📊", layout="centered")
st.title("📊 Survey Pre‑processing Toolkit")

# Upload raw
raw_file = st.sidebar.file_uploader("1️⃣ Raw survey file (Excel/CSV)", type=["xlsx", "xls", "csv"])
use_auto_label = st.sidebar.checkbox("Use question text as column label", value=True)

id_var = st.sidebar.text_input("Respondent ID column", value="회원ID")

# Population (weight)
use_weight = st.sidebar.checkbox("Enable weights")
if use_weight:
    pop_file = st.sidebar.file_uploader("Population CSV", type=["csv", "xlsx", "xls"], key="pop")
    pop_col_name = st.sidebar.text_input("Population share column", value="pop_share")
else:
    pop_file = None

# Steps
step_missing = st.sidebar.checkbox("Missing-value handling", value=True)
step_tidy = st.sidebar.checkbox("Tidy long export")
step_label = st.sidebar.checkbox("Label encoding", value=True)
run = st.sidebar.button("🚀 Run")

if not run or raw_file is None:
    st.info("📂 Upload Raw file and click ‘Run’.")
    st.stop()

# -------- Read raw ----------
raw_suffix = Path(raw_file.name).suffix.lower()
if raw_suffix in {'.xlsx', '.xls'}:
    df = pd.read_excel(raw_file, header=1)
    if use_auto_label:
        # read first two rows separately for mapping
        raw_top = pd.read_excel(raw_file, header=None, nrows=2)
else:
    df = pd.read_csv(raw_file)
    if use_auto_label:
        raw_top = pd.read_csv(raw_file, header=None, nrows=2)

# --- Auto label mapping ---
if use_auto_label:
    question_row = raw_top.iloc[0]
    code_row = raw_top.iloc[1]
    mapping: dict[str,str] = {}
    for q_text, code in zip(question_row, code_row):
        if pd.notna(code):
            mapping[str(code)] = str(q_text)
    rename_map, used = {}, set()
    for col in df.columns:
        new_lbl = mapping.get(str(col), str(col))
        if new_lbl in used:
            new_lbl = f"{new_lbl} ({col})"  # avoid duplicates
        rename_map[col] = new_lbl
        used.add(new_lbl)
    df.rename(columns=rename_map, inplace=True)
    st.success(f"Auto‑labeled {len(rename_map)} columns using question text ✅")

# -------- Weight --------
if use_weight:
    if pop_file is None:
        st.error("Population CSV missing."); st.stop()
    pop_df = pd.read_csv(pop_file) if Path(pop_file.name).suffix.lower()=='.csv' else pd.read_excel(pop_file)
    strata = st.multiselect("Pick strata columns", options=df.columns.tolist(), default=[])
    if not strata: st.error("Select strata columns"); st.stop()
    df = add_weights(df, pop_df, strata, pop_col=pop_col_name)
    st.success("Weight column added ✅")

# -------- Missing --------
if step_missing:
    df = handle_missing(df, id_var)
    st.success("Missing-value handling done ✅")

# -------- Tidy --------
if step_tidy:
    zip_bytes = tidy
