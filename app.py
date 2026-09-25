import io
import math
import re

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Football Betting Research Lab", page_icon="⚽", layout="wide")
st.title("⚽ Football Betting Research Lab")
st.write("A transparent dashboard for exploring football results, statistics and historical odds.")
st.info("Research only: this app does not place bets or guarantee profit. Historical patterns are not certain predictions.")

CORE_COLUMNS = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
STAT_PAIRS = {
    "Corners": ("HC", "AC"), "Shots": ("HS", "AS"), "Shots on target": ("HST", "AST"),
    "Yellow cards": ("HY", "AY"), "Red cards": ("HR", "AR"), "Fouls": ("HF", "AF"),
    "Offsides": ("HO", "AO"), "Saves": ("HSave", "ASave"), "Possession %": ("HPoss", "APoss"),
}
LEAGUES = {
    "England Premier League": "E0", "England Championship": "E1", "England League One": "E2",
    "England League Two": "E3", "Scotland Premiership": "SC0", "Germany Bundesliga": "D1",
    "Spain La Liga": "SP1", "Italy Serie A": "I1", "France Ligue 1": "F1", "Netherlands Eredivisie": "N1",
}
SEASONS = ["2026/27", "2025/26", "2024/25", "2023/24", "2022/23", "2021/22", "2020/21", "2019/20", "2018/19", "2017/18"]


def season_code(season):
    start, end = season.split("/")
    return start[-2:] + end[-2:]


def download_season(league_code, season):
    url = f"https://www.football-data.co.uk/mmz4281/{season_code(season)}/{league_code}.csv"
    response = requests.get(url, timeout=30, headers={"User-Agent": "FootballResearchLab/1.0"})
    response.raise_for_status()
    if len(response.content) < 100:
        raise ValueError("The source returned an unexpectedly small file.")
    return pd.read_csv(io.BytesIO(response.content))


def numeric(value):
    return pd.to_numeric(value, errors="coerce")


def max_drawdown(profits):
    curve = profits.cumsum()
    return float((curve.cummax() - curve).max()) if len(curve) else 0.0


def backtest(frame, odds_column, outcome_column, winning_value, minimum_odds, maximum_odds, start_date, end_date):
    data = frame[["Date", "HomeTeam", "AwayTeam", odds_column, outcome_column]].copy()
    data[odds_column] = numeric(data[odds_column])
    data = data.dropna(subset=["Date", odds_column, outcome_column])
    data = data[(data["Date"] >= pd.Timestamp(start_date)) & (data["Date"] <= pd.Timestamp(end_date))]
    data = data[(data[odds_column] >= minimum_odds) & (data[odds_column] <= maximum_odds)].copy()
    if data.empty:
        return None, data
    data["Won"] = data[outcome_column] == winning_value
    data["Profit"] = data[odds_column].where(data["Won"], 0) - 1
    data["CumulativeProfit"] = data["Profit"].cumsum()
    summary = {
        "Bets": int(len(data)), "Wins": int(data["Won"].sum()),
        "Strike rate": float(data["Won"].mean() * 100), "Profit": float(data["Profit"].sum()),
        "ROI": float(data["Profit"].sum() / len(data) * 100), "Average odds": float(data[odds_column].mean()),
        "Break-even rate": float((1 / data[odds_column].mean()) * 100),
        "Max drawdown": max_drawdown(data["Profit"]),
    }
    return summary, data


def show_summary(summary):
    cols = st.columns(7)
    cols[0].metric("Bets", summary["Bets"])
    cols[1].metric("Wins", summary["Wins"])
    cols[2].metric("Strike rate", f"{summary['Strike rate']:.1f}%")
    cols[3].metric("Profit", f"{summary['Profit']:+.2f} units")
    cols[4].metric("ROI", f"{summary['ROI']:+.2f}%")
    cols[5].metric("Break-even", f"{summary.get('Break-even rate', 0):.1f}%")
    cols[6].metric("Max drawdown", f"{summary['Max drawdown']:.2f} units")


def poisson_over_25(expected_goals):
    expected_goals = max(float(expected_goals), 0.05)
    under_or_equal_two = math.exp(-expected_goals) * (1 + expected_goals + (expected_goals ** 2) / 2)
    return max(0.0, min(1.0, 1 - under_or_equal_two))


def build_pre_match_features(frame):
    ordered = frame.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
    histories = {}
    rows = []

    def team_summary(team):
        history = histories.get(team, [])
        if not history:
            return {"games": 0, "for": None, "against": None}
        return {"games": len(history), "for": sum(x[0] for x in history) / len(history), "against": sum(x[1] for x in history) / len(history)}

    for _, match in ordered.iterrows():
        home, away = team_summary(match["HomeTeam"]), team_summary(match["AwayTeam"])
        home_parts = [x for x in [home["for"], away["against"]] if x is not None]
        away_parts = [x for x in [away["for"], home["against"]] if x is not None]
        expected_home = sum(home_parts) / len(home_parts) if home_parts else None
        expected_away = sum(away_parts) / len(away_parts) if away_parts else None
        expected_total = expected_home + expected_away if expected_home is not None and expected_away is not None else None
        probability = poisson_over_25(expected_total) if expected_total is not None else None
        rows.append({
            "Date": match["Date"], "HomeTeam": match["HomeTeam"], "AwayTeam": match["AwayTeam"],
            "PreMatchHomeGames": home["games"], "PreMatchAwayGames": away["games"],
            "ExpectedHomeGoals": expected_home, "ExpectedAwayGoals": expected_away,
            "ExpectedTotalGoals": expected_total, "ModelOver25Probability": probability,
        })
        histories.setdefault(match["HomeTeam"], []).append((float(match["FTHG"]), float(match["FTAG"])))
        histories.setdefault(match["AwayTeam"], []).append((float(match["FTAG"]), float(match["FTHG"])))

    return ordered.merge(pd.DataFrame(rows), on=["Date", "HomeTeam", "AwayTeam"], how="left")


def add_test_season(data):
    dates = pd.to_datetime(data["Date"])
    start_year = dates.dt.year.where(dates.dt.month >= 7, dates.dt.year - 1)
    data["TestSeason"] = start_year.astype(int).astype(str) + "/" + (start_year + 1).astype(int).astype(str).str[-2:]
    return data


def walk_forward_over25(frame, odds_column, minimum_games, minimum_edge, minimum_odds, maximum_odds, start_date, end_date):
    features = build_pre_match_features(frame)
    features[odds_column] = numeric(features[odds_column])
    features["ImpliedProbability"] = 1 / features[odds_column]
    features["Edge"] = features["ModelOver25Probability"] - features["ImpliedProbability"]
    eligible = features[
        (features["Date"] >= pd.Timestamp(start_date)) & (features["Date"] <= pd.Timestamp(end_date))
        & (features["PreMatchHomeGames"] >= minimum_games) & (features["PreMatchAwayGames"] >= minimum_games)
        & features["ModelOver25Probability"].notna() & features[odds_column].notna()
        & (features[odds_column] >= minimum_odds) & (features[odds_column] <= maximum_odds)
        & (features["Edge"] >= minimum_edge)
    ].copy()
    if eligible.empty:
        return None, eligible
    eligible["Won"] = (eligible["FTHG"] + eligible["FTAG"]) > 2
    eligible["Profit"] = eligible[odds_column].where(eligible["Won"], 0) - 1
    eligible["CumulativeProfit"] = eligible["Profit"].cumsum()
    eligible = add_test_season(eligible)
    summary = {
        "Bets": int(len(eligible)), "Wins": int(eligible["Won"].sum()),
        "Strike rate": float(eligible["Won"].mean() * 100), "Profit": float(eligible["Profit"].sum()),
        "ROI": float(eligible["Profit"].sum() / len(eligible) * 100),
        "Average odds": float(eligible[odds_column].mean()), "Average edge": float(eligible["Edge"].mean() * 100),
        "Max drawdown": max_drawdown(eligible["Profit"]),
    }
    return summary, eligible


def roi_confidence_interval(profits, iterations=500, seed=42):
    if len(profits) < 2:
        return None, None
    rng = __import__("numpy").random.default_rng(seed)
    values = __import__("numpy").asarray(profits, dtype=float)
    samples = rng.choice(values, size=(iterations, len(values)), replace=True).mean(axis=1) * 100
    return float(__import__("numpy").percentile(samples, 2.5)), float(__import__("numpy").percentile(samples, 97.5))


st.header("1. Get historical match data")
source = st.radio("Data source", ["Upload CSV", "Import multiple seasons"], horizontal=True)
frames, source_name = [], "Uploaded CSV"
if source == "Upload CSV":
    template = "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HC,AC,HS,AS,HST,AST,HY,AY,HR,AR,HF,AF,B365H,B365D,B365A,B365>2.5,B365<2.5\n2025-08-16,Arsenal,Leeds,2,0,H,7,3,15,7,6,2,1,2,0,0,9,12,1.5,4.2,6.5,1.8,2.0\n"
    st.download_button("Download CSV template", template, "football_results_template.csv", "text/csv")
    uploaded = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded is not None:
        frames = [pd.read_csv(uploaded)]
else:
    left, right = st.columns(2)
    with left:
        league_name = st.selectbox("League", list(LEAGUES.keys()), index=0)
    with right:
        chosen_seasons = st.multiselect("Seasons to combine", SEASONS, default=["2025/26", "2024/25", "2023/24"])
    if st.button("Import selected seasons", type="primary"):
        progress, errors = st.progress(0), []
        for index, season in enumerate(chosen_seasons):
            try:
                frame = download_season(LEAGUES[league_name], season)
                frame["ImportedSeason"] = season
                frames.append(frame)
            except Exception as error:
                errors.append(f"{season}: {error}")
            progress.progress((index + 1) / max(len(chosen_seasons), 1))
        for error in errors:
            st.warning(error)
        if frames:
            st.session_state["multi_season_frames"] = frames
            st.session_state["multi_season_source"] = f"{league_name} — {', '.join(chosen_seasons)}"
            st.success(f"Downloaded {len(frames)} season file(s).")
    frames = st.session_state.get("multi_season_frames", frames)
    source_name = st.session_state.get("multi_season_source", source_name)

if not frames:
    st.warning("Upload a CSV or import one or more seasons to begin.")
    st.stop()

matches = pd.concat(frames, ignore_index=True, sort=False)
rename_map = {"Home Team": "HomeTeam", "Away Team": "AwayTeam", "HomeGoals": "FTHG", "AwayGoals": "FTAG", "FullTimeHomeGoals": "FTHG", "FullTimeAwayGoals": "FTAG", "FullTimeResult": "FTR"}
matches = matches.rename(columns={k: v for k, v in rename_map.items() if k in matches.columns})
missing = [column for column in CORE_COLUMNS if column not in matches.columns]
if missing:
    st.error("Missing required columns: " + ", ".join(missing))
    st.write("Columns found:", ", ".join(map(str, matches.columns)))
    st.stop()

matches["Date"] = pd.to_datetime(matches["Date"], errors="coerce", dayfirst=True)
matches["FTR"] = matches["FTR"].astype(str).str.upper().str.strip()
for column in ["FTHG", "FTAG"]:
    matches[column] = numeric(matches[column])
for pair in STAT_PAIRS.values():
    for column in pair:
        if column in matches.columns:
            matches[column] = numeric(matches[column])
matches = matches.dropna(subset=["Date", "FTHG", "FTAG"]).copy()
if not matches["FTR"].isin(["H", "D", "A"]).all():
    st.error("Some result values are not H, D or A. Check the uploaded data.")
    st.stop()
matches["FTHG"], matches["FTAG"] = matches["FTHG"].astype(int), matches["FTAG"].astype(int)
matches["TotalGoals"] = matches["FTHG"] + matches["FTAG"]
matches["BTTS"] = (matches["FTHG"] > 0) & (matches["FTAG"] > 0)
matches = matches.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
available_stats = {label: pair for label, pair in STAT_PAIRS.items() if all(column in matches.columns for column in pair)}
odds_columns = [column for column in matches.columns if re.search(r"(^B365|^BW|^IW|^PS|^WH|^VC|^Max|^Avg|Odds|odds)", str(column))]

st.success(f"Validation passed: {len(matches):,} matches loaded from {source_name}.")
st.header("2. Dataset overview")
metrics = st.columns(6)
metrics[0].metric("Matches", f"{len(matches):,}")
metrics[1].metric("Teams", f"{pd.unique(matches[['HomeTeam', 'AwayTeam']].values.ravel()).size:,}")
metrics[2].metric("Average goals", f"{matches['TotalGoals'].mean():.2f}")
metrics[3].metric("BTTS", f"{matches['BTTS'].mean() * 100:.1f}%")
metrics[4].metric("Stat groups", len(available_stats))
metrics[5].metric("Odds columns", len(odds_columns))
if available_stats:
    st.success("Statistics detected: " + ", ".join(available_stats.keys()))
if odds_columns:
    st.success(f"Historical odds detected: {len(odds_columns)} columns.")
else:
    st.warning("No odds columns detected. Profitability cannot be tested without historical prices.")
st.download_button("Download combined dataset", matches.to_csv(index=False), "combined_football_dataset.csv", "text/csv")
st.subheader("Recent matches")
st.dataframe(matches.sort_values("Date", ascending=False).head(100), use_container_width=True, hide_index=True)

st.header("3. Result breakdown")
counts = matches["FTR"].value_counts().reindex(["H", "D", "A"], fill_value=0)
st.dataframe(pd.DataFrame({"Result": ["Home wins", "Draws", "Away wins"], "Matches": counts.values, "Percentage": (counts.values / len(matches) * 100).round(1)}), use_container_width=True, hide_index=True)

st.header("4. Market backtesting")
min_date, max_date = matches["Date"].min().date(), matches["Date"].max().date()
settings_left, settings_mid, settings_right = st.columns(3)
with settings_left:
    start_date = st.date_input("Start date", min_date, min_value=min_date, max_value=max_date)
with settings_mid:
    end_date = st.date_input("End date", max_date, min_value=min_date, max_value=max_date)
with settings_right:
    max_odds = st.number_input("Maximum odds", min_value=1.01, max_value=20.0, value=10.0, step=0.25)
if start_date > end_date:
    st.error("Start date must be before end date.")
    st.stop()

one_x_two_options = [c for c in ["B365H", "AvgH", "MaxH", "BWH", "IWH", "PSH", "WH", "VCH"] if c in matches.columns]
draw_options = [c for c in ["B365D", "AvgD", "MaxD", "BWD", "IWD", "PSD", "WD", "VCD"] if c in matches.columns]
away_options = [c for c in ["B365A", "AvgA", "MaxA", "BWA", "IWA", "PSA", "WA", "VCA"] if c in matches.columns]
over_options = [c for c in ["B365>2.5", "Avg>2.5", "Max>2.5", "P>2.5"] if c in matches.columns]
under_options = [c for c in ["B365<2.5", "Avg<2.5", "Max<2.5", "P<2.5"] if c in matches.columns]
market_tab, totals_tab, comparison_tab = st.tabs(["1X2", "Goals totals", "Threshold comparison"])
with market_tab:
    market_choice = st.selectbox("1X2 selection", ["Home win", "Draw", "Away win"])
    market_columns = {"Home win": one_x_two_options, "Draw": draw_options, "Away win": away_options}
    outcome_values = {"Home win": "H", "Draw": "D", "Away win": "A"}
    selected_market_column = st.selectbox("Odds source", market_columns[market_choice]) if market_columns[market_choice] else None
    minimum_odds = st.slider("Minimum odds", 1.01, 5.00, 1.50, 0.05)
    if selected_market_column:
        summary, tested = backtest(matches, selected_market_column, "FTR", outcome_values[market_choice], minimum_odds, max_odds, start_date, end_date)
        if summary:
            show_summary(summary); st.line_chart(tested.set_index("Date")["CumulativeProfit"]); st.dataframe(tested.head(100), use_container_width=True, hide_index=True)
        else: st.warning("No qualifying bets were found with those settings.")
    else: st.warning("No compatible 1X2 odds columns were found in this dataset.")
with totals_tab:
    total_choice = st.selectbox("Goals market", ["Over 2.5 goals", "Under 2.5 goals"])
    total_columns = over_options if total_choice == "Over 2.5 goals" else under_options
    total_column = st.selectbox("Odds source", total_columns) if total_columns else None
    minimum_total_odds = st.slider("Minimum odds for totals", 1.01, 5.00, 1.50, 0.05)
    if total_column:
        data = matches.copy(); data["TotalOutcome"] = (data["TotalGoals"] > 2.5) if total_choice == "Over 2.5 goals" else (data["TotalGoals"] < 2.5)
        summary, tested = backtest(data, total_column, "TotalOutcome", True, minimum_total_odds, max_odds, start_date, end_date)
        if summary:
            show_summary(summary); st.line_chart(tested.set_index("Date")["CumulativeProfit"]); st.dataframe(tested.head(100), use_container_width=True, hide_index=True)
        else: st.warning("No qualifying bets were found with those settings.")
    else: st.warning("No compatible over/under 2.5 odds columns were found in this dataset.")
with comparison_tab:
    st.write("Compare several minimum-odds thresholds over the same date range. This is descriptive, not a guarantee of future performance.")
    comparison_market = st.selectbox("Comparison market", ["Over 2.5 goals", "Under 2.5 goals", "Home win", "Draw", "Away win"])
    if comparison_market == "Over 2.5 goals":
        comparison_columns, comparison_outcome, comparison_value, comparison_frame = over_options, "TotalOutcome", True, matches.copy(); comparison_frame["TotalOutcome"] = comparison_frame["TotalGoals"] > 2.5
    elif comparison_market == "Under 2.5 goals":
        comparison_columns, comparison_outcome, comparison_value, comparison_frame = under_options, "TotalOutcome", True, matches.copy(); comparison_frame["TotalOutcome"] = comparison_frame["TotalGoals"] < 2.5
    else:
        comparison_columns = {"Home win": one_x_two_options, "Draw": draw_options, "Away win": away_options}[comparison_market]; comparison_outcome, comparison_value, comparison_frame = "FTR", {"Home win": "H", "Draw": "D", "Away win": "A"}[comparison_market], matches
    if comparison_columns:
        comparison_column = st.selectbox("Comparison odds source", comparison_columns)
        rows = []
        for threshold in [1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 3.00]:
            result, _ = backtest(comparison_frame, comparison_column, comparison_outcome, comparison_value, threshold, max_odds, start_date, end_date)
            if result:
                rows.append({"Minimum odds": threshold, "Bets": result["Bets"], "Strike rate %": round(result["Strike rate"], 2), "ROI %": round(result["ROI"], 2), "Profit units": round(result["Profit"], 2), "Max drawdown": round(result["Max drawdown"], 2)})
        if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else: st.warning("No comparison results were available.")
    else: st.warning("No compatible odds columns were found for this market.")

st.header("5. Team form and performance")
teams = sorted(pd.unique(matches[["HomeTeam", "AwayTeam"]].values.ravel()))
selected_team = st.selectbox("Choose a team", teams)
home, away = matches[matches["HomeTeam"] == selected_team].copy(), matches[matches["AwayTeam"] == selected_team].copy()
home["TeamGoalsFor"], home["TeamGoalsAgainst"], home["TeamResult"] = home["FTHG"], home["FTAG"], home["FTR"].map({"H": "W", "D": "D", "A": "L"})
away["TeamGoalsFor"], away["TeamGoalsAgainst"], away["TeamResult"] = away["FTAG"], away["FTHG"], away["FTR"].map({"A": "W", "D": "D", "H": "L"})
team_matches = pd.concat([home, away], ignore_index=True).sort_values("Date", ascending=False)
wins, draws, losses = int((team_matches["TeamResult"] == "W").sum()), int((team_matches["TeamResult"] == "D").sum()), int((team_matches["TeamResult"] == "L").sum())
team_metrics = st.columns(4); team_metrics[0].metric("Games", len(team_matches)); team_metrics[1].metric("Wins", wins); team_metrics[2].metric("Draws", draws); team_metrics[3].metric("Losses", losses)
if len(team_matches): st.write(f"**{selected_team}:** {wins * 3 + draws} points · {int(team_matches['TeamGoalsFor'].sum())} scored · {int(team_matches['TeamGoalsAgainst'].sum())} conceded · {team_matches['TeamGoalsFor'].mean():.2f} goals per game.")
st.subheader("Last five matches")
last_five = team_matches.head(5).copy(); last_five["Date"] = last_five["Date"].dt.strftime("%Y-%m-%d")
st.dataframe(last_five[["Date", "HomeTeam", "AwayTeam", "TeamGoalsFor", "TeamGoalsAgainst", "TeamResult"]], use_container_width=True, hide_index=True)
st.subheader("Team statistics")
if available_stats and len(team_matches):
    rows = []
    for label, (home_col, away_col) in available_stats.items():
        values = [row[home_col] if row["HomeTeam"] == selected_team else row[away_col] for _, row in team_matches.iterrows()]
        rows.append({"Statistic": label, "Team average per match": round(pd.Series(values).dropna().mean(), 2)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else: st.info("Upload a dataset containing optional statistics to see team-level averages.")

st.header("6. Walk-forward research")
st.write("This section creates pre-match team-strength features using only earlier matches, then evaluates a simple Over 2.5 model on later fixtures. It is deliberately transparent and should not be treated as a proven betting edge.")
wf_results = pd.DataFrame(); wf_summary = None
if over_options:
    wf_left, wf_mid, wf_right = st.columns(3)
    with wf_left: wf_odds_column = st.selectbox("Walk-forward odds source", over_options)
    with wf_mid: wf_min_games = st.number_input("Minimum prior games per team", min_value=1, max_value=20, value=5, step=1)
    with wf_right: wf_min_edge = st.slider("Minimum model edge", 0.00, 0.20, 0.05, 0.01, format="%.2f")
    wf_min_odds = st.number_input("Walk-forward minimum odds", min_value=1.01, max_value=10.0, value=1.50, step=0.05)
    if st.button("Run walk-forward evaluation", type="primary"):
        with st.spinner("Building strictly pre-match features and evaluating the test..."):
            wf_summary, wf_results = walk_forward_over25(matches, wf_odds_column, int(wf_min_games), float(wf_min_edge), float(wf_min_odds), float(max_odds), start_date, end_date)
        if wf_summary:
            wf_cols = st.columns(7); wf_cols[0].metric("Bets", wf_summary["Bets"]); wf_cols[1].metric("Wins", wf_summary["Wins"]); wf_cols[2].metric("Strike rate", f"{wf_summary['Strike rate']:.1f}%"); wf_cols[3].metric("Profit", f"{wf_summary['Profit']:+.2f} units"); wf_cols[4].metric("ROI", f"{wf_summary['ROI']:+.2f}%"); wf_cols[5].metric("Avg edge", f"{wf_summary['Average edge']:.2f}%"); wf_cols[6].metric("Max drawdown", f"{wf_summary['Max drawdown']:.2f}")
            st.line_chart(wf_results.set_index("Date")["CumulativeProfit"])
            st.dataframe(wf_results[["Date", "HomeTeam", "AwayTeam", "ExpectedTotalGoals", "ModelOver25Probability", "ImpliedProbability", "Edge", wf_odds_column, "Won", "Profit", "CumulativeProfit"]].head(200), use_container_width=True, hide_index=True)
        else: st.warning("No qualifying walk-forward selections were found. Try a lower edge or minimum-games requirement.")
else: st.warning("No Over 2.5 odds columns are available for walk-forward evaluation.")

st.header("7. Robustness and stability checks")
st.write("This section checks whether the walk-forward result is sensitive to model edge, odds ceiling and season. It is a research diagnostic, not a guarantee that any setting will remain profitable.")
if over_options:
    rb_left, rb_mid, rb_right = st.columns(3)
    with rb_left: rb_odds_column = st.selectbox("Robustness odds source", over_options, key="rb_odds")
    with rb_mid: rb_min_games = st.number_input("Robustness minimum prior games", min_value=1, max_value=20, value=5, step=1, key="rb_games")
    with rb_right: rb_min_odds = st.number_input("Robustness minimum odds", min_value=1.01, max_value=10.0, value=1.50, step=0.05, key="rb_min_odds")
    if st.button("Run robustness checks", type="secondary"):
        with st.spinner("Running sensitivity grid and season breakdown..."):
            robustness_rows = []
            for edge in [0.00, 0.03, 0.05, 0.07, 0.10]:
                for ceiling in [1.75, 2.00, 2.50, 3.00, 5.00]:
                    result, tested = walk_forward_over25(matches, rb_odds_column, int(rb_min_games), edge, float(rb_min_odds), ceiling, start_date, end_date)
                    if result:
                        low, high = roi_confidence_interval(tested["Profit"].tolist())
                        robustness_rows.append({"Minimum edge": edge, "Max odds": ceiling, "Bets": result["Bets"], "ROI %": round(result["ROI"], 2), "Profit": round(result["Profit"], 2), "Max drawdown": round(result["Max drawdown"], 2), "Bootstrap ROI low %": round(low, 2) if low is not None else None, "Bootstrap ROI high %": round(high, 2) if high is not None else None})
            if robustness_rows:
                robustness_table = pd.DataFrame(robustness_rows).sort_values(["ROI %", "Bets"], ascending=[False, False])
                st.subheader("Sensitivity grid")
                st.dataframe(robustness_table, use_container_width=True, hide_index=True)
                st.caption("The bootstrap interval describes variation in the observed bet sample; it does not account for model selection, market changes or all sources of uncertainty.")

                best_edge = float(robustness_table.iloc[0]["Minimum edge"])
                best_ceiling = float(robustness_table.iloc[0]["Max odds"])
                _, season_test = walk_forward_over25(matches, rb_odds_column, int(rb_min_games), best_edge, float(rb_min_odds), best_ceiling, start_date, end_date)
                if not season_test.empty:
                    season_rows = []
                    for season, group in season_test.groupby("TestSeason"):
                        season_rows.append({"Test season": season, "Bets": len(group), "Wins": int(group["Won"].sum()), "Strike rate %": round(group["Won"].mean() * 100, 2), "Profit": round(group["Profit"].sum(), 2), "ROI %": round(group["Profit"].sum() / len(group) * 100, 2), "Max drawdown": round(max_drawdown(group["Profit"]), 2)})
                    st.subheader("Season-by-season breakdown for the highest-ROI grid row")
                    st.dataframe(pd.DataFrame(season_rows), use_container_width=True, hide_index=True)
                    st.warning("The highest-ROI row is descriptive only. It was selected after comparing settings, so it must not be treated as an untouched final test.")
            else:
                st.warning("No robustness configurations produced qualifying selections.")
else:
    st.warning("No Over 2.5 odds columns are available for robustness checks.")

st.caption("Research safeguards: historical results are descriptive; model features are calculated chronologically; positive backtest results do not establish future profitability; sensitivity results are vulnerable to selection bias when settings are chosen after inspection.")
