
import streamlit as st
import pandas as pd
import altair as alt
import json
from datetime import datetime
from streamlit_local_storage import LocalStorage

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

MAX_EVENTS = 300
LOCAL_STORAGE_KEY = "kaiten_checker_draft_v1"

def normalize_events(events):
    """保存値を安全なイベント列へ整形する。"""
    normalized = []
    previous = None
    for raw in list(events or [])[:MAX_EVENTS]:
        if not isinstance(raw, dict):
            continue
        event_type = raw.get("type")
        if event_type not in ["start", "1k"]:
            continue
        try:
            value = max(0, int(raw.get("value")))
        except (TypeError, ValueError):
            continue
        if event_type == "1k" and (previous is None or value <= previous):
            continue
        normalized.append({"type": event_type, "value": value})
        previous = value
    return normalized

def migrate_v1_events(start_rotation, current_values):
    """旧版の開始回転数＋入力表を新しいイベント列へ変換する。"""
    filled_values = [value for value in list(current_values or []) if value is not None and not pd.isna(value)]
    if int(start_rotation) == 0 and not filled_values:
        return []

    events = [{"type": "start", "value": max(0, int(start_rotation))}]
    previous = events[0]["value"]
    for raw in filled_values:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > previous:
            events.append({"type": "1k", "value": value})
            previous = value
    return events

def calculate_all(events):
    """区間開始と1k確定の履歴から全指標を再計算する。"""
    rows = []
    previous = None
    first_start = None
    segment = 0
    investment_k = 0
    total_rotation = 0
    per_k_values = []
    latest = None

    for record_no, event in enumerate(normalize_events(events), start=1):
        value = int(event["value"])
        if event["type"] == "start":
            segment += 1
            previous = value
            if first_start is None:
                first_start = value
            rows.append({
                "記録No": record_no,
                "区間": segment,
                "区分": "開始",
                "投資k": investment_k,
                "現在回転数": value,
                "今回1k": None,
                "累計/k": round(total_rotation / investment_k, 2) if investment_k else None,
                "直近5k": round(sum(per_k_values[-5:]) / len(per_k_values[-5:]), 2) if per_k_values else None,
                "直近10k": round(sum(per_k_values[-10:]) / len(per_k_values[-10:]), 2) if per_k_values else None,
                "累計回転": total_rotation,
            })
            continue

        if previous is None or value <= previous:
            continue
        this_1k = value - previous
        previous = value
        investment_k += 1
        total_rotation += this_1k
        per_k_values.append(this_1k)
        row = {
            "記録No": record_no,
            "区間": segment,
            "区分": "1k確定",
            "投資k": investment_k,
            "現在回転数": value,
            "今回1k": this_1k,
            "累計/k": round(total_rotation / investment_k, 2),
            "直近5k": round(sum(per_k_values[-5:]) / len(per_k_values[-5:]), 2),
            "直近10k": round(sum(per_k_values[-10:]) / len(per_k_values[-10:]), 2),
            "累計回転": total_rotation,
            "開始回転数": first_start,
            "累計投資k": investment_k,
        }
        rows.append(row)
        latest = pd.Series(row)

    history = pd.DataFrame(rows)
    return history, latest, history.copy()

def make_summary_record(session_name, latest, result_data):
    return {
        "保存名": session_name,
        "保存時刻": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "開始回転数": int(latest["開始回転数"]),
        "累計投資k": int(latest["累計投資k"]),
        "最終回転数": int(latest["現在回転数"]),
        "累計回転": int(latest["累計回転"]),
        "累計/k": round(float(latest["累計/k"]), 2),
        "直近5k": round(float(latest["直近5k"]), 2),
        "直近10k": round(float(latest["直近10k"]), 2),
        "初当たり回数": result_data["初当たり回数"],
        "確変突入回数": result_data["確変突入回数"],
        "単発回数": result_data["単発回数"],
        "総当たり回数": result_data["総当たり回数"],
        "使用玉数": result_data["使用玉数"],
        "獲得玉数": result_data["獲得玉数"],
        "差玉": result_data["差玉"],
    }

def make_draft_payload():
    """入力途中の実戦をブラウザへ保存できる形にまとめる。"""
    return {
        "version": 2,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session_name": st.session_state.get("session_name", "実戦1"),
        "events": normalize_events(st.session_state.get("events", [])),
        "first_hits": int(st.session_state.get("first_hits", 0)),
        "kakuhen_hits": int(st.session_state.get("kakuhen_hits", 0)),
        "total_hits": int(st.session_state.get("total_hits", 0)),
        "earned_balls": int(st.session_state.get("earned_balls", 0)),
    }

def parse_draft(raw_draft):
    """localStorageの値を検証し、復元可能な辞書として返す。"""
    if not raw_draft:
        return None

    try:
        draft = json.loads(raw_draft) if isinstance(raw_draft, str) else raw_draft
        if not isinstance(draft, dict) or draft.get("version") not in [1, 2]:
            return None

        if draft.get("version") == 1:
            events = migrate_v1_events(
                draft.get("start_rotation", 0),
                draft.get("current_values", []),
            )
        else:
            events = normalize_events(draft.get("events", []))

        return {
            "session_name": str(draft.get("session_name", "実戦1")),
            "events": events,
            "first_hits": max(0, int(draft.get("first_hits", 0))),
            "kakuhen_hits": max(0, int(draft.get("kakuhen_hits", 0))),
            "total_hits": max(0, int(draft.get("total_hits", 0))),
            "earned_balls": max(0, int(draft.get("earned_balls", 0))),
            "saved_at": str(draft.get("saved_at", "")),
        }
    except (TypeError, ValueError):
        return None

def reset_current_session():
    st.session_state.events = []
    st.session_state.session_name = "実戦1"
    st.session_state.rotation_input = 0
    st.session_state.first_hits = 0
    st.session_state.kakuhen_hits = 0
    st.session_state.total_hits = 0
    st.session_state.earned_balls = 0

local_storage = LocalStorage(key="kaiten_checker_local_storage")

if "draft_restored" not in st.session_state:
    restored_draft = parse_draft(local_storage.getItem(LOCAL_STORAGE_KEY))
    if restored_draft:
        for key in [
            "session_name", "events", "first_hits",
            "kakuhen_hits", "total_hits", "earned_balls",
        ]:
            st.session_state[key] = restored_draft[key]
        st.session_state.restore_notice = restored_draft.get("saved_at", "")
    st.session_state.draft_restored = True

if "events" not in st.session_state:
    st.session_state.events = []

if "session_name" not in st.session_state:
    st.session_state.session_name = "実戦1"

if "rotation_input" not in st.session_state:
    st.session_state.rotation_input = 0

if "saved_sessions" not in st.session_state:
    st.session_state.saved_sessions = []

for key in ["first_hits", "kakuhen_hits", "total_hits", "earned_balls"]:
    if key not in st.session_state:
        st.session_state[key] = 0

if st.session_state.pop("reset_current_session", False):
    reset_current_session()

if "restore_rotation_input" in st.session_state:
    st.session_state.rotation_input = st.session_state.pop("restore_rotation_input")

if restore_notice := st.session_state.pop("restore_notice", None):
    st.success(f"前回の入力を復元しました（最終保存：{restore_notice}）")

st.markdown("### 現在の実戦")

session_name = st.text_input(
    "保存名",
    help="例：6/18 エヴァ、A店リゼロなど",
    key="session_name",
)

rotation_input = st.number_input(
    "現在回転数",
    min_value=0,
    step=1,
    key="rotation_input",
    help="数字を入力し、「区間開始」または「1k確定」を押します。",
)

action_col1, action_col2 = st.columns(2)
with action_col1:
    start_clicked = st.button(
        "区間開始",
        use_container_width=True,
        help="当たり・ST終了後など、新しい回転数の始まりを記録します。投資kは増えません。",
    )
with action_col2:
    confirm_clicked = st.button(
        "1k確定",
        use_container_width=True,
        help="前回値から1k使用後の回転数を記録します。",
    )

if start_clicked:
    st.session_state.events.append({"type": "start", "value": int(rotation_input)})
    st.rerun()

if confirm_clicked:
    if not st.session_state.events:
        st.error("先に「区間開始」で開始回転数を記録してください。")
    else:
        previous_value = int(st.session_state.events[-1]["value"])
        if int(rotation_input) <= previous_value:
            st.error(
                f"1k確定できません。入力値 {int(rotation_input)} は前回値 "
                f"{previous_value} 以下です。当たり・ST終了後なら「区間開始」を押してください。"
            )
        else:
            st.session_state.events.append({"type": "1k", "value": int(rotation_input)})
            st.rerun()

delete_clicked = st.button(
    "直前の1行を削除",
    use_container_width=True,
    disabled=not st.session_state.events,
    help="最後に記録した区間開始または1k確定を削除します。",
)

if delete_clicked:
    deleted = st.session_state.events.pop()
    st.session_state.restore_rotation_input = int(deleted["value"])
    st.session_state.delete_notice = (
        f"直前の1行（{'区間開始' if deleted['type'] == 'start' else '1k確定'}："
        f"{deleted['value']}）を削除しました。"
    )
    st.rerun()

if delete_notice := st.session_state.pop("delete_notice", None):
    st.success(delete_notice)

display_table_all, latest, calc_detail = calculate_all(st.session_state.events)

st.markdown("### 入力履歴")

if display_table_all.empty:
    st.caption("現在回転数を入力し、最初に「区間開始」を押してください。")
else:
    history_columns = [
        "記録No", "区間", "区分", "投資k", "現在回転数", "今回1k",
        "累計/k", "直近5k", "直近10k", "累計回転",
    ]
    st.dataframe(
        display_table_all[history_columns].tail(30),
        hide_index=True,
        use_container_width=True,
        height=480,
    )

if latest is None:
    st.info("区間開始を記録しました。1k使用後の現在回転数を入力し、「1k確定」を押してください。")
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

    st.markdown("### 実戦結果")

    result_col1, result_col2 = st.columns(2)
    with result_col1:
        first_hits = st.number_input(
            "初当たり回数",
            min_value=0,
            step=1,
            key="first_hits",
        )
        total_hits = st.number_input(
            "総当たり回数",
            min_value=0,
            step=1,
            key="total_hits",
        )

    with result_col2:
        kakuhen_hits = st.number_input(
            "確変突入回数",
            min_value=0,
            step=1,
            key="kakuhen_hits",
        )
        earned_balls = st.number_input(
            "獲得玉数（出玉カード）",
            min_value=0,
            step=1,
            key="earned_balls",
        )

    single_hits = max(0, int(first_hits) - int(kakuhen_hits))
    used_balls = int(latest["累計投資k"]) * 250
    ball_difference = int(earned_balls) - used_balls

    result_metric1, result_metric2, result_metric3 = st.columns(3)
    result_metric1.metric("単発回数（自動）", f"{single_hits}回")
    result_metric2.metric("使用玉数（自動）", f"{used_balls:,}玉")
    result_metric3.metric("差玉（自動）", f"{ball_difference:+,}玉")

    result_is_valid = True
    if kakuhen_hits > first_hits:
        st.error("確変突入回数は、初当たり回数以下で入力してください。")
        result_is_valid = False
    if total_hits < first_hits:
        st.error("総当たり回数は、初当たり回数以上で入力してください。")
        result_is_valid = False

    result_data = {
        "初当たり回数": int(first_hits),
        "確変突入回数": int(kakuhen_hits),
        "単発回数": single_hits,
        "総当たり回数": int(total_hits),
        "使用玉数": used_balls,
        "獲得玉数": int(earned_balls),
        "差玉": ball_difference,
    }

    save_col, reset_col = st.columns(2)
    with save_col:
        if st.button("この実戦を保存して次へ", disabled=not result_is_valid):
            detail_to_save = calc_detail.copy()
            detail_to_save.insert(0, "保存名", session_name)
            detail_to_save.insert(1, "保存時刻", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            st.session_state.saved_sessions.append({
                "summary": make_summary_record(session_name, latest, result_data),
                "detail": detail_to_save,
            })
            st.session_state.reset_current_session = True
            st.rerun()

    with reset_col:
        if st.button("保存せず入力をリセット"):
            st.session_state.reset_current_session = True
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

draft_json = json.dumps(make_draft_payload(), ensure_ascii=False)
if draft_json != st.session_state.get("last_saved_draft"):
    local_storage.setItem(
        LOCAL_STORAGE_KEY,
        draft_json,
        key="kaiten_checker_autosave",
    )
    st.session_state.last_saved_draft = draft_json

st.caption("※ 区間開始・1k確定の履歴は、この端末のブラウザへ自動保存されます。Safariの履歴・Webサイトデータを消去すると復元できません。保存済みデータは必要に応じてCSVダウンロードしてください。")
