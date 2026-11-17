
import io
import os
import json
import hashlib
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

try:
    from google import genai
except ImportError:
    genai = None

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


# =====================================================
# 1. CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="FINORA AI | Financial Analysis & Audit",
    page_icon="💗",
    layout="wide"
)

def get_secret(name):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name)

GEMINI_API_KEY = get_secret("GEMINI_API_KEY")

# =====================================================
# 2. PINK CREAM THEME
# =====================================================

st.markdown("""
<style>
.stApp {
    background: #FFF9F6;
    color: #51404A;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#F8E3E9,#FFF2E9);
    border-right: 1px solid #EBD0D8;
}
[data-testid="stSidebar"] * {
    color: #714B5D;
}
h1,h2,h3 {
    color: #A64F78 !important;
}
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #F0D6DE;
    padding: 16px;
    border-radius: 14px;
}
[data-testid="stMetricValue"] {
    color: #B65C85;
}
.stButton > button {
    background: #C66D91;
    color: white;
    border: none;
    border-radius: 9px;
}
.stButton > button:hover {
    background: #A94F78;
    color: white;
}
.finora-header {
    background: linear-gradient(110deg,#F7DCE6,#FFF0E6);
    padding: 25px;
    border: 1px solid #EBCBD7;
    border-radius: 16px;
    margin-bottom: 20px;
}
.finora-header h1 {
    color: #A64F78 !important;
    margin-bottom: 5px;
}
.finora-header p {
    color: #805B6C;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="finora-header">
    <h1>💗 FINORA AI</h1>
    <p>Financial Statement Analysis & Audit Intelligence</p>
    <p>Upload once. Analyze smarter. Audit deeper.</p>
</div>
""", unsafe_allow_html=True)


# =====================================================
# 3. SESSION STATE
# =====================================================

defaults = {
    "finora_data": {},
    "finora_results": {},
    "finora_file_name": None,
    "finora_ai_chat": [],
    "finora_report": ""
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =====================================================
# 4. FILE READER
# =====================================================

def read_uploaded_file(uploaded):
    name = uploaded.name.lower()
    raw = uploaded.getvalue()

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(
            io.BytesIO(raw),
            sheet_name=None
        )

    if name.endswith(".csv"):
        return {
            "Data": pd.read_csv(io.BytesIO(raw))
        }

    if name.endswith(".pdf"):
        if fitz is None:
            raise ValueError("Package PyMuPDF belum terpasang.")

        doc = fitz.open(stream=raw, filetype="pdf")
        pages = []

        for page_number, page in enumerate(doc, start=1):
            text = page.get_text("text")
            pages.append({
                "Halaman": page_number,
                "Isi": text
            })

        return {
            "Teks PDF": pd.DataFrame(pages)
        }

    if name.endswith((".png", ".jpg", ".jpeg")):
        if Image is None or pytesseract is None:
            raise ValueError(
                "Pembacaan gambar memerlukan Pillow, pytesseract, "
                "dan Tesseract OCR engine."
            )

        image = Image.open(io.BytesIO(raw))
        text = pytesseract.image_to_string(image, lang="eng")
        return {
            "Hasil OCR": pd.DataFrame({"Isi": [text]})
        }

    raise ValueError("Format file belum didukung.")


def get_numeric_columns(df):
    result = []

    for col in df.columns:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().sum() > 0:
            result.append(col)

    return result


def clean_dataframe(df):
    data = df.copy()
    data.columns = [
        str(c).strip().replace("\n", " ")
        for c in data.columns
    ]
    return data


# =====================================================
# 5. GENERAL DATA ANALYSIS
# =====================================================

def profile_data(df):
    data = clean_dataframe(df)

    numeric_cols = get_numeric_columns(data)
    missing = int(data.isna().sum().sum())
    duplicates = int(data.duplicated().sum())

    result = {
        "rows": len(data),
        "columns": len(data.columns),
        "numeric_columns": numeric_cols,
        "missing": missing,
        "duplicates": duplicates,
        "column_names": list(data.columns)
    }

    return result


def analyze_numeric_data(df):
    data = clean_dataframe(df)
    numeric_cols = get_numeric_columns(data)

    if not numeric_cols:
        return pd.DataFrame()

    numeric = data[numeric_cols].apply(
        pd.to_numeric, errors="coerce"
    )

    summary = numeric.describe().T.reset_index()
    summary = summary.rename(columns={"index": "Nama Kolom"})
    return summary


# =====================================================
# 6. FINANCIAL STATEMENT ANALYSIS
# =====================================================

def detect_financial_columns(df):
    columns = [str(c).lower().strip() for c in df.columns]

    mapping = {
        "revenue": ["revenue", "sales", "pendapatan", "penjualan"],
        "expense": ["expense", "beban", "biaya", "opex"],
        "asset": ["asset", "aset", "total assets", "total aset"],
        "liability": ["liability", "liabilitas", "utang", "kewajiban"],
        "equity": ["equity", "ekuitas", "modal"],
        "cash": ["cash", "kas", "bank", "cash and cash equivalents"],
        "current_asset": ["current assets", "aset lancar"],
        "current_liability": ["current liabilities", "liabilitas lancar"],
        "cogs": ["cogs", "cost of goods sold", "hpp"],
        "ebit": ["ebit", "operating profit", "laba operasi"],
        "net_income": ["net income", "laba bersih", "profit after tax"]
    }

    detected = {}

    for key, keywords in mapping.items():
        for col in df.columns:
            if str(col).lower().strip() in keywords:
                detected[key] = col
                break

    return detected


def financial_summary(df):
    detected = detect_financial_columns(df)
    data = clean_dataframe(df)

    result = []

    for key, column in detected.items():
        values = pd.to_numeric(data[column], errors="coerce")
        result.append({
            "Komponen": key.replace("_", " ").title(),
            "Kolom": column,
            "Total": values.sum()
        })

    return pd.DataFrame(result), detected


def ratio_analysis(df):
    data = clean_dataframe(df)
    _, detected = financial_summary(data)

    values = {}

    for key, col in detected.items():
        numeric = pd.to_numeric(data[col], errors="coerce")
        values[key] = numeric.sum()

    ratios = []

    if "current_asset" in values and "current_liability" in values:
        denominator = values["current_liability"]
        if denominator != 0:
            ratios.append({
                "Rasio": "Current Ratio",
                "Nilai": values["current_asset"] / denominator,
                "Interpretasi": "Aset lancar dibandingkan liabilitas lancar"
            })

    if "liability" in values and "asset" in values:
        if values["asset"] != 0:
            ratios.append({
                "Rasio": "Debt to Asset Ratio",
                "Nilai": values["liability"] / values["asset"],
                "Interpretasi": "Proporsi aset yang dibiayai liabilitas"
            })

    if "net_income" in values and "revenue" in values:
        if values["revenue"] != 0:
            ratios.append({
                "Rasio": "Net Profit Margin",
                "Nilai": values["net_income"] / values["revenue"],
                "Interpretasi": "Laba bersih dibandingkan pendapatan"
            })

    if "net_income" in values and "equity" in values:
        if values["equity"] != 0:
            ratios.append({
                "Rasio": "Return on Equity",
                "Nilai": values["net_income"] / values["equity"],
                "Interpretasi": "Laba bersih dibandingkan ekuitas"
            })

    return pd.DataFrame(ratios)


# =====================================================
# 7. BUDGET VS ACTUAL
# =====================================================

def budget_analysis(df):
    data = clean_dataframe(df)

    normalized = {
        str(c).lower().strip(): c
        for c in data.columns
    }

    budget_col = normalized.get("budget")
    actual_col = normalized.get("actual")

    if not budget_col or not actual_col:
        return None

    data[budget_col] = pd.to_numeric(
        data[budget_col], errors="coerce"
    )
    data[actual_col] = pd.to_numeric(
        data[actual_col], errors="coerce"
    )

    data["Variance"] = data[actual_col] - data[budget_col]

    data["Variance %"] = (
        data["Variance"] /
        data[budget_col].replace(0, np.nan)
    ) * 100

    return data


# =====================================================
# 8. AUDIT ENGINE
# =====================================================

def audit_analysis(df):
    data = clean_dataframe(df)
    findings = []

    def add(category, count, risk, description, recommendation):
        findings.append({
            "Temuan": category,
            "Jumlah": int(count),
            "Risiko": risk,
            "Keterangan": description,
            "Rekomendasi": recommendation
        })

    missing = int(data.isna().sum().sum())
    add(
        "Data Kosong",
        missing,
        "Sedang" if missing else "Rendah",
        "Jumlah sel yang tidak memiliki data.",
        "Periksa kelengkapan dokumen sumber."
    )

    duplicates = int(data.duplicated().sum())
    add(
        "Baris Duplikat",
        duplicates,
        "Tinggi" if duplicates else "Rendah",
        "Baris yang memiliki isi sama persis.",
        "Periksa nomor dokumen, tanggal, dan nominal."
    )

    numeric_cols = get_numeric_columns(data)
    outlier_count = 0

    for col in numeric_cols:
        values = pd.to_numeric(data[col], errors="coerce")
        valid = values.dropna()

        if len(valid) < 4 or valid.nunique() < 2:
            continue

        q1 = valid.quantile(.25)
        q3 = valid.quantile(.75)
        iqr = q3 - q1

        if iqr > 0:
            low = q1 - 1.5 * iqr
            high = q3 + 1.5 * iqr
            outlier_count += int(
                ((values < low) | (values > high)).sum()
            )

    add(
        "Nilai Tidak Wajar",
        outlier_count,
        "Sedang" if outlier_count else "Rendah",
        "Nilai ekstrem berdasarkan metode IQR.",
        "Cocokkan nilai ekstrem dengan dokumen pendukung."
    )

    date_cols = [
        c for c in data.columns
        if any(x in str(c).lower() for x in [
            "tanggal", "date", "tgl"
        ])
    ]

    invalid_dates = 0

    for col in date_cols:
        original = data[col].notna()
        parsed = pd.to_datetime(data[col], errors="coerce")
        invalid_dates += int((original & parsed.isna()).sum())

    add(
        "Tanggal Tidak Valid",
        invalid_dates,
        "Sedang" if invalid_dates else "Rendah",
        "Tanggal yang gagal dibaca sebagai tanggal.",
        "Periksa format tanggal dan periode transaksi."
    )

    normalized = {
        str(c).lower().strip(): c
        for c in data.columns
    }

    debit_col = normalized.get("debit")
    credit_col = normalized.get("credit") or normalized.get("kredit")

    if debit_col and credit_col:
        debit = pd.to_numeric(
            data[debit_col], errors="coerce"
        ).fillna(0).sum()

        credit = pd.to_numeric(
            data[credit_col], errors="coerce"
        ).fillna(0).sum()

        difference = abs(debit - credit)

        add(
            "Keseimbangan Debit Kredit",
            1 if difference > 0.01 else 0,
            "Tinggi" if difference > 0.01 else "Rendah",
            f"Selisih debit dan kredit: {difference:,.2f}",
            "Periksa jurnal dan keseimbangannya."
        )

    return pd.DataFrame(findings)


# =====================================================
# 9. GEMINI AI
# =====================================================

def ask_gemini(prompt):
    if not GEMINI_API_KEY:
        return "API Gemini belum diatur di Streamlit Secrets."

    if genai is None:
        return "Package google-genai belum terpasang."

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text or "AI tidak memberikan jawaban."

    except Exception as error:
        return f"Gemini Error: {error}"


def ai_analyze(df, analysis_type):
    sample = df.head(30).to_string(index=False)

    prompt = f"""
Kamu adalah FINORA AI, asisten analisis laporan keuangan dan audit.

Jenis analisis:
{analysis_type}

Data:
{sample}

Instruksi:
1. Buat ringkasan eksekutif.
2. Jelaskan angka dan pola yang terlihat.
3. Identifikasi indikasi risiko.
4. Jelaskan keterbatasan data.
5. Berikan rekomendasi yang dapat ditindaklanjuti.
6. Jangan mengarang angka yang tidak tersedia.
7. Jangan menyatakan fraud sebagai fakta.
8. Gunakan bahasa Indonesia profesional dan mudah dipahami.

Jika informasi tidak tersedia, nyatakan secara terbuka.
"""

    return ask_gemini(prompt)


# =====================================================
# 10. FILE UPLOAD CENTER
# =====================================================

def upload_center():
    st.title("📂 Upload Laporan")

    st.write(
        "Unggah laporan keuangan. FINORA akan membaca sheet "
        "dan menampilkan data yang berhasil dikenali."
    )

    uploaded = st.file_uploader(
        "Upload Excel, CSV, PDF, atau gambar",
        type=["xlsx", "xls", "csv", "pdf", "png", "jpg", "jpeg"],
        key="main_upload"
    )

    if uploaded:
        try:
            data = read_uploaded_file(uploaded)

            st.session_state.finora_data = {
                name: clean_dataframe(df)
                for name, df in data.items()
            }

            st.session_state.finora_file_name = uploaded.name
            st.session_state.finora_results = {}

            st.success("File berhasil dibaca.")

        except Exception as error:
            st.error(f"Gagal membaca file: {error}")

    if st.session_state.finora_data:
        st.subheader("📑 Sheet / Bagian yang Terbaca")

        for name, df in st.session_state.finora_data.items():
            with st.expander(f"📄 {name} — {len(df)} baris"):
                st.dataframe(df.head(100), width="stretch")


# =====================================================
# 11. AUTOMATIC ANALYSIS
# =====================================================

def automatic_analysis():
    st.title("⚡ Analisis Laporan Otomatis")

    if not st.session_state.finora_data:
        st.info("Unggah file terlebih dahulu melalui menu Upload Laporan.")
        return

    for sheet_name, df in st.session_state.finora_data.items():
        st.subheader(f"📄 {sheet_name}")

        profile = profile_data(df)

        a, b, c, d = st.columns(4)
        a.metric("Baris", profile["rows"])
        b.metric("Kolom", profile["columns"])
        c.metric("Data Kosong", profile["missing"])
        d.metric("Duplikat", profile["duplicates"])

        st.write("Analisis statistik")
        summary = analyze_numeric_data(df)

        if not summary.empty:
            st.dataframe(summary, width="stretch")

        st.write("Analisis laporan keuangan")
        financial, detected = financial_summary(df)

        if not financial.empty:
            st.dataframe(financial, width="stretch")
        else:
            st.caption("Belum ditemukan kolom keuangan yang dikenali.")

        st.write("Analisis rasio")
        ratios = ratio_analysis(df)

        if not ratios.empty:
            st.dataframe(ratios, width="stretch")

        budget = budget_analysis(df)

        if budget is not None:
            st.write("Budget vs Actual")
            st.dataframe(budget, width="stretch")

        st.write("Pemeriksaan audit")
        findings = audit_analysis(df)
        st.dataframe(findings, width="stretch")

        with st.expander("🤖 Analisis dan rekomendasi Gemini"):
            if st.button(
                f"Analisis AI: {sheet_name}",
                key=f"auto_ai_{sheet_name}"
            ):
                with st.spinner("Gemini sedang menganalisis..."):
                    result = ai_analyze(df, "Analisis otomatis seluruh laporan")

                st.session_state.finora_results[
                    f"AI_{sheet_name}"
                ] = result

            result = st.session_state.finora_results.get(
                f"AI_{sheet_name}"
            )

            if result:
                st.markdown(result)


# =====================================================
# 12. CUSTOM ANALYSIS
# =====================================================

def custom_analysis():
    st.title("🎛️ Custom Analysis")

    st.write(
        "Pilih beberapa pemeriksaan sekaligus. "
        "Satu file dapat digunakan untuk beberapa analisis."
    )

    if not st.session_state.finora_data:
        st.info("Unggah file terlebih dahulu.")
        return

    sheet_name = st.selectbox(
        "Pilih sheet atau bagian laporan",
        list(st.session_state.finora_data.keys())
    )

    df = st.session_state.finora_data[sheet_name]

    st.subheader("Pilih analisis yang diinginkan")

    options = {
        "Profil dan kelengkapan data": "profile",
        "Analisis statistik angka": "statistics",
        "Analisis laporan keuangan": "financial",
        "Analisis rasio keuangan": "ratios",
        "Analisis perbandingan Budget vs Actual": "budget",
        "Deteksi anomali dan audit": "audit",
        "Analisis tren": "trend",
        "Analisis AI Gemini": "ai"
    }

    selected = []

    for label, key in options.items():
        if st.checkbox(label, key=f"custom_{key}"):
            selected.append(key)

    if st.button("🚀 Jalankan Analisis Pilihan", type="primary"):
        if not selected:
            st.warning("Pilih minimal satu jenis analisis.")
            return

        results = {}

        for key in selected:
            if key == "profile":
                results[key] = profile_data(df)

            elif key == "statistics":
                results[key] = analyze_numeric_data(df)

            elif key == "financial":
                results[key] = financial_summary(df)[0]

            elif key == "ratios":
                results[key] = ratio_analysis(df)

            elif key == "budget":
                results[key] = budget_analysis(df)

            elif key == "audit":
                results[key] = audit_analysis(df)

            elif key == "trend":
                numeric = get_numeric_columns(df)
                results[key] = df[numeric].describe().T if numeric else None

            elif key == "ai":
                with st.spinner("Gemini sedang menganalisis..."):
                    results[key] = ai_analyze(
                        df,
                        "Analisis custom sesuai data yang tersedia"
                    )

        st.session_state.finora_results["custom"] = results

    results = st.session_state.finora_results.get("custom", {})

    for key, value in results.items():
        st.divider()
        st.subheader(key.replace("_", " ").title())

        if isinstance(value, pd.DataFrame):
            if value is not None and not value.empty:
                st.dataframe(value, width="stretch")
            else:
                st.info("Tidak ada hasil atau kolom yang sesuai.")

        elif isinstance(value, dict):
            st.json(value)

        elif isinstance(value, str):
            st.markdown(value)


# =====================================================
# 13. FINANCIAL ANALYSIS
# =====================================================

def financial_analysis():
    st.title("📊 Financial Statement Analysis")

    if not st.session_state.finora_data:
        st.info("Unggah laporan terlebih dahulu.")
        return

    sheet = st.selectbox(
        "Pilih laporan",
        list(st.session_state.finora_data.keys()),
        key="financial_sheet"
    )

    df = st.session_state.finora_data[sheet]

    summary, detected = financial_summary(df)

    if summary.empty:
        st.warning(
            "FINORA belum menemukan kolom laporan keuangan "
            "yang dikenali. Periksa nama kolom atau struktur file."
        )
        st.write("Kolom yang tersedia:", list(df.columns))
        return

    st.subheader("Komponen Keuangan yang Dikenali")
    st.dataframe(summary, width="stretch")

    ratios = ratio_analysis(df)

    st.subheader("Financial Ratios")

    if ratios.empty:
        st.info(
            "Data belum cukup untuk menghitung rasio keuangan."
        )
    else:
        st.dataframe(ratios, width="stretch")

    numeric = get_numeric_columns(df)

    if numeric:
        selected_col = st.selectbox(
            "Pilih komponen untuk grafik",
            numeric
        )

        chart = pd.DataFrame({
            "Baris": range(1, len(df) + 1),
            "Nilai": pd.to_numeric(
                df[selected_col], errors="coerce"
            )
        })

        fig = px.line(
            chart,
            x="Baris",
            y="Nilai",
            markers=True,
            title=f"Tren {selected_col}"
        )

        st.plotly_chart(fig, width="stretch")


# =====================================================
# 14. AUDIT CENTER
# =====================================================

def audit_center():
    st.title("🔍 AI Audit & Risk Detection")

    if not st.session_state.finora_data:
        st.info("Unggah laporan terlebih dahulu.")
        return

    sheet = st.selectbox(
        "Pilih data untuk audit",
        list(st.session_state.finora_data.keys()),
        key="audit_sheet"
    )

    df = st.session_state.finora_data[sheet]

    if st.button("🔎 Jalankan Pemeriksaan Audit"):
        st.session_state.finora_results["audit_current"] = audit_analysis(df)

    findings = st.session_state.finora_results.get("audit_current")

    if findings is not None:
        st.dataframe(findings, width="stretch")

        risk = findings.groupby("Risiko").size().reset_index(name="Jumlah")

        fig = px.bar(
            risk,
            x="Risiko",
            y="Jumlah",
            color="Risiko",
            title="Ringkasan Indikasi Risiko"
        )

        st.plotly_chart(fig, width="stretch")

        st.warning(
            "Temuan otomatis merupakan indikator untuk ditindaklanjuti, "
            "bukan bukti kecurangan atau fraud."
        )

        if st.button("Minta Gemini Menjelaskan Temuan"):
            prompt = f"""
            Jelaskan hasil pemeriksaan audit berikut:
            {findings.to_string(index=False)}

            Berikan prioritas pemeriksaan dan rekomendasi.
            Jangan menyatakan fraud sebagai fakta.
            """
            with st.spinner("Gemini menganalisis temuan..."):
                st.session_state.finora_results["audit_ai"] = ask_gemini(prompt)

        if st.session_state.finora_results.get("audit_ai"):
            st.markdown(st.session_state.finora_results["audit_ai"])


# =====================================================
# 15. AI FINANCIAL ASSISTANT
# =====================================================

def ai_assistant():
    st.title("💬 FINORA AI Assistant")

    if not st.session_state.finora_data:
        st.info("Unggah laporan terlebih dahulu agar AI memiliki konteks data.")
        return

    sheet = st.selectbox(
        "Gunakan data dari",
        list(st.session_state.finora_data.keys()),
        key="chat_sheet"
    )

    df = st.session_state.finora_data[sheet]

    for item in st.session_state.finora_ai_chat:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    question = st.chat_input(
        "Tanyakan tentang laporan, rasio, risiko, EBIT, arus kas..."
    )

    if question:
        st.session_state.finora_ai_chat.append({
            "role": "user",
            "content": question
        })

        prompt = f"""
        Kamu adalah FINORA AI, asisten analisis laporan keuangan.

        Data laporan:
        {df.head(40).to_string(index=False)}

        Pertanyaan pengguna:
        {question}

        Jawab dalam bahasa Indonesia.
        Gunakan data yang tersedia.
        Jangan mengarang angka.
        Jelaskan jika data tidak cukup.
        """

        with st.spinner("FINORA AI sedang menjawab..."):
            answer = ask_gemini(prompt)

        st.session_state.finora_ai_chat.append({
            "role": "assistant",
            "content": answer
        })

        st.rerun()

    if st.button("Reset Chat"):
        st.session_state.finora_ai_chat = []
        st.rerun()


# =====================================================
# 16. REPORT GENERATOR
# =====================================================

def report_generator():
    st.title("📑 Report Generator")

    if not st.session_state.finora_data:
        st.info("Belum ada laporan yang diunggah.")
        return

    sheet = st.selectbox(
        "Pilih laporan untuk dibuatkan hasil",
        list(st.session_state.finora_data.keys()),
        key="report_sheet"
    )

    df = st.session_state.finora_data[sheet]

    profile = profile_data(df)
    financial, _ = financial_summary(df)
    ratios = ratio_analysis(df)
    findings = audit_analysis(df)

    st.subheader("Preview hasil")

    st.write("Profil data")
    st.json(profile)

    st.write("Komponen keuangan")
    st.dataframe(financial, width="stretch")

    st.write("Rasio")
    st.dataframe(ratios, width="stretch")

    st.write("Temuan audit")
    st.dataframe(findings, width="stretch")

    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data Sumber", index=False)
        financial.to_excel(writer, sheet_name="Financial Analysis", index=False)
        ratios.to_excel(writer, sheet_name="Financial Ratios", index=False)
        findings.to_excel(writer, sheet_name="Audit Findings", index=False)

    st.download_button(
        "📥 Download Laporan Analisis Excel",
        data=buffer.getvalue(),
        file_name="FINORA_Analysis_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    text_report = f"""
FINORA AI - FINANCIAL ANALYSIS & AUDIT REPORT
Tanggal: {datetime.now().strftime("%d-%m-%Y %H:%M")}
File: {st.session_state.finora_file_name}
Bagian: {sheet}

PROFIL DATA
{json.dumps(profile, indent=2, ensure_ascii=False)}

FINANCIAL ANALYSIS
{financial.to_string(index=False)}

FINANCIAL RATIOS
{ratios.to_string(index=False)}

AUDIT FINDINGS
{findings.to_string(index=False)}

Catatan:
Hasil pemeriksaan otomatis perlu diverifikasi dengan dokumen sumber.
Indikasi risiko bukan bukti fraud.
"""

    st.download_button(
        "📄 Download Laporan TXT",
        data=text_report.encode("utf-8"),
        file_name="FINORA_Report.txt",
        mime="text/plain"
    )


# =====================================================
# 17. HISTORY / RESET
# =====================================================

def history_page():
    st.title("🕘 Riwayat Sesi")

    st.write("File aktif:", st.session_state.finora_file_name or "Belum ada")

    if st.button("Hapus Data Sesi"):
        st.session_state.finora_data = {}
        st.session_state.finora_results = {}
        st.session_state.finora_file_name = None
        st.session_state.finora_ai_chat = []
        st.rerun()


# =====================================================
# 18. NAVIGATION
# =====================================================

st.sidebar.markdown("## 💗 FINORA AI")
st.sidebar.caption("Financial Analysis & Audit Intelligence")

menu = st.sidebar.radio(
    "MENU UTAMA",
    [
        "Dashboard",
        "Upload Laporan",
        "Analisis Otomatis",
        "Custom Analysis",
        "Financial Statement Analysis",
        "AI Audit Center",
        "AI Financial Assistant",
        "Report Generator",
        "Riwayat Sesi"
    ]
)

if st.sidebar.button("Reset Seluruh Sesi"):
    for key in defaults:
        st.session_state[key] = defaults[key]
    st.rerun()

st.sidebar.divider()
st.sidebar.caption("FINORA AI © 2026")
st.sidebar.caption("Pink Cream Edition")

# =====================================================
# 19. PAGE ROUTER
# =====================================================

if menu == "Dashboard":
    st.title("💗 Dashboard Analisis")

    if not st.session_state.finora_data:
        st.info("Mulai dengan mengunggah laporan keuangan.")
    else:
        st.success(
            f"File aktif: {st.session_state.finora_file_name}"
        )

        sheets = st.session_state.finora_data

        total_rows = sum(len(df) for df in sheets.values())
        total_sheets = len(sheets)

        a, b = st.columns(2)
        a.metric("Bagian / Sheet", total_sheets)
        b.metric("Total Baris", total_rows)

        for name, df in sheets.items():
            st.write(f"**{name}** — {len(df)} baris, {len(df.columns)} kolom")

elif menu == "Upload Laporan":
    upload_center()

elif menu == "Analisis Otomatis":
    automatic_analysis()

elif menu == "Custom Analysis":
    custom_analysis()

elif menu == "Financial Statement Analysis":
    financial_analysis()

elif menu == "AI Audit Center":
    audit_center()

elif menu == "AI Financial Assistant":
    ai_assistant()

elif menu == "Report Generator":
    report_generator()

elif menu == "Riwayat Sesi":
    history_page()
