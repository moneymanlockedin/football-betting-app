import io
import math

import pandas as pd
import requests
import streamlit as st

CORE = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
LEAGUES = {
    "England Premier League": "E0",
    "England Championship": "E1",
    "England League One": "E2",
    "England League Two": "E3",
    "Scotland Premiership": "SC0",
    "Germany Bundesliga": "D1",
    "Spain La Liga": "SP1",
    "Italy Serie A": "I1",
    "France Ligue 1": "F1",
    "Netherlands Eredivisie": "N1",
}
SEASONS = ["2026/27", "2025/26", "2024/25", "2023/24", "2022/23", "2021/22", "2020/21", "2019/20", "2018/19"]


def num(x):
    return pd.to_numeric(x, errors="coerce")


def season_code(s):
    a, b = s.split("/")
    return a[-2:] + b[-2:]


def max_dd(profits):
    if len(profits) == 0:
        return 0.0
    cumulative = profits.cumsum()
    return float((cumulative.cummax() - cumulative).max())


def over25_probability(expected_goals):
    if pd.isna(expected_goals):
        return None
    goals = max(float(expected_goals), 0.05)
    return 1 - math.exp(-goals) * (1 + goals + goals * goals / 2)


def download(code, season):
    url = f"https://www.football-data.co.uk/mmz4281/{season_code(season)}/{code}.csv"
    response = requests.get(url, timeout=30, headers={"User-Agent": "FootballResearchLab/1.0"})
    response.raise_for_status()
    return pd.read_csv(io.BytesIO(response.content), encoding="latin1")


def load_data():
    frames = []
    source = st.radio("Data source", ["Import multiple seasons", "Upload CSV"], horizontal=True)

    if source == "Upload CSV":
        file = st.file_uploader("Choose CSV", type=["csv"])
        if file:
            frames = [pd.read_csv(file, encoding="latin1")]
    else:
        left, right = st.columns(2)
        with left:
            league = st.selectbox("League", list(LEAGUES))
        with right:
            seasons = st.multiselect("Seasons", SEASONS, ["2025/26", "2024/25", "2023/24"])

        if st.button("Import selected seasons", type="primary"):
            errors = []
            progress = st.progress(0)
            for index, season in enumerate(seasons):
                try:
                    frame = download(LEAGUES[league], season)
                    frame["ImportedSeason"] = season
                    frames.append(frame)
                except Exception as error:
                    errors.append(f"{season}: {error}")
                progress.progress((index + 1) / max(len(seasons), 1))

            for error in errors:
                st.warning(error)
            if frames:
                st.session_state["frames_locked"] = frames
                st.session_state["source_locked"] = league

        frames = st.session_state.get("frames_locked", frames)

    if not frames:
        st.warning("Import or upload match data to begin.")
        st.stop()

    data = pd.concat(frames, ignore_index=True, sort=False)
    rename = {
        "Home Team": "HomeTeam",
        "Away Team": "AwayTeam",
        "HomeGoals": "FTHG",
        "AwayGoals": "FTAG",
        "FullTimeHomeGoals": "FTHG",
        "FullTimeAwayGoals": "FTAG",
        "FullTimeResult": "FTR",
    }
    data = data.rename(columns={key: value for key, value in rename.items() if key in data.columns})

    missing = [column for column in CORE if column not in data.columns]
    if missing:
        st.error("Missing columns: " + ", ".join(missing))
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"], errors="coerce", dayfirst=True)
    data["FTHG"] = num(data["FTHG"])
    data["FTAG"] = num(data["FTAG"])
    data["FTR"] = data["FTR"].astype(str).str.upper().str.strip()
    data = data.dropna(subset=["Date", "FTHG", "FTAG"])
    data = data[data["FTR"].isin(["H", "D", "A"])].copy()
    data["FTHG"] = data["FTHG"].astype(int)
    data["FTAG"] = data["FTAG"].astype(int)
    data["TotalGoals"] = data["FTHG"] + data["FTAG"]
    return data.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)


def odds_options(data):
    return [column for column in ["B365>2.5", "Avg>2.5", "Max>2.5", "P>2.5"] if column in data.columns]


def features(data):
    history = {}
    rows = []

    for _, match in data.sort_values(["Date", "HomeTeam", "AwayTeam"]).iterrows():
        def summary(team):
            team_history = history.get(team, [])
            if not team_history:
                return 0, None, None
            return (
                len(team_history),
                sum(item[0] for item in team_history) / len(team_history),
                sum(item[1] for item in team_history) / len(team_history),
            )

        home_games, home_for, home_against = summary(match.HomeTeam)
        away_games, away_for, away_against = summary(match.AwayTeam)
        home_inputs = [home_for, away_against]
        away_inputs = [away_for, home_against]
        valid_home = [value for value in home_inputs if value is not None]
        valid_away = [value for value in away_inputs if value is not None]
        expected_home = sum(valid_home) / len(valid_home) if valid_home else None
        expected_away = sum(valid_away) / len(valid_away) if valid_away else None
        expected_total = expected_home + expected_away if expected_home is not None and expected_away is not None else None

        rows.append(
            {
                "Date": match.Date,
                "HomeTeam": match.HomeTeam,
                "AwayTeam": match.AwayTeam,
                "PriorHome": home_games,
                "PriorAway": away_games,
                "ExpectedTotal": expected_total,
                "ModelProb": over25_probability(expected_total),
            }
        )

        history.setdefault(match.HomeTeam, []).append((match.FTHG, match.FTAG))
        history.setdefault(match.AwayTeam, []).append((match.FTAG, match.FTHG))

    return data.merge(pd.DataFrame(rows), on=["Date", "HomeTeam", "AwayTeam"], how="left")


def prepared_pool(data, odds, min_games, min_odds, max_odds, start, end):
    pool = features(data)
    pool[odds] = num(pool[odds])
    pool["Implied"] = 1 / pool[odds]
    pool["Actual"] = (pool["TotalGoals"] > 2).astype(int)
    pool = pool[
        (pool.Date >= pd.Timestamp(start))
        & (pool.Date <= pd.Timestamp(end))
        & (pool.PriorHome >= min_games)
        & (pool.PriorAway >= min_games)
        & pool.ModelProb.notna()
        & pool[odds].notna()
        & (pool[odds] >= min_odds)
        & (pool[odds] <= max_odds)
    ].copy()
    return pool


def evaluate_pool(pool, odds, edge):
    selected = pool[pool["ModelProb"] - pool["Implied"] >= edge].copy()
    if selected.empty:
        return None, selected
    selected["Won"] = selected["Actual"].astype(bool)
    selected["Profit"] = selected[odds].where(selected["Won"], 0) - 1
    selected["CumulativeProfit"] = selected["Profit"].cumsum()
    result = {
        "Bets": len(selected),
        "Wins": int(selected["Won"].sum()),
        "Strike rate": selected["Won"].mean() * 100,
        "Profit": selected["Profit"].sum(),
        "ROI": selected["Profit"].mean() * 100,
        "Max drawdown": max_dd(selected["Profit"]),
    }
    return result, selected


def evaluate(data, odds, min_games, edge, min_odds, max_odds, start, end):
    pool = prepared_pool(data, odds, min_games, min_odds, max_odds, start, end)
    return evaluate_pool(pool, odds, edge)


def calibration_diagnostics(pool):
    if pool.empty:
        return None, pd.DataFrame()

    diagnostics = {
        "Observations": len(pool),
        "Brier score - model": ((pool["ModelProb"] - pool["Actual"]) ** 2).mean(),
        "Brier score - odds implied": ((pool["Implied"] - pool["Actual"]) ** 2).mean(),
        "Mean model probability": pool["ModelProb"].mean(),
        "Actual over 2.5 rate": pool["Actual"].mean(),
    }
    bins = [0.0, 0.40, 0.50, 0.60, 0.70, 0.80, 1.01]
    labels = ["<40%", "40-50%", "50-60%", "60-70%", "70-80%", "80%+"]
    table = pool.copy()
    table["Probability band"] = pd.cut(table["ModelProb"], bins=bins, labels=labels, right=False, include_lowest=True)
    calibration = (
        table.groupby("Probability band", observed=False)
        .agg(
            Bets=("Actual", "size"),
            MeanPredicted=("ModelProb", "mean"),
            ActualRate=("Actual", "mean"),
            MeanOddsImplied=("Implied", "mean"),
        )
        .reset_index()
    )
    calibration["MeanPredicted"] = (calibration["MeanPredicted"] * 100).round(2)
    calibration["ActualRate"] = (calibration["ActualRate"] * 100).round(2)
    calibration["MeanOddsImplied"] = (calibration["MeanOddsImplied"] * 100).round(2)
    return diagnostics, calibration


def show_metrics(result):
    columns = st.columns(6)
    labels = ["Bets", "Wins", "Strike rate", "Profit", "ROI", "Max drawdown"]
    values = [
        result["Bets"],
        result["Wins"],
        f"{result['Strike rate']:.1f}%",
        f"{result['Profit']:+.2f}",
        f"{result['ROI']:+.2f}%",
        f"{result['Max drawdown']:.2f}",
    ]
    for column, label, value in zip(columns, labels, values):
        column.metric(label, value)


st.set_page_config(page_title="Football Betting Research Lab", page_icon="⚽", layout="wide")
st.title("⚽ Football Betting Research Lab")
st.info("Research only. Results are historical diagnostics, not forecasts or guarantees.")
data = load_data()
st.success(f"Loaded {len(data):,} matches")
st.download_button("Download combined dataset", data.to_csv(index=False), "combined_dataset.csv", "text/csv")

st.header("Market setup")
options = odds_options(data)
if not options:
    st.error("No Over 2.5 odds column found.")
    st.stop()

column_one, column_two, column_three = st.columns(3)
with column_one:
    odds = st.selectbox("Over 2.5 odds source", options)
with column_two:
    min_games = st.number_input("Minimum prior games", 1, 20, 5)
with column_three:
    min_odds = st.number_input("Minimum odds", 1.01, 10.0, 1.50, 0.05)
max_odds = st.number_input("Maximum odds", 1.01, 20.0, 10.0, 0.25)

min_date, max_date = data.Date.min().date(), data.Date.max().date()
left_date, right_date = st.columns(2)
with left_date:
    start = st.date_input("Analysis start", min_date, min_value=min_date, max_value=max_date)
with right_date:
    end = st.date_input("Analysis end", max_date, min_value=min_date, max_value=max_date)

st.header("Walk-forward research")
edge = st.slider("Minimum model edge", 0.0, 0.20, 0.05, 0.01)
if st.button("Run walk-forward evaluation", type="primary"):
    result, test = evaluate(data, odds, int(min_games), float(edge), float(min_odds), float(max_odds), start, end)
    if result:
        show_metrics(result)
        st.line_chart(test.set_index("Date")["CumulativeProfit"])
        st.dataframe(test.head(200), use_container_width=True, hide_index=True)
    else:
        st.warning("No qualifying selections.")

st.header("Robustness checks")
if st.button("Run sensitivity grid"):
    rows = []
    for minimum_edge in [0.0, 0.03, 0.05, 0.07, 0.10]:
        for ceiling in [1.75, 2.0, 2.5, 3.0, 5.0]:
            result, _ = evaluate(data, odds, int(min_games), minimum_edge, float(min_odds), ceiling, start, end)
            if result:
                rows.append(
                    {
                        "Minimum edge": minimum_edge,
                        "Max odds": ceiling,
                        **{key: round(value, 2) if isinstance(value, float) else value for key, value in result.items()},
                    }
                )
    if rows:
        st.dataframe(
            pd.DataFrame(rows).sort_values(["ROI", "Bets"], ascending=False),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No configurations produced results.")

st.header("Locked final holdout test")
st.write("Choose a development cutoff. Settings are selected above, then the holdout is evaluated separately and is not used in the sensitivity grid.")
cutoff = st.date_input("Development cutoff", max_date - pd.Timedelta(days=365), min_value=min_date, max_value=max_date)

if st.button("Run locked holdout test", type="primary"):
    train_end = pd.Timestamp(cutoff)
    holdout_start = (train_end + pd.Timedelta(days=1)).date()
    if holdout_start > end:
        st.warning("Move the cutoff earlier so a holdout period remains.")
    else:
        holdout_pool = prepared_pool(data, odds, int(min_games), float(min_odds), float(max_odds), holdout_start, end)
        result, holdout = evaluate_pool(holdout_pool, odds, float(edge))
        st.subheader("Untouched holdout results")
        st.caption("This test uses the settings currently shown. Do not change them after inspecting the holdout result and call it independent.")
        if result:
            show_metrics(result)
            st.line_chart(holdout.set_index("Date")["CumulativeProfit"])
            st.dataframe(holdout, use_container_width=True, hide_index=True)

            st.subheader("Probability calibration")
            calibration_metrics, calibration_table = calibration_diagnostics(holdout_pool)
            if calibration_metrics:
                metric_columns = st.columns(5)
                metric_values = [
                    ("Observations", calibration_metrics["Observations"]),
                    ("Model Brier score", f"{calibration_metrics['Brier score - model']:.4f}"),
                    ("Odds Brier score", f"{calibration_metrics['Brier score - odds implied']:.4f}"),
                    ("Mean model probability", f"{calibration_metrics['Mean model probability'] * 100:.1f}%"),
                    ("Actual Over 2.5 rate", f"{calibration_metrics['Actual over 2.5 rate'] * 100:.1f}%"),
                ]
                for metric_column, (label, value) in zip(metric_columns, metric_values):
                    metric_column.metric(label, value)
                st.caption("Lower Brier scores are better. The odds-implied score is a reference benchmark, not a claim that bookmaker prices are perfectly efficient.")
                st.dataframe(calibration_table, use_container_width=True, hide_index=True)

            st.subheader("Benchmark comparison")
            benchmark_result, benchmark_bets = evaluate_pool(holdout_pool, odds, -1.0)
            benchmark_rows = []
            if benchmark_result:
                benchmark_rows.append(
                    {
                        "Strategy": "All eligible matches",
                        "Bets": benchmark_result["Bets"],
                        "Strike rate %": round(benchmark_result["Strike rate"], 2),
                        "Profit": round(benchmark_result["Profit"], 2),
                        "ROI %": round(benchmark_result["ROI"], 2),
                    }
                )
            benchmark_rows.append(
                {
                    "Strategy": f"Model edge >= {edge:.2f}",
                    "Bets": result["Bets"],
                    "Strike rate %": round(result["Strike rate"], 2),
                    "Profit": round(result["Profit"], 2),
                    "ROI %": round(result["ROI"], 2),
                }
            )
            st.dataframe(pd.DataFrame(benchmark_rows), use_container_width=True, hide_index=True)
            st.caption("The benchmark uses the same holdout dates, prior-game requirement and odds range, but does not apply the model-edge filter.")
        else:
            st.warning("No qualifying holdout selections. Lower the edge or move the cutoff earlier, but preserve the original result before changing settings.")

st.caption("Safeguards: chronological features, explicit holdout, sensitivity diagnostics, calibration checks, a simple benchmark, and warnings against selecting settings after seeing holdout results.")
