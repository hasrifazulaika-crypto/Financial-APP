
import os
import io
import re
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime, date

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# Optional document readers
try:
    import fitz
except ImportError:
    fitz = None

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

# AI providers
try:
    from google import genai
except ImportError:
    genai = None

try:
    from groq import Groq
except ImportError:
    Groq = None


# =========================================================
# 1. CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="FINORA AI | Financial Intelligence",
    page_icon="💗",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = os.getenv("FINORA_DB_PATH", "finora.db")

PINK = "#FF5C8B"
PINK_LIGHT = "#FFE1E8"
CREAM = "#FFF4E8"
CREAM_DARK = "#F9EBDD"
TEXT = "#593746"
WHITE = "#FFFFFF"

def get_secret(key, default=None):
    try:
        value = st.secrets.get(key)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(key, default)

GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
GROQ_API_KEY = get_secret("GROQ_API_KEY")
RECOVERY_KEY = get_secret("FINORA_RECOVERY_KEY")


# =========================================================
# 2. THEME
# =========================================================

st.markdown(f"""
<style>
.stApp {{
    background: {CREAM};
    color: {TEXT};
}}
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #FFE1E8 0%, #FFF4E8 100%);
    border-right: 1px solid #F5C4D2;
}}
[data-testid="stSidebar"] * {{
    color: {TEXT};
}}
h1, h2, h3 {{
    color: {TEXT} !important;
}}
[data-testid="stMetric"] {{
    background: white;
    border: 1px solid #F4CAD7;
    padding: 16px;
    border-radius: 14px;
}}
[data-testid="stMetricValue"] {{
    color: {PINK};
}}
.stButton > button {{
    background: {PINK};
    color: white;
    border: none;
    border-radius: 10px;
    font-weight: 600;
}}
.stButton > button:hover {{
    background: #E84979;
    color: white;
}}
.stDownloadButton > button {{
    border: 1px solid {PINK};
    border-radius: 9px;
}}
[data-testid="stFileUploader"] {{
    background: white;
    border: 1px dashed {PINK};
    border-radius: 12px;
    padding: 12px;
}}
[data-testid="stDataFrame"] {{
    border: 1px solid #F4CAD7;
    border-radius: 10px;
}}
.finora-header {{
    background: linear-gradient(110deg, #FF5C8B, #FF9AB6);
    padding: 26px;
    border-radius: 18px;
    margin-bottom: 20px;
    color: white;
}}
.finora-header h1, .finora-header h2 {{
    color: white !important;
    margin: 0;
}}
.finora-header p {{
    color: white;
    margin: 7px 0 0 0;
}}
.finora-card {{
    background: white;
    border: 1px solid #F4CAD7;
    border-radius: 14px;
    padding: 18px;
}}
.small-note {{
    color: #987486;
    font-size: 12px;
}}
</style>
""", unsafe_allow_html=True)


# =========================================================
# 3. DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT,
        role TEXT DEFAULT 'Admin',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS analysis_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        filename TEXT,
        analysis_type TEXT,
        summary TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        activity TEXT,
        created_at TEXT
    );
    """)

    # Migrate older databases safely
    for table, column, definition in [
        ("users", "full_name", "TEXT"),
        ("users", "role", "TEXT DEFAULT 'Admin'"),
        ("users", "created_at", "TEXT"),
        ("activity_logs", "created_at", "TEXT"),
    ]:
        existing = {
            row["name"]
            for row in cur.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }
        if column not in existing:
            cur.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    cur.execute("""
        UPDATE users
        SET full_name=username
        WHERE full_name IS NULL OR full_name=''
    """)

    cur.execute("""
        UPDATE users SET role='Admin'
        WHERE role IS NULL OR role=''
    """)

    conn.commit()
    conn.close()


init_db()


def query_df(sql, params=()):
    conn = db()
    result = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return result


def execute(sql, params=()):
    conn = db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def log_activity(activity):
    execute("""
        INSERT INTO activity_logs (username, activity, created_at)
        VALUES (?, ?, ?)
    """, (
        st.session_state.get("username", "system"),
        activity,
        datetime.now().isoformat(timespec="seconds")
    ))


def save_history(filename, analysis_type, summary):
    execute("""
        INSERT INTO analysis_history
        (username, filename, analysis_type, summary, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        st.session_state.get("username", "unknown"),
        filename,
        analysis_type,
        summary[:3000],
        datetime.now().isoformat(timespec="seconds")
    ))


# =========================================================
# 4. AUTHENTICATION
# =========================================================

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        200000
    ).hex()
    return f"{salt}${hashed}"


def verify_password(password, stored):
    try:
        salt, saved_hash = stored.split("$")
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            200000
        ).hex()
        return secrets.compare_digest(candidate, saved_hash)
    except Exception:
        return False


def user_count():
    result = query_df("SELECT COUNT(*) AS total FROM users")
    return int(result.iloc[0]["total"])


def login_screen():
    st.markdown("""
    <div class="finora-header">
        <h1>💗 FINORA AI</h1>
        <p>Financial Intelligence & Audit Platform</p>
    </div>
    """, unsafe_allow_html=True)

    if user_count() == 0:
        st.subheader("Buat Administrator Pertama")

        with st.form("first_admin"):
            full_name = st.text_input("Nama lengkap")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Konfirmasi password", type="password")
            submit = st.form_submit_button("Buat Administrator")

            if submit:
                if not full_name.strip() or not username.strip():
                    st.error("Nama dan username wajib diisi.")
                elif len(password) < 8:
                    st.error("Password minimal 8 karakter.")
                elif password != confirm:
                    st.error("Konfirmasi password tidak sama.")
                else:
                    execute("""
                        INSERT INTO users
                        (username, password, full_name, role, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        username.strip(),
                        hash_password(password),
                        full_name.strip(),
                        "Admin",
                        datetime.now().isoformat()
                    ))
                    st.success("Admin berhasil dibuat. Silakan login.")
                    st.rerun()
        return

    login_tab, reset_tab = st.tabs(["Login", "Reset Password"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Masuk ke FINORA AI")

            if submit:
                users = query_df(
                    "SELECT * FROM users WHERE username=?",
                    (username.strip(),)
                )

                if (
                    not users.empty
                    and verify_password(password, users.iloc[0]["password"])
                ):
                    user = users.iloc[0]
                    st.session_state.authenticated = True
                    st.session_state.username = user["username"]
                    st.session_state.full_name = (
                        user["full_name"] or user["username"]
                    )
                    st.session_state.role = user["role"] or "Admin"
                    log_activity("Login")
                    st.rerun()
                else:
                    st.error("Username atau password salah.")

    with reset_tab:
        st.warning("Masukkan kunci pemulihan yang disimpan di Streamlit Secrets.")

        with st.form("reset_form"):
            username = st.text_input("Username Admin")
            recovery = st.text_input("Kunci Pemulihan", type="password")
            new_password = st.text_input("Password Baru", type="password")
            confirm = st.text_input("Konfirmasi Password Baru", type="password")
            submit = st.form_submit_button("Reset Password")

            if submit:
                if not RECOVERY_KEY:
                    st.error("FINORA_RECOVERY_KEY belum diatur.")
                elif not secrets.compare_digest(
                    str(recovery), str(RECOVERY_KEY)
                ):
                    st.error("Kunci pemulihan salah.")
                elif len(new_password) < 8:
                    st.error("Password minimal 8 karakter.")
                elif new_password != confirm:
                    st.error("Konfirmasi password tidak sama.")
                else:
                    admins = query_df("""
                        SELECT id FROM users
                        WHERE username=? AND role='Admin'
                    """, (username.strip(),))

                    if admins.empty:
                        st.error("Admin tidak ditemukan.")
                    else:
                        execute(
                            "UPDATE users SET password=? WHERE id=?",
                            (
                                hash_password(new_password),
                                int(admins.iloc[0]["id"])
                            )
                        )
                        st.success("Password berhasil diperbarui.")


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login_screen()
    st.stop()


# =========================================================
# 5. UNIVERSAL FILE READER
# =========================================================

def read_uploaded_file(uploaded):
    """
    Returns:
        dataframes: dict of sheet/table name -> DataFrame
        extracted_text: text extracted from PDF or image
    """
    name = uploaded.name.lower()
    dataframes = {}
    extracted_text = ""

    if name.endswith((".xlsx", ".xls")):
        dataframes = pd.read_excel(
            uploaded,
            sheet_name=None
        )

    elif name.endswith(".csv"):
        df = pd.read_csv(uploaded)
        dataframes["CSV Data"] = df

    elif name.endswith(".pdf"):
        if fitz is None:
            raise ValueError("PDF reader belum terpasang. Tambahkan PyMuPDF.")
        pdf = fitz.open(stream=uploaded.getvalue(), filetype="pdf")
        pages = []
        for page_number, page in enumerate(pdf, start=1):
            pages.append(
                f"\n--- HALAMAN {page_number} ---\n{page.get_text()}"
            )
        extracted_text = "\n".join(pages)

    elif name.endswith((".png", ".jpg", ".jpeg")):
        if Image is None or pytesseract is None:
            raise ValueError(
                "OCR belum tersedia. Pastikan Pillow dan pytesseract terpasang. "
                "OCR juga memerlukan Tesseract OCR engine."
            )
        image_file = Image.open(uploaded)
        extracted_text = pytesseract.image_to_string(
            image_file,
            lang="ind+eng"
        )

    else:
        raise ValueError("Format file belum didukung.")

    # Remove completely empty rows and columns
    cleaned = {}
    for sheet_name, frame in dataframes.items():
        frame = frame.dropna(how="all").dropna(axis=1, how="all")
        cleaned[sheet_name] = frame

    return cleaned, extracted_text


def dataframe_context(dataframes, max_rows=80):
    pieces = []
    for name, frame in dataframes.items():
        pieces.append(
            f"\nSHEET: {name}\n"
            f"ROWS: {len(frame)} | COLUMNS: {list(frame.columns)}\n"
            f"{frame.head(max_rows).to_string(index=False)}"
        )
    return "\n".join(pieces)


def detect_report_type(dataframes, extracted_text=""):
    content = (
        " ".join(
            str(col).lower()
            for frame in dataframes.values()
            for col in frame.columns
        )
        + " "
        + extracted_text[:5000].lower()
    )

    types = []

    patterns = {
        "Laporan Laba Rugi": [
            "revenue", "pendapatan", "gross profit",
            "laba kotor", "ebit", "net income", "laba bersih"
        ],
        "Laporan Posisi Keuangan / Neraca": [
            "total assets", "total aset", "liabilities",
            "liabilitas", "equity", "ekuitas"
        ],
        "Laporan Arus Kas": [
            "cash flow", "arus kas", "operating activities",
            "aktivitas operasi", "investing activities"
        ],
        "Anggaran dan Realisasi": [
            "budget", "anggaran", "actual", "realisasi", "variance"
        ],
        "Jurnal / Buku Besar": [
            "debit", "kredit", "credit", "account code",
            "kode akun", "nomor jurnal"
        ],
        "Data Transaksi": [
            "transaction date", "tanggal transaksi",
            "description", "keterangan", "nominal", "amount"
        ],
        "Aset Tetap": [
            "fixed asset", "aset tetap", "depreciation",
            "penyusutan", "nilai buku"
        ],
        "Perpajakan": [
            "ppn", "pph", "tax payable", "pajak terutang"
        ]
    }

    for report, keywords in patterns.items():
        if any(keyword in content for keyword in keywords):
            types.append(report)

    return types or ["Jenis laporan belum dapat dikenali secara otomatis"]


# =========================================================
# 6. FINANCIAL DATA UTILITIES
# =========================================================

def find_column(df, aliases):
    lookup = {
        re.sub(r"[^a-z0-9]", "", str(col).lower()): col
        for col in df.columns
    }

    for alias in aliases:
        key = re.sub(r"[^a-z0-9]", "", alias.lower())
        if key in lookup:
            return lookup[key]

    for key, original in lookup.items():
        if any(
            re.sub(r"[^a-z0-9]", "", alias.lower()) in key
            for alias in aliases
        ):
            return original

    return None


def numeric_columns(df):
    result = []
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() > 0:
            result.append(col)
    return result


def money(value):
    try:
        return "Rp " + f"{float(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except Exception:
        return "-"


def financial_summary(df):
    numbers = numeric_columns(df)
    result = {
        "rows": len(df),
        "columns": len(df.columns),
        "numeric_columns": numbers,
        "missing_cells": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum())
    }

    for col in numbers:
        values = pd.to_numeric(df[col], errors="coerce")
        result[str(col)] = {
            "total": float(values.sum()),
            "average": float(values.mean()) if values.notna().any() else 0,
            "minimum": float(values.min()) if values.notna().any() else 0,
            "maximum": float(values.max()) if values.notna().any() else 0
        }

    return result


def ratio_analysis(df):
    revenue_col = find_column(
        df, ["revenue", "sales", "pendapatan", "penjualan"]
    )
    net_income_col = find_column(
        df, ["net income", "net profit", "laba bersih"]
    )
    current_assets_col = find_column(
        df, ["current assets", "aset lancar"]
    )
    current_liabilities_col = find_column(
        df, ["current liabilities", "liabilitas lancar", "utang lancar"]
    )
    total_assets_col = find_column(
        df, ["total assets", "total aset"]
    )
    total_liabilities_col = find_column(
        df, ["total liabilities", "total liabilitas", "total utang"]
    )
    equity_col = find_column(
        df, ["total equity", "total ekuitas", "equity"]
    )

    def total(col):
        if col is None:
            return None
        return pd.to_numeric(df[col], errors="coerce").sum()

    metrics = {}

    revenue = total(revenue_col)
    net_income = total(net_income_col)
    current_assets = total(current_assets_col)
    current_liabilities = total(current_liabilities_col)
    total_assets = total(total_assets_col)
    total_liabilities = total(total_liabilities_col)
    equity = total(equity_col)

    if revenue is not None and net_income is not None and revenue != 0:
        metrics["Net Profit Margin (%)"] = net_income / revenue * 100

    if current_assets is not None and current_liabilities not in (None, 0):
        metrics["Current Ratio (x)"] = current_assets / current_liabilities

    if total_liabilities is not None and equity not in (None, 0):
        metrics["Debt to Equity Ratio (x)"] = total_liabilities / equity

    if net_income is not None and total_assets not in (None, 0):
        metrics["Return on Assets (%)"] = net_income / total_assets * 100

    if net_income is not None and equity not in (None, 0):
        metrics["Return on Equity (%)"] = net_income / equity * 100

    return metrics


# =========================================================
# 7. AUDIT ENGINE
# =========================================================

def audit_engine(df):
    data = df.copy()
    findings = []

    def add(category, risk, count, description, recommendation):
        findings.append({
            "Kategori": category,
            "Risiko": risk,
            "Jumlah": int(count),
            "Deskripsi": description,
            "Rekomendasi": recommendation
        })

    missing = int(data.isna().sum().sum())
    duplicates = int(data.duplicated().sum())

    add(
        "Data Kosong",
        "Sedang" if missing else "Rendah",
        missing,
        f"Ditemukan {missing} sel kosong.",
        "Periksa kelengkapan data dengan dokumen sumber."
    )

    add(
        "Duplikasi Baris",
        "Tinggi" if duplicates else "Rendah",
        duplicates,
        f"Ditemukan {duplicates} baris yang identik.",
        "Periksa nomor bukti, tanggal, nominal, dan penerima."
    )

    amount_cols = [
        col for col in numeric_columns(data)
        if any(word in str(col).lower() for word in [
            "amount", "nominal", "jumlah", "debit", "credit",
            "kredit", "budget", "actual", "realisasi", "saldo",
            "revenue", "expense", "nilai"
        ])
    ]

    negative_count = 0
    outlier_count = 0

    for col in amount_cols:
        values = pd.to_numeric(data[col], errors="coerce")
        negative_count += int((values < 0).sum())

        valid = values.dropna()
        if len(valid) >= 4 and valid.nunique() > 1:
            q1 = valid.quantile(.25)
            q3 = valid.quantile(.75)
            iqr = q3 - q1
            if iqr > 0:
                outlier_count += int(
                    ((values < q1 - 1.5 * iqr) |
                     (values > q3 + 1.5 * iqr)).sum()
                )

    add(
        "Nominal Negatif",
        "Sedang" if negative_count else "Rendah",
        negative_count,
        f"Ditemukan {negative_count} nilai negatif.",
        "Periksa apakah nilai merupakan koreksi, retur, atau kesalahan input."
    )

    add(
        "Nilai Ekstrem",
        "Sedang" if outlier_count else "Rendah",
        outlier_count,
        f"Ditemukan {outlier_count} nilai ekstrem berdasarkan metode IQR.",
        "Periksa transaksi ekstrem dan bukti pendukungnya."
    )

    debit_col = find_column(data, ["debit"])
    credit_col = find_column(data, ["credit", "kredit"])

    if debit_col and credit_col:
        debit = pd.to_numeric(data[debit_col], errors="coerce").fillna(0)
        credit = pd.to_numeric(data[credit_col], errors="coerce").fillna(0)
        difference = abs(debit.sum() - credit.sum())

        add(
            "Keseimbangan Debit Kredit",
            "Tinggi" if difference > 0.01 else "Rendah",
            1 if difference > 0.01 else 0,
            f"Selisih total debit dan kredit adalah {difference:,.2f}.",
            "Periksa keseimbangan jurnal per nomor jurnal."
        )

    date_col = find_column(
        data, ["date", "tanggal", "transaction date", "tgl"]
    )
    if date_col:
        original = data[date_col].notna()
        parsed = pd.to_datetime(data[date_col], errors="coerce")
        invalid = int((original & parsed.isna()).sum())
        add(
            "Tanggal Tidak Valid",
            "Sedang" if invalid else "Rendah",
            invalid,
            f"Ditemukan {invalid} tanggal yang tidak dapat dibaca.",
            "Periksa format tanggal dan periode transaksi."
        )

    return data, pd.DataFrame(findings)


# =========================================================
# 8. GEMINI / GROQ AI
# =========================================================

def ask_ai(prompt, provider="Gemini", model=None):
    try:
        if provider == "Gemini":
            if not GEMINI_API_KEY:
                return "GEMINI_API_KEY belum diatur di Streamlit Secrets."
            if genai is None:
                return "Package google-genai belum terpasang."

            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=model or "gemini-2.5-flash",
                contents=(
                    "Kamu adalah FINORA AI, analis laporan keuangan "
                    "dan asisten audit profesional. Jawab dalam bahasa "
                    "Indonesia, jelas, terstruktur, dan berdasarkan data. "
                    "Jangan mengarang angka atau bukti.\n\n" + prompt
                )
            )
            return response.text or "Gemini tidak memberikan jawaban."

        if provider == "Groq":
            if not GROQ_API_KEY:
                return "GROQ_API_KEY belum diatur."
            if Groq is None:
                return "Package groq belum terpasang."

            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model=model or "llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Kamu adalah FINORA AI, analis keuangan "
                            "dan audit profesional. Jawab dalam bahasa Indonesia."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content

    except Exception as error:
        return f"AI mengalami kendala: {error}"

    return "Provider AI tidak dikenali."


def ai_controls(key="ai"):
    provider = st.selectbox(
        "AI Provider",
        ["Gemini", "Groq"],
        key=f"{key}_provider"
    )

    if provider == "Gemini":
        model = st.selectbox(
            "Model Gemini",
            ["gemini-2.5-flash"],
            key=f"{key}_model"
        )
    else:
        model = st.selectbox(
            "Model Groq",
            [
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "openai/gpt-oss-120b"
            ],
            key=f"{key}_model"
        )

    return provider, model


def current_context():
    frames = st.session_state.get("dataframes", {})
    text = st.session_state.get("extracted_text", "")
    return dataframe_context(frames) + "\n\nDOCUMENT TEXT:\n" + text[:12000]


# =========================================================
# 9. DASHBOARD
# =========================================================

def dashboard():
    st.markdown("""
    <div class="finora-header">
        <h1>💗 FINORA AI</h1>
        <p>Financial Intelligence & Audit Platform</p>
    </div>
    """, unsafe_allow_html=True)

    history = query_df(
        "SELECT * FROM analysis_history WHERE username=?",
        (st.session_state.username,)
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Analisis", len(history))
    c2.metric("Dokumen Dianalisis", history["filename"].nunique() if not history.empty else 0)
    c3.metric("AI Assistant", "Gemini" if GEMINI_API_KEY else "Belum dikonfigurasi")

    st.subheader("🚀 Mulai Analisis")
    st.write(
        "Unggah laporan melalui menu Universal Report Analyzer. "
        "Pilih analisis otomatis atau tentukan sendiri fitur yang dibutuhkan."
    )

    if st.session_state.get("dataframes"):
        st.success(
            "Dokumen aktif: " + st.session_state.get("active_filename", "File")
        )
        st.info("Data sudah tersedia untuk digunakan pada modul analisis.")
    else:
        st.info("Belum ada dokumen aktif.")

    st.subheader("Riwayat Analisis Terbaru")
    if history.empty:
        st.caption("Belum ada riwayat analisis.")
    else:
        st.dataframe(
            history.sort_values("created_at", ascending=False).head(10),
            width="stretch",
            hide_index=True
        )


# =========================================================
# 10. UNIVERSAL REPORT ANALYZER
# =========================================================

ANALYSIS_OPTIONS = [
    "Analisis Laba Rugi",
    "Analisis Neraca",
    "Analisis Arus Kas",
    "Analisis Anggaran dan Realisasi",
    "Analisis Rasio Keuangan",
    "Analisis Tren Keuangan",
    "Deteksi Anomali dan Duplikasi",
    "Pemeriksaan Debit dan Kredit",
    "Analisis Aset dan Penyusutan",
    "Analisis Perpajakan",
    "AI Financial Insights",
    "AI Audit Report"
]


def universal_analyzer():
    st.title("📂 Universal Report Analyzer")
    st.write(
        "Unggah satu dokumen, kemudian jalankan analisis otomatis "
        "atau pilih beberapa analisis sesuai kebutuhan."
    )

    uploaded = st.file_uploader(
        "Upload laporan keuangan",
        type=["xlsx", "xls", "csv", "pdf", "png", "jpg", "jpeg"],
        key="universal_upload"
    )

    if uploaded:
        if (
            st.session_state.get("active_filename") != uploaded.name
            or "dataframes" not in st.session_state
        ):
            try:
                frames, extracted_text = read_uploaded_file(uploaded)
                st.session_state.dataframes = frames
                st.session_state.extracted_text = extracted_text
                st.session_state.active_filename = uploaded.name
                st.session_state.analysis_results = {}
                log_activity(f"Upload dokumen {uploaded.name}")
            except Exception as error:
                st.error(f"Gagal membaca dokumen: {error}")
                return

    frames = st.session_state.get("dataframes", {})
    extracted_text = st.session_state.get("extracted_text", "")

    if not frames and not extracted_text:
        st.info("Silakan unggah file untuk memulai analisis.")
        return

    st.success(
        f"Dokumen aktif: {st.session_state.get('active_filename', '-')}"
    )

    if frames:
        sheet_names = list(frames.keys())
        selected_sheet = st.selectbox(
            "Pilih sheet untuk dianalisis",
            sheet_names
        )
        df = frames[selected_sheet]

        st.subheader("Data Preview")
        st.write(f"{len(df):,} baris | {len(df.columns)} kolom")
        st.dataframe(df.head(100), width="stretch")

        detected = detect_report_type(frames, extracted_text)
        st.subheader("Jenis Laporan yang Terdeteksi")
        for item in detected:
            st.write("• " + item)

        st.subheader("Pilih Mode Analisis")
        mode = st.radio(
            "Mode",
            ["Analisis Otomatis", "Analisis Custom"],
            horizontal=True
        )

        if mode == "Analisis Otomatis":
            selected = ANALYSIS_OPTIONS
            st.caption(
                "FINORA akan menjalankan pemeriksaan umum dan analisis "
                "yang relevan dengan kolom yang ditemukan."
            )
        else:
            selected = st.multiselect(
                "Pilih beberapa analisis",
                ANALYSIS_OPTIONS,
                default=["Analisis Rasio Keuangan", "Deteksi Anomali dan Duplikasi"]
            )

        provider, model = ai_controls("universal")

        if st.button("💗 Jalankan Analisis", type="primary"):
            if not selected:
                st.warning("Pilih minimal satu jenis analisis.")
                return

            results = {}
            context = dataframe_context({selected_sheet: df})

            for item in selected:
                if item == "Deteksi Anomali dan Duplikasi":
                    _, findings = audit_engine(df)
                    results[item] = findings

                elif item == "Pemeriksaan Debit dan Kredit":
                    _, findings = audit_engine(df)
                    results[item] = findings[
                        findings["Kategori"].str.contains(
                            "Debit Kredit", case=False
                        )
                    ]

                elif item == "Analisis Rasio Keuangan":
                    results[item] = ratio_analysis(df)

                elif item == "Analisis Tren Keuangan":
                    numbers = numeric_columns(df)
                    results[item] = df[numbers].describe().T if numbers else pd.DataFrame()

                elif item == "Analisis Anggaran dan Realisasi":
                    budget_col = find_column(df, ["budget", "anggaran"])
                    actual_col = find_column(df, ["actual", "realisasi"])
                    if budget_col and actual_col:
                        temp = df.copy()
                        temp["Variance"] = (
                            pd.to_numeric(temp[actual_col], errors="coerce")
                            - pd.to_numeric(temp[budget_col], errors="coerce")
                        )
                        results[item] = temp
                    else:
                        results[item] = "Kolom anggaran dan realisasi tidak ditemukan."

                elif item in [
                    "Analisis Laba Rugi",
                    "Analisis Neraca",
                    "Analisis Arus Kas",
                    "Analisis Aset dan Penyusutan",
                    "Analisis Perpajakan",
                    "AI Financial Insights",
                    "AI Audit Report"
                ]:
                    prompt = f"""
                    Analisis data berikut untuk kebutuhan: {item}.

                    DATA:
                    {context}

                    Instruksi:
                    - Jelaskan hanya informasi yang didukung data.
                    - Sebutkan kolom yang digunakan.
                    - Jangan mengarang nilai yang tidak tersedia.
                    - Jika data tidak cukup, jelaskan keterbatasannya.
                    - Berikan temuan dan rekomendasi yang relevan.
                    - Untuk audit, bedakan indikasi risiko dari bukti fraud.
                    """
                    results[item] = ask_ai(prompt, provider, model)

            st.session_state.analysis_results = results
            st.session_state.analysis_source = selected_sheet

            save_history(
                st.session_state.active_filename,
                ", ".join(selected),
                f"Analisis {len(selected)} modul selesai."
            )
            log_activity("Menjalankan analisis dokumen")
            st.success("Analisis selesai.")

    elif extracted_text:
        st.subheader("Hasil Ekstraksi Dokumen")
        st.text_area(
            "Teks yang berhasil dibaca",
            extracted_text,
            height=300
        )
        provider, model = ai_controls("document_ai")

        if st.button("Analisis Isi Dokumen"):
            prompt = f"""
            Analisis dokumen keuangan berikut:
            {extracted_text[:25000]}

            Identifikasi jenis laporan, informasi penting, risiko,
            keterbatasan data, dan rekomendasi. Jangan mengarang angka.
            """
            with st.spinner("Gemini sedang membaca dokumen..."):
                result = ask_ai(prompt, provider, model)
            st.markdown(result)
            save_history(
                st.session_state.active_filename,
                "Analisis dokumen teks",
                result
            )

    if st.session_state.get("analysis_results"):
        st.divider()
        st.subheader("📊 Hasil Analisis")

        for name, result in st.session_state.analysis_results.items():
            with st.expander(name, expanded=True):
                if isinstance(result, pd.DataFrame):
                    st.dataframe(result, width="stretch")
                elif isinstance(result, dict):
                    st.json(result)
                else:
                    st.markdown(str(result))

        export_analysis_results()


def export_analysis_results():
    results = st.session_state.get("analysis_results", {})
    if not results:
        return

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for index, (name, result) in enumerate(results.items()):
            sheet = re.sub(r"[^A-Za-z0-9 ]", "", name)[:25]
            if isinstance(result, pd.DataFrame):
                result.to_excel(
                    writer,
                    sheet_name=sheet or f"Sheet{index}",
                    index=False
                )
            elif isinstance(result, dict):
                pd.DataFrame(
                    list(result.items()),
                    columns=["Indikator", "Hasil"]
                ).to_excel(
                    writer,
                    sheet_name=sheet or f"Sheet{index}",
                    index=False
                )
            else:
                pd.DataFrame({"Hasil": [str(result)]}).to_excel(
                    writer,
                    sheet_name=sheet or f"Sheet{index}",
                    index=False
                )

    st.download_button(
        "📥 Download Hasil Analisis Excel",
        data=buffer.getvalue(),
        file_name="FINORA_AI_Analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# =========================================================
# 11. INDEPENDENT ANALYSIS MODULES
# =========================================================

def get_active_dataframe():
    frames = st.session_state.get("dataframes", {})
    if not frames:
        return None, None
    names = list(frames.keys())
    name = st.selectbox("Pilih sheet data", names, key="module_sheet")
    return frames[name], name


def financial_statement_analysis():
    st.title("📑 Financial Statement Analysis")
    df, name = get_active_dataframe()
    if df is None:
        st.info("Upload laporan terlebih dahulu di Universal Report Analyzer.")
        return

    st.dataframe(df.head(100), width="stretch")
    provider, model = ai_controls("statement")

    if st.button("Analisis Laporan Keuangan"):
        prompt = f"""
        Analisis laporan keuangan berikut:
        {df.head(150).to_string(index=False)}

        Buat ringkasan, identifikasi pendapatan, beban, laba,
        aset, kewajiban, ekuitas, dan keterbatasan data.
        Jangan menyimpulkan komponen yang tidak tersedia.
        """
        with st.spinner("Menganalisis laporan..."):
            result = ask_ai(prompt, provider, model)
        st.markdown(result)
        save_history(
            st.session_state.active_filename,
            "Financial Statement Analysis",
            result
        )


def ratio_module():
    st.title("📈 Financial Ratio Analysis")
    df, name = get_active_dataframe()
    if df is None:
        st.info("Upload laporan terlebih dahulu.")
        return

    ratios = ratio_analysis(df)
    if not ratios:
        st.warning(
            "Kolom untuk menghitung rasio belum lengkap. "
            "Pastikan data memiliki komponen yang diperlukan."
        )
    else:
        ratio_df = pd.DataFrame(
            list(ratios.items()),
            columns=["Rasio", "Nilai"]
        )
        st.dataframe(ratio_df, width="stretch", hide_index=True)
        fig = px.bar(
            ratio_df,
            x="Rasio",
            y="Nilai",
            title="Financial Ratios"
        )
        st.plotly_chart(fig, width="stretch")

    st.caption(
        "Rasio dihitung hanya jika komponen data tersedia. "
        "Interpretasi perlu mempertimbangkan jenis industri dan periode."
    )


def cashflow_module():
    st.title("💧 Cash Flow Analysis")
    df, name = get_active_dataframe()
    if df is None:
        st.info("Upload data arus kas terlebih dahulu.")
        return

    numbers = numeric_columns(df)
    if not numbers:
        st.warning("Tidak ditemukan kolom numerik.")
        return

    st.dataframe(df.head(100), width="stretch")
    selected = st.selectbox("Pilih kolom nominal", numbers)
    values = pd.to_numeric(df[selected], errors="coerce").dropna()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total", money(values.sum()))
    c2.metric("Rata-rata", money(values.mean()))
    c3.metric("Jumlah data", len(values))

    fig = px.line(
        x=list(range(1, len(values) + 1)),
        y=values,
        labels={"x": "Urutan Data", "y": selected},
        title="Pergerakan Nilai Arus Kas"
    )
    st.plotly_chart(fig, width="stretch")


def budget_module():
    st.title("📊 Budget & Performance Analysis")
    df, name = get_active_dataframe()
    if df is None:
        st.info("Upload data anggaran terlebih dahulu.")
        return

    budget_col = find_column(df, ["budget", "anggaran"])
    actual_col = find_column(df, ["actual", "realisasi"])

    if not budget_col or not actual_col:
        st.warning("Kolom Budget dan Actual/Realisasi belum ditemukan.")
        st.dataframe(df.head(100), width="stretch")
        return

    result = df.copy()
    result[budget_col] = pd.to_numeric(result[budget_col], errors="coerce")
    result[actual_col] = pd.to_numeric(result[actual_col], errors="coerce")
    result["Variance"] = result[actual_col] - result[budget_col]
    result["Variance %"] = (
        result["Variance"] /
        result[budget_col].replace(0, np.nan)
    ) * 100

    st.dataframe(result, width="stretch")

    fig = px.bar(
        result,
        x=find_column(result, ["category", "kategori"]) or result.columns[0],
        y=[budget_col, actual_col],
        barmode="group",
        title="Budget vs Actual"
    )
    st.plotly_chart(fig, width="stretch")


def audit_module():
    st.title("🔍 FINORA AI Audit Center")
    df, name = get_active_dataframe()
    if df is None:
        st.info("Upload data yang ingin diperiksa terlebih dahulu.")
        return

    st.dataframe(df.head(100), width="stretch")

    if st.button("Jalankan Pemeriksaan Audit"):
        audited, findings = audit_engine(df)
        st.session_state.audit_findings = findings
        st.session_state.audit_data = audited
        log_activity("Menjalankan audit data")

    findings = st.session_state.get("audit_findings")
    if findings is not None:
        high = int((findings["Risiko"] == "Tinggi").sum())
        medium = int((findings["Risiko"] == "Sedang").sum())
        low = int((findings["Risiko"] == "Rendah").sum())

        a, b, c = st.columns(3)
        a.metric("Risiko Tinggi", high)
        b.metric("Risiko Sedang", medium)
        c.metric("Risiko Rendah", low)

        st.dataframe(findings, width="stretch")
        fig = px.bar(
            findings,
            x="Kategori",
            y="Jumlah",
            color="Risiko",
            title="Temuan Pemeriksaan"
        )
        st.plotly_chart(fig, width="stretch")

        st.download_button(
            "Download Temuan Audit CSV",
            findings.to_csv(index=False).encode("utf-8"),
            "FINORA_Audit_Findings.csv",
            "text/csv"
        )

        provider, model = ai_controls("audit_module")
        if st.button("Minta Gemini Menjelaskan Temuan"):
            prompt = f"""
            Jelaskan hasil pemeriksaan ini:
            {findings.to_string(index=False)}

            Buat ringkasan risiko, kemungkinan penyebab,
            prosedur tindak lanjut, dan rekomendasi.
            Jangan menyatakan fraud sebagai fakta.
            """
            result = ask_ai(prompt, provider, model)
            st.markdown(result)
            save_history(
                st.session_state.get("active_filename", "Data"),
                "AI Audit",
                result
            )


# =========================================================
# 12. FINANCIAL COPILOT
# =========================================================

def copilot_module():
    st.title("🤖 Financial Copilot AI")
    st.write("Tanyakan apa pun mengenai laporan keuangan yang sedang dianalisis.")

    provider, model = ai_controls("copilot_chat")
    context = current_context()

    if not context.strip():
        st.info(
            "Belum ada data aktif. Kamu tetap dapat bertanya secara umum, "
            "atau upload laporan melalui Universal Report Analyzer."
        )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for item in st.session_state.chat_history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    question = st.chat_input(
        "Contoh: Mengapa EBIT meningkat tetapi arus kas menurun?"
    )

    if question:
        st.session_state.chat_history.append({
            "role": "user",
            "content": question
        })

        prompt = f"""
        KONTEKS LAPORAN PENGGUNA:
        {context[:25000]}

        PERTANYAAN:
        {question}

        Jawab dengan bahasa Indonesia yang mudah dipahami.
        Gunakan angka dari konteks jika tersedia.
        Jika data tidak cukup, jelaskan data apa yang diperlukan.
        Jangan mengarang angka.
        """

        with st.spinner("FINORA AI sedang berpikir..."):
            answer = ask_ai(prompt, provider, model)

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer
        })
        st.rerun()

    if st.button("Reset Chat"):
        st.session_state.chat_history = []
        st.success("Percakapan telah direset.")
        st.rerun()


# =========================================================
# 13. REPORT GENERATOR
# =========================================================

def report_generator():
    st.title("📝 Report Generator")

    results = st.session_state.get("analysis_results", {})
    findings = st.session_state.get("audit_findings")

    if not results and findings is None:
        st.info("Jalankan analisis terlebih dahulu.")
        return

    provider, model = ai_controls("report_writer")

    if st.button("Buat Laporan Analisis dengan AI"):
        prompt = f"""
        Buat laporan analisis keuangan FINORA AI.

        Hasil analisis:
        {str(results)[:15000]}

        Temuan audit:
        {findings.to_string(index=False) if findings is not None else "Tidak tersedia"}

        Struktur:
        1. Judul laporan
        2. Ringkasan eksekutif
        3. Ruang lingkup dan data
        4. Hasil analisis
        5. Temuan dan risiko
        6. Rekomendasi
        7. Keterbatasan
        8. Kesimpulan

        Jangan mengarang angka atau bukti.
        """
        with st.spinner("Menyusun laporan..."):
            report = ask_ai(prompt, provider, model)
        st.session_state.generated_report = report

    report = st.session_state.get("generated_report")
    if report:
        st.markdown(report)
        st.download_button(
            "Download Laporan TXT",
            report.encode("utf-8"),
            "FINORA_Report.txt",
            "text/plain"
        )

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer
            )
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from xml.sax.saxutils import escape

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm
            )
            styles = getSampleStyleSheet()
            story = [
                Paragraph("FINORA AI - LAPORAN ANALISIS", styles["Title"]),
                Spacer(1, 16)
            ]

            for line in report.splitlines():
                if line.strip():
                    story.append(Paragraph(escape(line), styles["BodyText"]))
                    story.append(Spacer(1, 6))

            doc.build(story)

            st.download_button(
                "Download Laporan PDF",
                buffer.getvalue(),
                "FINORA_Report.pdf",
                "application/pdf"
            )
        except ImportError:
            st.caption("Tambahkan reportlab di requirements untuk ekspor PDF.")


# =========================================================
# 14. HISTORY
# =========================================================

def history_module():
    st.title("🗂️ Data History")
    history = query_df("""
        SELECT filename, analysis_type, summary, created_at
        FROM analysis_history
        WHERE username=?
        ORDER BY created_at DESC
    """, (st.session_state.username,))

    if history.empty:
        st.info("Belum ada riwayat.")
    else:
        st.dataframe(history, width="stretch", hide_index=True)
        st.download_button(
            "Download Riwayat CSV",
            history.to_csv(index=False).encode("utf-8"),
            "FINORA_History.csv",
            "text/csv"
        )


# =========================================================
# 15. USER MANAGEMENT
# =========================================================

def user_management():
    st.title("👥 User Management")

    if st.session_state.role != "Admin":
        st.error("Hanya Admin yang dapat mengakses menu ini.")
        return

    with st.form("new_user"):
        full_name = st.text_input("Nama lengkap")
        username = st.text_input("Username baru")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["Finance", "Auditor", "Manager"])
        submit = st.form_submit_button("Buat Pengguna")

        if submit:
            if not full_name or not username or len(password) < 8:
                st.error("Lengkapi data. Password minimal 8 karakter.")
            else:
                try:
                    execute("""
                        INSERT INTO users
                        (username, password, full_name, role, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        username.strip(),
                        hash_password(password),
                        full_name.strip(),
                        role,
                        datetime.now().isoformat()
                    ))
                    st.success("Pengguna berhasil dibuat.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Username sudah digunakan.")

    users = query_df("""
        SELECT id, username, full_name, role, created_at
        FROM users
        ORDER BY id
    """)
    st.subheader("Daftar Pengguna")
    st.dataframe(users, width="stretch", hide_index=True)


def activity_module():
    st.title("📜 Activity Log")
    if st.session_state.role != "Admin":
        st.error("Hanya Admin yang dapat melihat activity log.")
        return

    logs = query_df(
        "SELECT * FROM activity_logs ORDER BY id DESC"
    )
    st.dataframe(logs, width="stretch", hide_index=True)


# =========================================================
# 16. NAVIGATION
# =========================================================

st.sidebar.markdown("""
# 💗 FINORA AI
**Financial Intelligence Platform**
""")

st.sidebar.write(f"Pengguna: **{st.session_state.full_name}**")
st.sidebar.caption(f"Role: {st.session_state.role}")

menu = [
    "Dashboard",
    "Universal Report Analyzer",
    "Financial Statement Analysis",
    "Financial Ratio Analysis",
    "Cash Flow Analysis",
    "Budget & Performance",
    "AI Audit Center",
    "Financial Copilot AI",
    "Report Generator",
    "Data History"
]

if st.session_state.role == "Admin":
    menu += ["User Management", "Activity Log"]

page = st.sidebar.radio("MAIN MENU", menu)

st.sidebar.divider()
st.sidebar.caption(
    "AI Provider: Gemini" if GEMINI_API_KEY else "Gemini API belum dikonfigurasi"
)

if st.sidebar.button("Logout", width="stretch"):
    log_activity("Logout")
    for key in [
        "authenticated", "username", "full_name", "role"
    ]:
        st.session_state.pop(key, None)
    st.rerun()


# =========================================================
# 17. ROUTER
# =========================================================

if page == "Dashboard":
    dashboard()

elif page == "Universal Report Analyzer":
    universal_analyzer()

elif page == "Financial Statement Analysis":
    financial_statement_analysis()

elif page == "Financial Ratio Analysis":
    ratio_module()

elif page == "Cash Flow Analysis":
    cashflow_module()

elif page == "Budget & Performance":
    budget_module()

elif page == "AI Audit Center":
    audit_module()

elif page == "Financial Copilot AI":
    copilot_module()

elif page == "Report Generator":
    report_generator()

elif page == "Data History":
    history_module()

elif page == "User Management":
    user_management()

elif page == "Activity Log":
    activity_module()


# =========================================================
# 18. FOOTER
# =========================================================

st.sidebar.divider()
st.sidebar.caption("FINORA AI © 2026")
st.sidebar.caption("Pink Cream Edition")
