    mode = st.radio("Mode analisis", ["Mandiri", "Custom"], horizontal=True, key="report_mode")
    if df is None:
        st.info("Unggah file Excel untuk memulai analisis laporan keuangan.")
    else:
        if mode == "Mandiri":
            chosen_report = st.selectbox("Pilih analisis", report_options)
            selected_reports = [chosen_report]
        else:
            selected_reports = st.multiselect(
                "Pilih analisis yang ingin dijalankan",
                report_options,
                default=report_options[:3],
            )
        if st.button("Jalankan Analisis", disabled=not selected_reports, use_container_width=True):
            results, tables = build_financial_analysis(df, selected_reports)
            st.session_state.report_results = results
            st.session_state.report_tables = tables
            context = (
                f"File: {st.session_state.active_filename}\n"
                f"Jumlah baris: {len(df)}\nHasil analisis:\n"
                f"{json.dumps(results, ensure_ascii=False, default=str)}"
            )
            st.session_state.analysis_context = context
            summary = f"{len(selected_reports)} analisis dijalankan pada file {st.session_state.active_filename}."
            save_analysis(
                st.session_state.username,
                f"Laporan - {st.session_state.active_filename}",
                "Laporan Keuangan",
                summary,
                {"file": st.session_state.active_filename, "selected": selected_reports,
                 "results": results},
            )
            st.success("Analisis selesai dan hasilnya disimpan.")
        if "report_results" in st.session_state:
            st.markdown("### Hasil analisis")
            for name, value in st.session_state.report_results.items():
                with st.expander(name, expanded=True):
                    if name in st.session_state.report_tables:
                        table = st.session_state.report_tables[name]
                        if not table.empty:
                            st.dataframe(table, use_container_width=True, hide_index=True)
                            numeric_cols = table.select_dtypes(include=np.number).columns.tolist()
                            if numeric_cols and len(table) > 0:
                                st.plotly_chart(
                                    px.bar(table, x=table.columns[0], y=numeric_cols[0],
                                           title=name),
                                    use_container_width=True,
                                )
                        else:
                            st.info(str(value))
                    else:
                        st.json(value) if isinstance(value, (dict, list)) else st.info(str(value))
            tables = st.session_state.report_tables
            if tables:
                st.download_button(
                    "Download hasil analisis (Excel)",
                    dataframe_to_excel(tables),
                    file_name="FINORA_Analisis_Keuangan.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            first_table = next(iter(tables.values()), pd.DataFrame())
            st.download_button(
                "Download ringkasan (PDF)",
                make_pdf("Laporan Analisis Keuangan",
                         f"File: {st.session_state.active_filename}. Analisis: {', '.join(st.session_state.report_results.keys())}.",
                         first_table),
                file_name="FINORA_Analisis_Keuangan.pdf",
                mime="application/pdf",
            )

    st.divider()
    st.markdown("### Tanya FINORA AI")
    st.caption("Gemini akan menjawab berdasarkan konteks analisis yang tersedia pada sesi ini.")
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    question = st.chat_input("Tanyakan sesuatu tentang data keuangan...")
    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        answer = ask_gemini(question, st.session_state.analysis_context)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)

elif page == "Simpan":
    st.subheader("Simpan & Riwayat Analisis")
    records = load_saved(st.session_state.username)
    if not records:
        st.info("Belum ada hasil analisis yang tersimpan untuk workspace ini.")
    else:
        for record in records:
            rid, title, kind, created, summary, details = record
            with st.expander(f"{title} · {created}"):
                st.caption(f"Jenis: {kind} · ID: {rid}")
                st.write(summary)
                try:
                    st.json(json.loads(details))
                except Exception:
                    st.text(details)
                st.download_button(
                    "Download detail JSON",
                    data=details,
                    file_name=f"FINORA_riwayat_{rid}.json",
                    mime="application/json",
                    key=f"download_{rid}",
                )

st.divider()
st.caption("FINORA AI · Hasil analisis otomatis perlu ditinjau dan diverifikasi oleh pengguna.")
