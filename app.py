import streamlit as st
import datetime
import calendar
import pandas as pd
from optimizer import run_optimizer, to_excel_bytes

# ══════════════════════════════════════════
#  ページ設定
# ══════════════════════════════════════════

st.set_page_config(
    page_title="当直スケジューラー",
    page_icon="🏥",
    layout="wide",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .stButton > button {
        width: 100%;
        background: #1a6fbf;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.6rem;
        font-size: 1rem;
    }
    .stButton > button:hover { background: #155a9e; }
    .result-box {
        background: #f0f7ff;
        border-left: 4px solid #1a6fbf;
        padding: 1rem;
        border-radius: 6px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏥 当直スケジューラー")
st.caption("メンバー・NG日・固定当直などを設定し、最適なスケジュールを自動生成します。")

# ══════════════════════════════════════════
#  デフォルト値
# ══════════════════════════════════════════

DEFAULT_MEMBERS = ["谷口大", "谷口友", "今井", "上坂", "菅原", "岡田", "横手"]

DEFAULT_PREV_DUTIES = {
    "谷口大": 4.5, "谷口友": 6.0, "今井": 4.5,
    "上坂": 5.5, "菅原": 4.5, "岡田": 5.0, "横手": 5.0,
}

DEFAULT_PREV_GAP = {
    "谷口大": 10, "谷口友": 4, "今井": 11,
    "上坂": 2, "菅原": 1, "岡田": 3, "横手": 0,
}

DEFAULT_NG = {
    "谷口大": "3,4,5,14,19,28",
    "谷口友": "1,13,24,25,26,27,28",
    "今井": "17,18,19,22",
    "上坂": "",
    "菅原": "17,18,19,25,26",
    "岡田": "",
    "横手": "",
}

today = datetime.date.today()
default_year  = today.year + 1 if today.month == 12 else today.year
default_month = 1 if today.month == 12 else today.month + 1

# ══════════════════════════════════════════
#  サイドバー：基本設定
# ══════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ 基本設定")

    col_y, col_m = st.columns(2)
    with col_y:
        year  = st.number_input("年", min_value=2024, max_value=2100, value=default_year)
    with col_m:
        month = st.number_input("月", min_value=1, max_value=12, value=default_month)

    st.markdown("---")
    st.subheader("👥 メンバー")
    members_text = st.text_area(
        "メンバー（1行1名）",
        value="\n".join(DEFAULT_MEMBERS),
        height=180,
    )
    members = [m.strip() for m in members_text.splitlines() if m.strip()]

    st.markdown("---")
    st.subheader("📅 外部当直日")
    external_text = st.text_input(
        "外部当直日（カンマ区切り）",
        value="6,16,23,27,8,18,24,29",
    )
    external_days = [int(d.strip()) for d in external_text.split(",") if d.strip().isdigit()]

    st.markdown("---")
    st.subheader("🔒 固定当直")
    fixed_text = st.text_area(
        "日:名前（1行1件）例: 12:谷口大",
        value="12:谷口大\n19:谷口友\n26:今井",
        height=100,
    )
    fixed_assignments = {}
    for line in fixed_text.splitlines():
        line = line.strip()
        if ":" in line:
            parts = line.split(":", 1)
            try:
                fixed_assignments[int(parts[0].strip())] = parts[1].strip()
            except ValueError:
                pass

    st.markdown("---")
    gap_days = st.slider("最低間隔（日）", min_value=1, max_value=7, value=3)

# ══════════════════════════════════════════
#  メインエリア：タブ構成
# ══════════════════════════════════════════

tab_member, tab_run = st.tabs(["📝 メンバー詳細設定", "▶️ スケジュール生成"])

# ──────────────────────────────────────────
#  タブ1：メンバー詳細設定
# ──────────────────────────────────────────

with tab_member:
    st.subheader("前月データ・NG日の設定")
    st.caption("各メンバーの前月累計当直・前月最終当直からの経過日数・NG日を入力してください。")

    prev_duties = {}
    prev_gap    = {}
    ng_days     = {}

    # テーブル形式で入力
    cols = st.columns([2, 2, 2, 4])
    cols[0].markdown("**メンバー**")
    cols[1].markdown("**前月累計当直**")
    cols[2].markdown("**前月末からの経過日数**")
    cols[3].markdown("**NG日（カンマ区切り）**")

    for p in members:
        c0, c1, c2, c3 = st.columns([2, 2, 2, 4])
        c0.markdown(f"**{p}**")
        prev_duties[p] = c1.number_input(
            f"前月累計_{p}", min_value=0.0, step=0.5,
            value=float(DEFAULT_PREV_DUTIES.get(p, 0)),
            label_visibility="collapsed",
        )
        prev_gap[p] = c2.number_input(
            f"前月gap_{p}", min_value=0, step=1,
            value=int(DEFAULT_PREV_GAP.get(p, 3)),
            label_visibility="collapsed",
        )
        ng_raw = c3.text_input(
            f"NG_{p}",
            value=DEFAULT_NG.get(p, ""),
            label_visibility="collapsed",
        )
        ng_days[p] = [int(d.strip()) for d in ng_raw.split(",") if d.strip().isdigit()]

# ──────────────────────────────────────────
#  タブ2：スケジュール生成
# ──────────────────────────────────────────

with tab_run:

    st.subheader(f"📆 {year}年{month}月 スケジュール生成")

    # 設定サマリー
    _, last_day = calendar.monthrange(int(year), int(month))
    with st.expander("現在の設定を確認", expanded=False):
        st.write(f"**対象月**: {year}年{month}月（{last_day}日まで）")
        st.write(f"**メンバー**: {', '.join(members)}")
        st.write(f"**外部当直日**: {sorted(external_days)}")
        st.write(f"**固定当直**: {fixed_assignments}")
        st.write(f"**最低間隔**: {gap_days}日")

    if st.button("🚀 スケジュールを生成する"):
        if not members:
            st.error("メンバーを1人以上入力してください。")
        else:
            with st.spinner("最適化中... しばらくお待ちください"):
                try:
                    df, summary_df, status = run_optimizer(
                        year=int(year),
                        month=int(month),
                        members=members,
                        prev_duties=prev_duties,
                        prev_gap=prev_gap,
                        ng_days=ng_days,
                        fixed_assignments=fixed_assignments,
                        external_days=external_days,
                        gap_days=int(gap_days),
                    )
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
                    st.stop()

            if status != "Optimal":
                st.error(f"最適解が見つかりませんでした（ステータス: {status}）。NG日や固定当直の設定を見直してください。")
            else:
                st.success("✅ 最適スケジュールが生成されました！")

                # ── カレンダー表示 ──────────────────
                st.subheader("📅 当直カレンダー")

                duty_map = {
                    row["日"]: row["当直者"]
                    for _, row in df.iterrows()
                }

                wday_labels = ["月", "火", "水", "木", "金", "土", "日"]
                first_wday, _ = calendar.monthrange(int(year), int(month))

                import jpholiday

                cal_html = """
                <style>
                .cal-table { border-collapse: collapse; width: 100%; }
                .cal-table th {
                    background: #1a6fbf; color: white;
                    padding: 8px; text-align: center; font-size: 0.85rem;
                }
                .cal-table td {
                    border: 1px solid #dde3ec;
                    padding: 6px 8px; vertical-align: top;
                    min-width: 70px; height: 60px;
                    font-size: 0.82rem;
                }
                .cal-table td.sat { background: #eef4ff; }
                .cal-table td.sun { background: #fff0f0; }
                .cal-table td.hol { background: #fff0f0; }
                .cal-table td.ext { background: #f5f5f5; color: #aaa; }
                .cal-table td.empty { background: #fafafa; }
                .day-num { font-weight: bold; font-size: 0.95rem; }
                .duty-name {
                    margin-top: 4px;
                    background: #1a6fbf;
                    color: white;
                    border-radius: 4px;
                    padding: 2px 5px;
                    font-size: 0.78rem;
                    display: inline-block;
                }
                .ext-label {
                    margin-top: 4px;
                    background: #bbb;
                    color: white;
                    border-radius: 4px;
                    padding: 2px 5px;
                    font-size: 0.78rem;
                    display: inline-block;
                }
                </style>
                <table class="cal-table">
                <tr>
                """
                for w in wday_labels:
                    cal_html += f"<th>{w}</th>"
                cal_html += "</tr><tr>"

                # 月初の空白
                for _ in range(first_wday):
                    cal_html += '<td class="empty"></td>'

                for day in range(1, last_day + 1):
                    date_obj = datetime.date(int(year), int(month), day)
                    wday = date_obj.weekday()
                    is_holiday = jpholiday.is_holiday(date_obj)
                    is_ext = day in external_days

                    if is_ext:
                        css = "ext"
                    elif is_holiday or wday == 6:
                        css = "sun"
                    elif wday == 5:
                        css = "sat"
                    else:
                        css = ""

                    person = duty_map.get(day, None)
                    badge = ""
                    if is_ext:
                        badge = '<br><span class="ext-label">外部</span>'
                    elif person and person != "-":
                        badge = f'<br><span class="duty-name">{person}</span>'

                    cal_html += f'<td class="{css}"><span class="day-num">{day}</span>{badge}</td>'

                    if (first_wday + day) % 7 == 0 and day != last_day:
                        cal_html += "</tr><tr>"

                cal_html += "</tr></table>"
                st.markdown(cal_html, unsafe_allow_html=True)

                # ── 一覧表 ──────────────────────────
                st.subheader("📋 当直一覧")
                st.dataframe(
                    df[df["外部"] == ""],
                    use_container_width=True,
                    hide_index=True,
                )

                # ── 統計 ────────────────────────────
                st.subheader("📊 メンバー別集計")
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

                # ── Excelダウンロード ────────────────
                st.subheader("⬇️ Excelダウンロード")
                excel_bytes = to_excel_bytes(df, summary_df)
                st.download_button(
                    label="📥 Excelファイルをダウンロード",
                    data=excel_bytes,
                    file_name=f"duty_schedule_{year}_{month}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
