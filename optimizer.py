import pulp
import pandas as pd
import datetime
import jpholiday
import calendar
import io


def run_optimizer(
    year: int,
    month: int,
    members: list[str],
    prev_duties: dict,
    prev_gap: dict,
    ng_days: dict,
    fixed_assignments: dict,
    external_days: list[int],
    gap_days: int = 3,
    day_weights: dict = None,
    w_shift: float = 2,
    w_total: float = 4,
    w_weight: float = 2,
    w_limit: float = 5,
    w_weekend: float = 3,
):
    """
    当直スケジュール最適化を実行し、(schedule_df, summary_df, status_str) を返す。
    """

    if day_weights is None:
        day_weights = {
            0: 1.5, 1: 1, 2: 1, 3: 1.5,
            4: 1,   5: 2.0, 6: 2.0
        }

    _, last_day = calendar.monthrange(year, month)
    days = list(range(1, last_day + 1))
    num_members = len(members)
    dates = {d: datetime.date(year, month, d) for d in days}

    def duty_weekday(date):
        if jpholiday.is_holiday(date):
            return 6
        return date.weekday()

    prob = pulp.LpProblem("DutySchedule", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("x", (days, members), cat=pulp.LpBinary)

    # ── ハード制約 ──────────────────────────────────────────

    for d in days:
        if d in external_days:
            prob += pulp.lpSum(x[d][p] for p in members) == 0
        else:
            prob += pulp.lpSum(x[d][p] for p in members) == 1

    for p in members:
        for d in ng_days.get(p, []):
            if d in days:
                prob += x[d][p] == 0

    for d, p in fixed_assignments.items():
        if d in days and p in members:
            prob += x[d][p] == 1

    for d in days:
        for p in members:
            window = [d + i for i in range(0, gap_days + 1) if d + i in days]
            prob += pulp.lpSum(x[d2][p] for d2 in window) <= 1

    for p in members:
        remaining_block = gap_days - prev_gap.get(p, gap_days)
        if remaining_block > 0:
            for d in range(1, remaining_block + 1):
                if d in days:
                    prob += x[d][p] == 0

    # ── ソフト制約 ──────────────────────────────────────────

    penalties = []

    mean_shifts = len(days) / num_members
    mean_total = (sum(prev_duties.values()) + len(days)) / num_members
    mean_weight = (
        sum(prev_duties.values()) +
        sum(day_weights[duty_weekday(dates[d])] for d in days)
    ) / num_members

    sat_days = [d for d in days if duty_weekday(dates[d]) == 5]
    sun_days = [d for d in days if duty_weekday(dates[d]) == 6]

    for p in members:
        total_shifts = pulp.lpSum(x[d][p] for d in days)

        dp = pulp.LpVariable(f"dev_plus_{p}", lowBound=0)
        dm = pulp.LpVariable(f"dev_minus_{p}", lowBound=0)
        prob += total_shifts - mean_shifts == dp - dm
        penalties.append(w_shift * (dp + dm))

        short = pulp.LpVariable(f"short_{p}", lowBound=0)
        over  = pulp.LpVariable(f"over_{p}", lowBound=0)
        prob += total_shifts + short >= 3
        prob += total_shifts - over  <= 4
        penalties.append(w_limit * (short + over))

        total_all = prev_duties.get(p, 0) + total_shifts
        dp2 = pulp.LpVariable(f"dev_total_plus_{p}", lowBound=0)
        dm2 = pulp.LpVariable(f"dev_total_minus_{p}", lowBound=0)
        prob += total_all - mean_total == dp2 - dm2
        penalties.append(w_total * (dp2 + dm2))

        current_weight = pulp.lpSum(
            x[d][p] * day_weights[duty_weekday(dates[d])]
            for d in days
        )
        total_weight = prev_duties.get(p, 0) + current_weight
        dp3 = pulp.LpVariable(f"dev_weight_plus_{p}", lowBound=0)
        dm3 = pulp.LpVariable(f"dev_weight_minus_{p}", lowBound=0)
        prob += total_weight - mean_weight == dp3 - dm3
        penalties.append(w_weight * (dp3 + dm3))

        weekend_count = (
            pulp.lpSum(x[d][p] for d in sat_days) +
            pulp.lpSum(x[d][p] for d in sun_days)
        )
        weekend_over = pulp.LpVariable(f"weekend_over_{p}", lowBound=0)
        prob += weekend_count - weekend_over <= 1
        penalties.append(w_weekend * weekend_over)

    prob += pulp.lpSum(penalties)

    # ── 求解 ────────────────────────────────────────────────

    solver = pulp.PULP_CBC_CMD(msg=0)
    status = prob.solve(solver)
    status_str = pulp.LpStatus[status]

    if status_str != "Optimal":
        return None, None, status_str

    # ── 結果整形 ────────────────────────────────────────────

    schedule = []
    for d in days:
        date_obj = dates[d]
        wday = duty_weekday(date_obj)
        wday_labels = ["月", "火", "水", "木", "金", "土", "日"]
        is_holiday = jpholiday.is_holiday(date_obj)
        assigned = None
        for p in members:
            if pulp.value(x[d][p]) == 1:
                assigned = p
        schedule.append({
            "日": d,
            "曜日": ("祝" if is_holiday else wday_labels[date_obj.weekday()]),
            "外部": "✓" if d in external_days else "",
            "当直者": assigned if assigned else "-",
        })

    df = pd.DataFrame(schedule)

    summary = []
    for p in members:
        total_days = int(sum(pulp.value(x[d][p]) for d in days))
        total_w = sum(
            pulp.value(x[d][p]) * day_weights[duty_weekday(dates[d])]
            for d in days
        )
        duty_list = [d for d in days if pulp.value(x[d][p]) == 1]
        summary.append({
            "メンバー": p,
            "今月当直日数": total_days,
            "今月重み合計": round(total_w, 2),
            "累計当直": round(prev_duties.get(p, 0) + total_days, 2),
            "当直日": ", ".join(str(d) for d in duty_list),
        })

    summary_df = pd.DataFrame(summary)

    return df, summary_df, status_str


def to_excel_bytes(df: pd.DataFrame, summary_df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="当直表", index=False)
        summary_df.to_excel(writer, sheet_name="集計", index=False)
    return buf.getvalue()
