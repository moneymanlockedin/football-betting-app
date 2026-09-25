import io
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


def backtest(frame, odds_column, outcome_column, winning_value, minimum_odds, maximum_odds, start_date, end_date):
    columns = ["Date", "HomeTeam", "AwayTeam", odds_column, outcome_column]
    data = frame[columns].copy()
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
        "Bets": int(len(data)),
        "Wins": int(data["Won"].sum()),
        "Strike rate": float(data["Won"].mean() * 100),
        "Profit": float(data["Profit"].sum()),
        "ROI": float(data["Profit"].sum() / len(data) * 100),
        "Average odds": float(data[odds_column].mean()),
        "Break-even rate": float((1 / data[odds_column].mean()) * 100),
        "Max drawdown": float((data["CumulativeProfit"].cummax() - data["CumulativeProfit"]).max()),
    }
    return summary, data


def show_summary(summary):
    cols = st.columns(7)
    cols[0].metric("Bets", summary["Bets"])
    cols[1].metric("Wins", summary["Wins"])
    cols[2].metric("Strike rate", f"{summary['Strike rate']:.1f}%")
    cols[3].metric("Profit", f"{summary['Profit']:+.2f} units")
    cols[4].metric("ROI", f"{summary['ROI']:+.2f}%")
    cols[5].metric("Break-even", f"{summary['Break-even rate']:.1f}%")
    cols[6].metric("Max drawdown", f"{summary['Max drawdown']:.2f} units")


st.header("1. Get historical match data")
source = st.radio("Data source", ["Upload CSV", "Import multiple seasons"], horizontal=True)
frames = []
source_name = "Uploaded CSV"

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
        progress = st.progress(0)
        errors = []
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
rename_map = {
    "Home Team": "HomeTeam", "Away Team": "AwayTeam", "HomeGoals": "FTHG", "AwayGoals": "FTAG",
    "FullTimeHomeGoals": "FTHG", "FullTimeAwayGoals": "FTAG", "FullTimeResult": "FTR",
}
matches = matches.rename(columns={key: value for key, value in rename_map.items() if key in matches.columns})
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
matches["FTHG"] = matches["FTHG"].astype(int)
matches["FTAG"] = matches["FTAG"].astype(int)
matches["TotalGoals"] = matches["FTHG"] + matches["FTAG"]
matches["BTTS"] = (matches["FTHG"] > 0) & (matches["FTAG"] > 0)
matches = matches.sort_values("Date").reset_index(drop=True)

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
st.write("Use the date window and odds bounds to test a strategy without cherry-picking only a convenient part of the data.")
min_date = matches["Date"].min().date()
max_date = matches["Date"].max().date()
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

one_x_two_options = [column for column in ["B365H", "AvgH", "MaxH", "BWH", "IWH", "PSH", "WH", "VCH"] if column in matches.columns]
draw_options = [column for column in ["B365D", "AvgD", "MaxD", "BWD", "IWD", "PSD", "WD", "VCD"] if column in matches.columns]
away_options = [column for column in ["B365A", "AvgA", "MaxA", "BWA", "IWA", "PSA", "WA", "VCA"] if column in matches.columns]
over_options = [column for column in ["B365>2.5", "Avg>2.5", "Max>2.5", "P>2.5"] if column in matches.columns]
under_options = [column for column in ["B365<2.5", "Avg<2.5", "Max<2.5", "P<2.5"] if column in matches.columns]

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
            show_summary(summary)
            st.line_chart(tested.set_index("Date")["CumulativeProfit"])
            st.dataframe(tested.head(100), use_container_width=True, hide_index=True)
        else:
            st.warning("No qualifying bets were found with those settings.")
    else:
        st.warning("No compatible 1X2 odds columns were found in this dataset.")

with totals_tab:
    total_choice = st.selectbox("Goals market", ["Over 2.5 goals", "Under 2.5 goals"])
    total_columns = over_options if total_choice == "Over 2.5 goals" else under_options
    total_column = st.selectbox("Odds source", total_columns) if total_columns else None
    minimum_total_odds = st.slider("Minimum odds for totals", 1.01, 5.00, 1.50, 0.05)
    if total_column:
        data = matches.copy()
        data["TotalOutcome"] = (data["TotalGoals"] > 2.5) if total_choice == "Over 2.5 goals" else (data["TotalGoals"] < 2.5)
        summary, tested = backtest(data, total_column, "TotalOutcome", True, minimum_total_odds, max_odds, start_date, end_date)
        if summary:
            show_summary(summary)
            st.line_chart(tested.set_index("Date")["CumulativeProfit"])
            st.dataframe(tested.head(100), use_container_width=True, hide_index=True)
        else:
            st.warning("No qualifying bets were found with those settings.")
    else:
        st.warning("No compatible over/under 2.5 odds columns were found in this dataset.")

with comparison_tab:
    st.write("Compare several minimum-odds thresholds over the same date range. This helps reveal whether a result depends on one hand-picked cutoff.")
    comparison_market = st.selectbox("Comparison market", ["Over 2.5 goals", "Under 2.5 goals", "Home win", "Draw", "Away win"])
    if comparison_market == "Over 2.5 goals":
        comparison_columns = over_options
        comparison_outcome = "TotalOutcome"
        comparison_value = True
        comparison_frame = matches.copy()
        comparison_frame["TotalOutcome"] = comparison_frame["TotalGoals"] > 2.5
    elif comparison_market == "Under 2.5 goals":
        comparison_columns = under_options
        comparison_outcome = "TotalOutcome"
        comparison_value = True
        comparison_frame = matches.copy()
        comparison_frame["TotalOutcome"] = comparison_frame["TotalGoals"] < 2.5
    else:
        comparison_columns = {"Home win": one_x_two_options, "Draw": draw_options, "Away win": away_options}[comparison_market]
        comparison_outcome = "FTR"
        comparison_value = {"Home win": "H", "Draw": "D", "Away win": "A"}[comparison_market]
        comparison_frame = matches
    if comparison_columns:
        comparison_column = st.selectbox("Comparison odds source", comparison_columns)
        rows = []
        for threshold in [1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 3.00]:
            result, _ = backtest(comparison_frame, comparison_column, comparison_outcome, comparison_value, threshold, max_odds, start_date, end_date)
            if result:
                rows.append({"Minimum odds": threshold, "Bets": result["Bets"], "Strike rate %": round(result["Strike rate"], 2), "ROI %": round(result["ROI"], 2), "Profit units": round(result["Profit"], 2), "Max drawdown": round(result["Max drawdown"], 2)})
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.warning("No comparison results were available.")
    else:
        st.warning("No compatible odds columns were found for this market.")

st.header("5. Team form and performance")
teams = sorted(pd.unique(matches[["HomeTeam", "AwayTeam"]].values.ravel()))
selected_team = st.selectbox("Choose a team", teams)
home = matches[matches["HomeTeam"] == selected_team].copy()
away = matches[matches["AwayTeam"] == selected_team].copy()
home["TeamGoalsFor"], home["TeamGoalsAgainst"] = home["FTHG"], home["FTAG"]
home["TeamResult"] = home["FTR"].map({"H": "W", "D": "D", "A": "L"})
away["TeamGoalsFor"], away["TeamGoalsAgainst"] = away["FTAG"], away["FTHG"]
away["TeamResult"] = away["FTR"].map({"A": "W", "D": "D", "H": "L"})
team_matches = pd.concat([home, away], ignore_index=True).sort_values("Date", ascending=False)
wins = int((team_matches["TeamResult"] == "W").sum())
draws = int((team_matches["TeamResult"] == "D").sum())
losses = int((team_matches["TeamResult"] == "L").sum())
team_metrics = st.columns(4)
team_metrics[0].metric("Games", len(team_matches))
team_metrics[1].metric("Wins", wins)
team_metrics[2].metric("Draws", draws)
team_metrics[3].metric("Losses", losses)
if len(team_matches):
    st.write(f"**{selected_team}:** {wins * 3 + draws} points · {int(team_matches['TeamGoalsFor'].sum())} scored · {int(team_matches['TeamGoalsAgainst'].sum())} conceded · {team_matches['TeamGoalsFor'].mean():.2f} goals per game.")

st.subheader("Last five matches")
last_five = team_matches.head(5).copy()
last_five["Date"] = last_five["Date"].dt.strftime("%Y-%m-%d")
st.dataframe(last_five[["Date", "HomeTeam", "AwayTeam", "TeamGoalsFor", "TeamGoalsAgainst", "TeamResult"]], use_container_width=True, hide_index=True)

st.subheader("Team statistics")
if available_stats and len(team_matches):
    rows = []
    for label, (home_col, away_col) in available_stats.items():
        values = [row[home_col] if row["HomeTeam"] == selected_team else row[away_col] for _, row in team_matches.iterrows()]
        rows.append({"Statistic": label, "Team average per match": round(pd.Series(values).dropna().mean(), 2)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Upload a dataset containing optional statistics to see team-level averages.")

st.caption("Next: pre-match team-strength features and walk-forward model evaluation. No future information is used in the current summaries.")
