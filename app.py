
import io
import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# FINORA AI - FINANCIAL ANALYSIS & AUDIT INTELLIGENCE
# =========================================================

st.set_page_config(
    page_title="FINORA AI | Financial Analysis & Audit",
    page_icon="💗",
    layout="wide",
    initial_sidebar_state="expanded"
)

PINK = "#FF5C8B"
CREAM = "#FFF8F5"
DARK = "#71384F"
SOFT_PINK = "#FCE2EA"
WHITE = "#FFFFFF"

# ------------------------- DESIGN -------------------------

st.markdown(f"""
<style>
.stApp {{
    background: {CREAM};
}}
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #FCE2EA 0%, #FFF4F0 100%);
    border-right: 1px solid #F3CAD8;
}}
h1, h2, h3 {{
    color: {DARK};
}}
p, label, span {{
    color: #573D49;
}}
.stButton > button {{
    background: {PINK};
    color: white;
    border: none;
    border-radius: 10px;
    font-weight: 600;
}}
.stButton > button:hover {{
    background: #E94B7B;
    color: white;
    border: none;
}}
div[data-testid="stMetric"] {{
    background: white;
    border: 1px solid #F3D6E0;
    padding: 15px;
    border-radius: 13px;
}}
div[data-testid="stFileUploader"] {{
    background: white;
    border: 1px dashed #E9A9BF;
    border-radius: 12px;
    padding: 12px;
}}
</style>
""", unsafe_allow_html=True)


# ------------------------- SESSION -------------------------

if "analysis_history" not in st.session_state:
    st.session_state.analysis_history = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "last_dataframe" not in st.session_state:
    st.session_state.last_dataframe = None

if "last_filename" not in st.session_state:
    st.session_state.last_filename = ""


# ------------------------- FILE READER -------------------------

def read_uploaded_file(uploaded_file):
    """Membaca Excel, CSV, dan beberapa format teks."""
    if uploaded_file is None:
        return None, None

    filename = uploaded_file.name.lower()

    try:
        if filename.endswith((".xlsx", ".xls")):
            workbook = pd.ExcelFile(uploaded_file)
            sheets = {
                sheet: pd.read_excel(workbook, sheet_name=sheet)
                for sheet in workbook.sheet_names
            }
            return sheets, "excel"

        if filename.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            return {"Data": df}, "csv"

        if filename.endswith((".txt", ".tsv")):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
            return {"Data": df}, "text"

        st.error("Format file belum didukung. Gunakan Excel atau CSV.")
        return None, None

    except Exception as e:
        st.error(f"File gagal dibaca: {e}")
        return None, None


def clean_dataframe(df):
    """Membersihkan nama kolom dan mencoba mengubah angka."""
    data = df.copy()
    data.columns = [
        str(col).strip() if str(col).strip() else f"Kolom_{i+1}"
        for i, col in enumerate(data.columns)
    ]

    for col in data.columns:
        if data[col].dtype == "object":
            cleaned = (
                data[col].astype(str)
                .str.replace("Rp", "", regex=False)
                .str.replace("IDR", "", regex=False)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.replace("%", "", regex=False)
                .str.strip()
            )
            converted = pd.to_numeric(cleaned, errors="coerce")

            if converted.notna().sum() >= max(2, int(len(data) * 0.5)):
                data[col] = converted

    return data


def numeric_columns(df):
    return df.select_dtypes(include=np.number).columns.tolist()


def choose_column(label, columns, key):
    options = ["-- Pilih kolom --"] + list(columns)
    selected = st.selectbox(label, options, key=key)
    return None if selected == "-- Pilih kolom --" else selected


def money(value):
    try:
        return f"{value:,.2f}"
    except Exception:
        return str(value)


# ------------------------- GEMINI AI -------------------------

def get_gemini_key():
    try:
        return st.secrets.get("GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    except Exception:
        return os.getenv("GEMINI_API_KEY", "")


def ask_gemini(prompt):
    api_key = get_gemini_key()

    if not api_key:
        return (
            "Gemini belum terhubung. Tambahkan GEMINI_API_KEY "
            "pada Streamlit Settings → Secrets."
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text or "Gemini tidak memberikan jawaban."

    except Exception as e:
        return f"Gemini gagal memproses permintaan: {e}"


def dataframe_context(df, filename):
    preview = df.head(25).to_string(index=False)
    return f"""
Nama file: {filename}
Jumlah baris: {len(df)}
Jumlah kolom: {len(df.columns)}
Nama kolom: {list(df.columns)}

Cuplikan data (maksimal 25 baris):
{preview}
"""


# ------------------------- ANALYSIS FUNCTIONS -------------------------

def financial_statement_analysis(df):
    st.subheader("📑 Financial Statement Analysis")

    st.write("Ringkasan struktur data dan nilai keuangan yang ditemukan.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Jumlah Baris", len(df))
    c2.metric("Jumlah Kolom", len(df.columns))
    c3.metric("Kolom Numerik", len(numeric_columns(df)))

    nums = numeric_columns(df)

    if nums:
        summary = df[nums].describe().T.reset_index()
        summary = summary.rename(columns={"index": "Nama Akun"})
        st.markdown("#### Ringkasan angka")
        st.dataframe(summary, use_container_width=True)

        selected = st.selectbox(
            "Pilih kolom untuk melihat grafik",
            nums,
            key="statement_chart"
        )

        chart_data = df[[selected]].dropna().reset_index()
        chart_data.columns = ["Urutan Data", "Nilai"]

        fig = px.line(
            chart_data,
            x="Urutan Data",
            y="Nilai",
            title=f"Pergerakan {selected}",
            markers=True
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Tidak ditemukan kolom numerik pada data ini.")

    st.caption(
        "Analisis ini merangkum data yang tersedia. "
        "Identifikasi akun dan interpretasi laporan tetap perlu diperiksa."
    )


def ratio_analysis(df):
    st.subheader("📊 Financial Ratio Analysis")
    nums = numeric_columns(df)

    if not nums:
        st.warning("File belum memiliki kolom angka yang dapat dihitung.")
        return

    st.write("Pilih kolom akun yang sesuai dengan laporan keuangan.")

    col1, col2 = st.columns(2)

    with col1:
        current_assets = choose_column(
            "Aset Lancar", nums, "ratio_current_assets"
        )
        inventory = choose_column(
            "Persediaan", nums, "ratio_inventory"
        )
        total_assets = choose_column(
            "Total Aset", nums, "ratio_total_assets"
        )
        revenue = choose_column(
            "Pendapatan/Penjualan", nums, "ratio_revenue"
        )

    with col2:
        current_liabilities = choose_column(
            "Liabilitas Lancar", nums, "ratio_current_liabilities"
        )
        total_liabilities = choose_column(
            "Total Liabilitas", nums, "ratio_total_liabilities"
        )
        equity = choose_column(
            "Total Ekuitas", nums, "ratio_equity"
        )
        net_income = choose_column(
            "Laba Bersih", nums, "ratio_net_income"
        )

    def last_value(column):
        if column:
            values = pd.to_numeric(df[column], errors="coerce").dropna()
            if not values.empty:
                return float(values.iloc[-1])
        return None

    ratios = {}

    ca = last_value(current_assets)
    cl = last_value(current_liabilities)
    inv = last_value(inventory)
    ta = last_value(total_assets)
    tl = last_value(total_liabilities)
    eq = last_value(equity)
    rev = last_value(revenue)
    ni = last_value(net_income)

    if ca is not None and cl not in (None, 0):
        ratios["Current Ratio"] = ca / cl

    if ca is not None and inv is not None and cl not in (None, 0):
        ratios["Quick Ratio"] = (ca - inv) / cl

    if tl is not None and eq not in (None, 0):
        ratios["Debt to Equity Ratio"] = tl / eq

    if tl is not None and ta not in (None, 0):
        ratios["Debt to Asset Ratio"] = tl / ta

    if ni is not None and rev not in (None, 0):
        ratios["Net Profit Margin"] = (ni / rev) * 100

    if ni is not None and ta not in (None, 0):
        ratios["Return on Assets"] = (ni / ta) * 100

    if ni is not None and eq not in (None, 0):
        ratios["Return on Equity"] = (ni / eq) * 100

    if ratios:
        result = pd.DataFrame(
            [{"Rasio": k, "Hasil": v} for k, v in ratios.items()]
        )
        st.dataframe(result, use_container_width=True)

        fig = px.bar(
            result,
            x="Rasio",
            y="Hasil",
            title="Hasil Perhitungan Rasio Keuangan"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Belum cukup kolom yang dipilih untuk menghitung rasio. "
            "Pastikan kolom yang dipilih sesuai dengan akun laporan."
        )

    st.caption(
        "Rasio dihitung dari nilai terakhir pada kolom yang dipilih. "
        "Pastikan data mewakili periode yang sama."
    )


def automated_audit(df):
    st.subheader("🔎 Automated Financial Audit")

    findings = []

    duplicate_count = int(df.duplicated().sum())
    if duplicate_count:
        findings.append({
            "Pengujian": "Data duplikat",
            "Jumlah": duplicate_count,
            "Risiko": "Sedang",
            "Keterangan": "Ditemukan baris dengan isi yang sama."
        })

    missing_count = int(df.isna().sum().sum())
    if missing_count:
        findings.append({
            "Pengujian": "Data kosong",
            "Jumlah": missing_count,
            "Risiko": "Sedang",
            "Keterangan": "Terdapat sel yang belum terisi."
        })

    for col in numeric_columns(df):
        values = pd.to_numeric(df[col], errors="coerce").dropna()

        if len(values) >= 4:
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1

            if iqr > 0:
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                unusual = int(((values < lower) | (values > upper)).sum())

                if unusual:
                    findings.append({
                        "Pengujian": f"Nilai tidak biasa: {col}",
                        "Jumlah": unusual,
                        "Risiko": "Perlu ditinjau",
                        "Keterangan": "Nilai berada di luar batas IQR."
                    })

    for col in df.columns:
        if "tanggal" in str(col).lower() or "date" in str(col).lower():
            parsed = pd.to_datetime(df[col], errors="coerce")
            invalid = int(parsed.isna().sum())

            if invalid:
                findings.append({
                    "Pengujian": f"Tanggal tidak valid: {col}",
                    "Jumlah": invalid,
                    "Risiko": "Sedang",
                    "Keterangan": "Sebagian tanggal tidak dapat dibaca."
                })

    if findings:
        result = pd.DataFrame(findings)
        st.dataframe(result, use_container_width=True)
        st.metric("Jumlah jenis indikasi", len(findings))
    else:
        st.success("Tidak ditemukan indikasi dari pengujian dasar.")

    st.warning(
        "Hasil ini merupakan indikasi awal untuk pemeriksaan lanjutan, "
        "bukan bukti kecurangan atau kesimpulan audit."
    )


def risk_assessment(df):
    st.subheader("⚠️ Audit Risk Assessment")

    nums = numeric_columns(df)
    if not nums:
        st.warning("Tidak ada kolom numerik untuk penilaian awal.")
        return

    selected = st.selectbox(
        "Pilih kolom yang ingin dinilai",
        nums,
        key="risk_column"
    )

    values = pd.to_numeric(df[selected], errors="coerce").dropna()

    if values.empty:
        st.warning("Kolom tidak memiliki nilai angka.")
        return

    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1

    if iqr == 0:
        unusual = values.iloc[0:0]
    else:
        unusual = values[(values < q1 - 1.5 * iqr) |
                         (values > q3 + 1.5 * iqr)]

    percentage = len(unusual) / len(values) * 100

    if percentage >= 10:
        level = "Tinggi"
    elif percentage >= 5:
        level = "Sedang"
    else:
        level = "Rendah"

    c1, c2, c3 = st.columns(3)
    c1.metric("Jumlah data", len(values))
    c2.metric("Nilai yang perlu ditinjau", len(unusual))
    c3.metric("Indikasi risiko", level)

    st.write(
        f"Sebanyak {percentage:.2f}% data berada di luar batas "
        "IQR pada kolom yang dipilih."
    )

    st.caption(
        "Penilaian ini hanya penyaringan statistik awal, bukan "
        "penilaian risiko audit profesional secara menyeluruh."
    )


def budget_analysis(df):
    st.subheader("💰 Budget vs Actual Analysis")
    nums = numeric_columns(df)

    if len(nums) < 2:
        st.warning("Pilih file yang memiliki kolom anggaran dan realisasi.")
        return

    budget_col = choose_column("Kolom Anggaran", nums, "budget_col")
    actual_col = choose_column("Kolom Realisasi", nums, "actual_col")

    if not budget_col or not actual_col:
        return

    result = df.copy()
    result["Selisih"] = result[budget_col] - result[actual_col]
    result["Persentase Realisasi"] = np.where(
        result[budget_col] != 0,
        result[actual_col] / result[budget_col] * 100,
        np.nan
    )

    st.dataframe(result, use_container_width=True)

    total_budget = result[budget_col].sum()
    total_actual = result[actual_col].sum()
    variance = total_budget - total_actual

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Anggaran", money(total_budget))
    c2.metric("Total Realisasi", money(total_actual))
    c3.metric("Selisih", money(variance))

    chart = result.reset_index()
    fig = px.bar(
        chart,
        x="index",
        y=[budget_col, actual_col],
        barmode="group",
        title="Perbandingan Anggaran dan Realisasi"
    )
    st.plotly_chart(fig, use_container_width=True)


def cashflow_analysis(df):
    st.subheader("🏦 Cash Flow Analysis")
    nums = numeric_columns(df)

    if not nums:
        st.warning("Tidak ditemukan kolom angka.")
        return

    amount_col = choose_column(
        "Pilih kolom nominal arus kas",
        nums,
        "cashflow_amount"
    )

    if not amount_col:
        return

    values = pd.to_numeric(df[amount_col], errors="coerce").dropna()
    inflow = values[values > 0].sum()
    outflow = abs(values[values < 0].sum())
    net_cash = inflow - outflow

    c1, c2, c3 = st.columns(3)
    c1.metric("Cash Inflow", money(inflow))
    c2.metric("Cash Outflow", money(outflow))
    c3.metric("Net Cash Flow", money(net_cash))

    chart = pd.DataFrame({
        "Jenis": ["Inflow", "Outflow"],
        "Nominal": [inflow, outflow]
    })

    fig = px.bar(chart, x="Jenis", y="Nominal", title="Arus Kas")
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Perhitungan ini menggunakan tanda positif sebagai kas masuk "
        "dan negatif sebagai kas keluar. Pastikan format data sesuai."
    )


def forecasting_analysis(df):
    st.subheader("🔮 Financial Forecasting & Scenario Planning")
    nums = numeric_columns(df)

    if not nums:
        st.warning("Tidak ditemukan kolom numerik.")
        return

    selected = st.selectbox(
        "Pilih kolom yang akan diproyeksikan",
        nums,
        key="forecast_column"
    )

    values = pd.to_numeric(df[selected], errors="coerce").dropna()

    if values.empty:
        st.warning("Kolom tidak memiliki nilai.")
        return

    base = float(values.iloc[-1])

    optimistic_rate = st.slider(
        "Asumsi optimistis (%)", 0, 100, 10
    )
    pessimistic_rate = st.slider(
        "Asumsi pesimistis (%)", 0, 100, 10
    )

    result = pd.DataFrame({
        "Skenario": ["Optimistis", "Base", "Pesimistis"],
        "Proyeksi": [
            base * (1 + optimistic_rate / 100),
            base,
            base * (1 - pessimistic_rate / 100)
        ]
    })

    st.dataframe(result, use_container_width=True)

    fig = px.bar(
        result,
        x="Skenario",
        y="Proyeksi",
        title=f"Simulasi Skenario {selected}"
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Ini adalah simulasi berdasarkan asumsi persentase, "
        "bukan prediksi statistik atau jaminan hasil masa depan."
    )


# ------------------------- AI ASSISTANT -------------------------

def ai_assistant(df, filename):
    st.subheader("🤖 FINORA AI Assistant")

    context = dataframe_context(df, filename)

    st.write(
        "Tanyakan kondisi laporan, perubahan akun, risiko, "
        "atau minta penjelasan hasil analisis."
    )

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Tanyakan sesuatu tentang file ini...")

    if question:
        st.session_state.chat_history.append({
            "role": "user",
            "content": question
        })

        with st.chat_message("user"):
            st.markdown(question)

        prompt = f"""
Kamu adalah FINORA AI, asisten analisis laporan keuangan dan audit.

Gunakan data yang diberikan sebagai dasar jawaban.
Jangan mengarang angka, akun, atau informasi yang tidak tersedia.
Jika data tidak cukup, jelaskan informasi apa yang dibutuhkan.
Bedakan indikasi risiko dengan bukti kecurangan.
Gunakan Bahasa Indonesia yang jelas dan profesional.

DATA:
{context}

PERTANYAAN:
{question}
"""

        with st.chat_message("assistant"):
            with st.spinner("FINORA AI sedang menganalisis..."):
                answer = ask_gemini(prompt)
                st.markdown(answer)

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer
        })

    if st.button("🗑️ Reset Chat"):
        st.session_state.chat_history = []
        st.rerun()


# ------------------------- AI INTERPRETATION -------------------------

def ai_interpretation(df, filename, module_name):
    st.markdown("#### 🤖 Interpretasi dengan Gemini AI")

    if st.button(
        f"Analisis hasil {module_name} dengan Gemini",
        key=f"ai_{module_name}"
    ):
        context = dataframe_context(df, filename)

        prompt = f"""
Kamu adalah FINORA AI, ahli analisis keuangan dan audit.

Analisis data berikut untuk kebutuhan {module_name}.
Berikan:
1. Ringkasan data.
2. Hal penting yang terlihat.
3. Potensi masalah atau risiko.
4. Rekomendasi tindak lanjut.
5. Keterbatasan analisis.

Jangan mengarang data atau menyimpulkan kecurangan tanpa bukti.
Gunakan Bahasa Indonesia yang mudah dipahami.

{context}
"""
        with st.spinner("Gemini sedang menganalisis..."):
            answer = ask_gemini(prompt)

        st.markdown(answer)


# ------------------------- UPLOAD & MODULE RUNNER -------------------------

MODULES = {
    "Financial Statement Analysis": financial_statement_analysis,
    "Financial Ratio Analysis": ratio_analysis,
    "Automated Financial Audit": automated_audit,
    "Audit Risk Assessment": risk_assessment,
    "Budget vs Actual Analysis": budget_analysis,
    "Cash Flow Analysis": cashflow_analysis,
    "Financial Forecasting": forecasting_analysis
}


def show_file_preview(df):
    st.markdown("#### 👀 Preview Data")
    st.caption(f"{len(df)} baris · {len(df.columns)} kolom")
    st.dataframe(df.head(100), use_container_width=True)


def run_one_module(module_name, df, filename):
    function = MODULES[module_name]
    function(df)

    ai_interpretation(df, filename, module_name)

    st.session_state.analysis_history.append({
        "Waktu": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "File": filename,
        "Modul": module_name
    })


# ------------------------- SIDEBAR -------------------------

st.sidebar.markdown("# 💗 FINORA AI")
st.sidebar.caption("Financial Analysis & Audit Intelligence")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "MENU UTAMA",
    [
        "Executive Dashboard",
        "Custom Analysis",
        "Financial Statement Analysis",
        "Financial Ratio Analysis",
        "Automated Financial Audit",
        "Audit Risk Assessment",
        "Budget vs Actual Analysis",
        "Cash Flow Analysis",
        "Financial Forecasting",
        "FINORA AI Assistant",
        "Report Center"
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption("FINORA Signature Pink")
st.sidebar.caption("#FF5C8B · Cream")


# ------------------------- PAGE HEADER -------------------------

st.markdown(
    "<h1>💗 FINORA AI</h1>",
    unsafe_allow_html=True
)
st.caption(
    "Financial Analysis & Audit Intelligence | "
    "Smart Financial Report Analysis"
)


# ------------------------- DASHBOARD -------------------------

if menu == "Executive Dashboard":
    st.title("Executive Financial Dashboard")
    st.write(
        "Ringkasan aktivitas analisis dan pemeriksaan yang telah "
        "dijalankan pada sesi aplikasi ini."
    )

    history = pd.DataFrame(st.session_state.analysis_history)

    total = len(history)
    files = history["File"].nunique() if not history.empty else 0
    modules = history["Modul"].nunique() if not history.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Analisis dijalankan", total)
    c2.metric("File diproses", files)
    c3.metric("Modul digunakan", modules)

    if not history.empty:
        st.subheader("Aktivitas Analisis")
        st.dataframe(history, use_container_width=True)

        chart = history["Modul"].value_counts().reset_index()
        chart.columns = ["Modul", "Jumlah"]
        fig = px.bar(
            chart,
            x="Modul",
            y="Jumlah",
            title="Aktivitas per Modul"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Belum ada aktivitas analisis. Pilih salah satu modul "
            "di menu sebelah kiri untuk memulai."
        )


# ------------------------- CUSTOM ANALYSIS -------------------------

elif menu == "Custom Analysis":
    st.title("🧩 Custom Analysis")
    st.write(
        "Unggah satu file, lalu pilih beberapa jenis analisis "
        "yang ingin dijalankan."
    )

    uploaded = st.file_uploader(
        "Upload satu file Excel atau CSV",
        type=["xlsx", "xls", "csv"],
        key="custom_upload"
    )

    if uploaded:
        sheets, file_type = read_uploaded_file(uploaded)

        if sheets:
            sheet_name = st.selectbox(
                "Pilih sheet yang akan dianalisis",
                list(sheets.keys()),
                key="custom_sheet"
            )

            df = clean_dataframe(sheets[sheet_name])
            st.session_state.last_dataframe = df
            st.session_state.last_filename = uploaded.name

            show_file_preview(df)

            st.markdown("### Pilih analisis")
            selected_modules = []

            cols = st.columns(2)
            module_names = list(MODULES.keys())

            for i, module_name in enumerate(module_names):
                with cols[i % 2]:
                    if st.checkbox(
                        module_name,
                        key=f"custom_check_{module_name}"
                    ):
                        selected_modules.append(module_name)

            include_ai = st.checkbox(
                "Sertakan interpretasi Gemini AI",
                value=True,
                key="custom_include_ai"
            )

            if st.button(
                "🚀 Jalankan Analisis Terpilih",
                type="primary",
                use_container_width=True
            ):
                if not selected_modules:
                    st.warning("Pilih minimal satu jenis analisis.")
                else:
                    st.markdown("---")
                    for module_name in selected_modules:
                        with st.expander(
                            f"📊 {module_name}",
                            expanded=True
                        ):
                            MODULES[module_name](df)

                            if include_ai:
                                ai_interpretation(
                                    df,
                                    uploaded.name,
                                    module_name
                                )

                            st.session_state.analysis_history.append({
                                "Waktu": datetime.now().strftime(
                                    "%d-%m-%Y %H:%M:%S"
                                ),
                                "File": uploaded.name,
                                "Modul": module_name
                            })

                    st.success("Analisis terpilih selesai dijalankan.")


# ------------------------- STANDALONE MODULES -------------------------

elif menu in MODULES:
    st.title(f"📊 {menu}")
    st.write(
        "Modul ini dapat dijalankan secara mandiri. "
        "Unggah file yang diperlukan tanpa harus menjalankan modul lain."
    )

    uploaded = st.file_uploader(
        "Upload file Excel atau CSV",
        type=["xlsx", "xls", "csv"],
        key=f"upload_{menu}"
    )

    if uploaded:
        sheets, file_type = read_uploaded_file(uploaded)

        if sheets:
            sheet_name = st.selectbox(
                "Pilih sheet",
                list(sheets.keys()),
                key=f"sheet_{menu}"
            )

            df = clean_dataframe(sheets[sheet_name])
            show_file_preview(df)

            if st.button(
                f"Jalankan {menu}",
                type="primary",
                use_container_width=True
            ):
                run_one_module(menu, df, uploaded.name)

            # AI chat dapat digunakan setelah file berhasil dibaca.
            if menu == "Financial Statement Analysis":
                ai_assistant(df, uploaded.name)


# ------------------------- AI ASSISTANT PAGE -------------------------

elif menu == "FINORA AI Assistant":
    st.title("🤖 FINORA AI Assistant")
    st.write(
        "Unggah laporan keuangan dan diskusikan isi file tersebut "
        "dengan Gemini AI."
    )

    uploaded = st.file_uploader(
        "Upload file untuk ditanyakan kepada AI",
        type=["xlsx", "xls", "csv"],
        key="assistant_upload"
    )

    if uploaded:
        sheets, file_type = read_uploaded_file(uploaded)

        if sheets:
            sheet_name = st.selectbox(
                "Pilih sheet",
                list(sheets.keys()),
                key="assistant_sheet"
            )

            df = clean_dataframe(sheets[sheet_name])
            show_file_preview(df)
            ai_assistant(df, uploaded.name)


# ------------------------- REPORT CENTER -------------------------

elif menu == "Report Center":
    st.title("📁 Report Center")
    st.write(
        "Lihat riwayat analisis pada sesi aplikasi ini dan unduh "
        "rekap aktivitas."
    )

    history = pd.DataFrame(st.session_state.analysis_history)

    if history.empty:
        st.info("Belum ada riwayat analisis.")
    else:
        st.dataframe(history, use_container_width=True)

        csv_data = history.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            "⬇️ Download Riwayat Analisis (CSV)",
            data=csv_data,
            file_name="FINORA_Analysis_History.csv",
            mime="text/csv",
            use_container_width=True
        )

st.markdown("---")
st.caption(
    "FINORA AI | Financial Analysis & Audit Intelligence | "
    "Analisis otomatis merupakan alat bantu dan perlu diverifikasi."
)
