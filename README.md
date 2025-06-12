# 🏃‍♀️ Survey Pre‑processing Toolkit

A lightweight Streamlit web‑app for one‑click cleaning of multi‑response survey data.

## Features
- **Missing‑value handling**  – binary‑encode MR items, fill skips
- **Weight calculation**     – attach sampling weights from a population CSV
- **Label encoding**         – replace numeric codes with human labels
- **Tidy export**            – download long‑format CSVs (per MR set & master)

## Quick start (local)
```bash
# 1  clone repo & install deps
pip install -r requirements.txt

# 2  run Streamlit app
streamlit run streamlit_survey_prepro_app.py
```
The UI lets you upload your *Raw* Excel/CSV and (optionally) a *population.csv* file, choose the steps to run, and download the processed output.

## Deploy on Streamlit Cloud
1. Push the repo to GitHub.
2. Go to **https://streamlit.io/cloud** → **New app**.
3. Fill in:
   - **Repository**  `<USER>/<REPO>`
   - **Branch**      `main`
   - **Main file**   `streamlit_survey_prepro_app.py`
4. Click **Deploy** – the app will be live at `https://<project-id>.streamlit.app`.

## File layout
```
my-survey-app/
├─ streamlit_survey_prepro_app.py   ← main app
├─ requirements.txt                 ← Python deps
└─ README.md                        ← this file
```

---
© 2025  Your Name. MIT License.
