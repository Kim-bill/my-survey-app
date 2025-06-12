# 🏃‍♀️ Survey Pre‑processing Toolkit

A minimal Streamlit web‑app for one‑click cleaning of multi‑response survey data.

## What it does
| Step | Purpose | Toggle |
|------|---------|--------|
| **Weight calculation** | Attach sampling weights from a population CSV | *Enable weights* |
| **Missing‑value handling** | • Binary‑encode multi‑response columns<br>• Fill conditional‑skip cells with `스킵(해당 없음)` | Always **ON** by default (can be unticked) |
| **Label encoding** | Replace numeric codes with text labels using existing `(TEXT)` columns | Optional (off by default) |
| **Tidy export** | Output long‑format CSVs (per MR set + master) as a zip | Optional |

> **Note** Automatic or manual column‑name relabeling has been removed. The app now relies exclusively on `(TEXT)` columns for value labels. If your raw data does not include those columns, keep *Label encoding* unchecked.

## Quick start (local)
```bash
# 1 clone repo & install deps
pip install -r requirements.txt

# 2 run Streamlit app
streamlit run streamlit_survey_prepro_app.py
```

## Deploy on Streamlit Cloud
1. Push the repo to GitHub.
2. Open **https://streamlit.io/cloud** → **New app**.
3. Fill in Repository, Branch (`main`), and Main file (`streamlit_survey_prepro_app.py`).
4. Click **Deploy** – your app will be live at `https://<project-id>.streamlit.app`.

## Repository layout
```
my-survey-app/
├─ streamlit_survey_prepro_app.py   ← main app (v5)
├─ requirements.txt                 ← Python deps
└─ README.md                        ← this file
```

---
© 2025 Your Name — MIT License.
