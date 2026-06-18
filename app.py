
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

st.set_page_config(
    page_title="回転率チェッカー",
    page_icon="🎰",
    layout="centered",
)

st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
    max-width: 820px;
}
h1 {
    font-size: 1.45rem !important;
}
h2, h3 {
    font-size: 1.05rem !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.05rem;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem;
}
</style>
""", unsafe_allow_html=True)

st.title("🎰 回転率チェッカー")
st.caption("開始回転数を入れ、表の「現在回転数」だけ入力します。ほかの列は自動計算です。")

MAX_ROWS = 150

def blank_values(n=MAX_ROWS):
    return [None] * n

def adjust_values(values, n):
    values = list(values)
    if len(values) < n:
        values += [None] * (n - len(values))
    return values[:n]

def last_filled_k(values):
    last = 0
    for i, v in enumerate(values, start=1):
        if v is not None and not pd.isna(v):
            last = i
    return last

def calculate_all(current_values, start_rotation):
    values = adjust_values(current_values, MAX_ROWS)

    base = pd.DataFrame({
        "投資k": list(range(1, MAX_ROWS + 1)),
        "現在回転数": values,
    })

    base["今回1k"] = None
    base["累計/k"] = None
    base["直近5k"] = None
    base["直近10k"] = None
    base["累計回転"] = None

    valid = base.dropna(subset=["現在回転数"]).copy()
    if valid.empty:
        return base, None, pd.DataFrame()

    valid["現在回転数"] = pd.to_numeric(valid["現在回転数"], errors="coerce")
    valid = valid.dropna(subset=["現在回転数"]).copy()
    valid["現在回転数"] = valid["現在回転数"].astype(int)

    valid = valid[valid["現在回転数"] >= start_rotation].copy()
    if valid.empty:
        return base, None, pd.DataFrame()

    valid = valid.sort_values("投資k").reset_index(drop=True)

    previous_values = [start_rotation] + valid["現在回転数"].tolist()[:-1]
    valid["前回回転数"] = previous_values
    valid["今回1k"] = valid["現在回転数"] - valid["前回回転数"]
    valid["累計投資k"] = range(1, len(valid) + 1)
    valid["累計回転"] = valid["現在回転数"] - start_rotation
    valid["累計/k"] = valid["累計回転"] / valid["累計投資k"]
    valid["直近5k"] = valid["今回1k"].rolling(window=5, min_periods=1).mean()
    valid["直近10k"] = valid["今回1k"].rolling(window=10, min_periods=1).mean()

    out = base.copy()
    for i, row in valid.iterrows():
        source_k = int(row["投資k"])
        idx = out.index[out["投資k"] == source_k][0]
        out.loc[idx, "今回1k"] = int(row["今回1k"])
        out.loc[idx, "累計/k"] = round(float(row["累計/k"]), 2)
        out.loc[idx, "直近5k"] = round(float(row["直近5k"]), 2)
        out.loc[idx, "直近10k"] = round(float(row["直近10k"]), 2)
        out.loc[idx, "累計回転"] = int(row["累計回転"])

    latest = valid.iloc[-1]
    calc_detail = valid[[
        "累計投資k", "現在回転数", "今回1k", "累計/k", "直近5k", "直近10k", "累計回転"
    ]].copy()
    calc_detail["累計/k"] = calc_detail["累計/k"].round(2)
    calc_detail["直近5k"] = calc_detail["直近5k"].round(2)
    calc_detail["直近10k"] = calc_detail["直近10k"].round(2)

    return out, latest, calc_detail

def get_window_range(values, window_size, mode):
    if mode == "全体を表示":
        return 1, MAX_ROWS

    last = last_filled_k(values)
    if last == 0:
        start = 1
    else:
        # 最新入力が下の方に来るように、少し手前から表示
        start = max(1, last - window_size + 6)

    end = min(MAX_ROWS, start + window_size - 1)
    start = max(1, end - window_size + 1)
    return start, end

def make_summary_record(session_name, start_rotation, latest):
    return {
        "保存名": session_name,
        "保存時刻": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "開始回転数": int(start_rotation),
        "累計投資k": int(latest["累計投資k"]),
        "最終回転数": int(latest["現在回転数"]),
        "累計回転": int(latest["累計回転"]),
        "累計/k": round(float(latest["累計/k"]), 2),
        "直近5k": round(float(latest["直近5k"]), 2),
        "直近10k": round(float(latest["直近10k"]), 2),
    }

if "current_values" not in st.session_state:
    st.session_state.current_values = blank_values(MAX_ROWS)

if "saved_sessions" not in st.session_state:
    st.session_state.saved_sessions = []

st.markdown("### 現在の実戦")

session_name = st.text_input("保存名", value="実戦1", help="例：6/18 エヴァ、A店リゼロなど")

start_rotation = st.number_input(
    "開始回転数",
    min_value=0,
    step=1,
    value=0,
)

st.session_state.current_values = adjust_values(st.session_state.current_values, MAX_ROWS)

display_mode = st.radio(
    "表示範囲",
    options=["最新付近を表示", "全体を表示"],
    horizontal=True,
    index=0,
    help="入力中は「最新付近を表示」の方がスクロール戻りを避けやすいです。",
)

window_size = st.selectbox(
    "表示行数",
    options=[10, 20, 30, 40, 60],
    index=2,
    disabled=(display_mode == "全体を表示"),
)

display_table_all, latest, calc_detail = calculate_all(st.session_state.current_values, start_rotation)

start_k, end_k = get_window_range(st.session_state.current_values, window_size, display_mode)
display_table = display_table_all[
    (display_table_all["投資k"] >= start_k) & (display_table_all["投資k"] <= end_k)
].copy()

st.markdown(f"### 入力・計算表（{start_k}k〜{end_k}k）")

edited = st.data_editor(
    display_table,
    hide_index=True,
    use_container_width=True,
    height=560,
    num_rows="fixed",
    disabled=["投資k", "今回1k", "累計/k", "直近5k", "直近10k", "累計回転"],
    column_config={
        "投資k": st.column_config.NumberColumn("投資k", width="small"),
        "現在回転数": st.column_config.NumberColumn("現在回転数", min_value=0, step=1, width="small"),
        "今回1k": st.column_config.NumberColumn("今回1k", width="small"),
        "累計/k": st.column_config.NumberColumn("累計/k", width="small", format="%.2f"),
        "直近5k": st.column_config.NumberColumn("直近5k", width="small", format="%.2f"),
        "直近10k": st.column_config.NumberColumn("直近10k", width="small", format="%.2f"),
        "累計回転": st.column_config.NumberColumn("累計回転", width="small"),
    },
    key="kaiten_single_table",
)

new_visible_values = edited["現在回転数"].tolist()
normalized_visible = []
for v in new_visible_values:
    if pd.isna(v):
        normalized_visible.append(None)
    else:
        normalized_visible.append(int(v))

new_all_values = st.session_state.current_values.copy()
new_all_values[start_k - 1:end_k] = normalized_visible

if new_all_values != st.session_state.current_values:
    st.session_state.current_values = new_all_values
    st.rerun()

display_table_all, latest, calc_detail = calculate_all(st.session_state.current_values, start_rotation)

if latest is None:
    st.info("現在回転数を入力すると、同じ表の右側に計算結果が表示されます。")
else:
    st.markdown("### 現在の結果")

    col0, col1, col2, col3, col4, col5, col6 = st.columns(7)
    col0.metric("現在の結果", "最新")
    col1.metric("累計投資", f"{int(latest['累計投資k'])}k")
    col2.metric("今回1k", f"{int(latest['今回1k'])}")
    col3.metric("累計/k", f"{latest['累計/k']:.2f}")
    col4.metric("直近5k", f"{latest['直近5k']:.2f}")
    col5.metric("直近10k", f"{latest['直近10k']:.2f}")
    col6.metric("累計回転", f"{int(latest['累計回転'])}")

    save_col, reset_col = st.columns(2)
    with save_col:
        if st.button("この実戦を保存して次へ"):
            detail_to_save = calc_detail.copy()
            detail_to_save.insert(0, "保存名", session_name)
            detail_to_save.insert(1, "開始回転数", int(start_rotation))
            detail_to_save.insert(2, "保存時刻", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            st.session_state.saved_sessions.append({
                "summary": make_summary_record(session_name, start_rotation, latest),
                "detail": detail_to_save,
            })
            st.session_state.current_values = blank_values(MAX_ROWS)
            st.rerun()

    with reset_col:
        if st.button("保存せず入力をリセット"):
            st.session_state.current_values = blank_values(MAX_ROWS)
            st.rerun()

    show_graph = st.checkbox("グラフを表示する", value=False)

    if show_graph:
        st.markdown("### グラフ")

        calc_rows = display_table_all.dropna(subset=["現在回転数", "今回1k"]).copy()
        if not calc_rows.empty:
            chart_df = calc_rows[["投資k", "今回1k", "累計/k", "直近5k", "直近10k"]].copy()
            chart_df = chart_df.melt(
                id_vars=["投資k"],
                value_vars=["今回1k", "累計/k", "直近5k", "直近10k"],
                var_name="指標",
                value_name="回転率",
            )

            chart = alt.Chart(chart_df).mark_line(point=True).encode(
                x=alt.X(
                    "投資k:O",
                    title="投資k",
                    axis=alt.Axis(labelAngle=-90)
                ),
                y=alt.Y("回転率:Q", title="回転/k"),
                color=alt.Color("指標:N", title="指標"),
                tooltip=["投資k", "指標", alt.Tooltip("回転率:Q", format=".2f")],
            ).properties(height=320)

            st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("グラフは必要なときだけ表示できます。入力中は非表示の方が軽く動きます。")

st.markdown("---")
st.markdown("### 保存済みデータ")

if not st.session_state.saved_sessions:
    st.caption("まだ保存済みデータはありません。")
else:
    summary_df = pd.DataFrame([s["summary"] for s in st.session_state.saved_sessions])
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    all_detail_df = pd.concat([s["detail"] for s in st.session_state.saved_sessions], ignore_index=True)

    with st.expander("保存済みの詳細を見る", expanded=False):
        st.dataframe(all_detail_df, use_container_width=True, hide_index=True)

    csv_summary = summary_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "保存済みサマリーをCSVダウンロード",
        data=csv_summary,
        file_name="kaiten_checker_summary.csv",
        mime="text/csv",
    )

    csv_detail = all_detail_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "保存済み詳細をCSVダウンロード",
        data=csv_detail,
        file_name="kaiten_checker_detail.csv",
        mime="text/csv",
    )

    if st.button("保存済みデータを全削除"):
        st.session_state.saved_sessions = []
        st.rerun()

st.caption("※ 入力中は最新付近表示がおすすめです。この保存はブラウザセッション内の一時保存なので、必要ならCSVダウンロードしてください。")
