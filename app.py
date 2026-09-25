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
    return pd.read_csv(io.BytesIO(response.content)), url


st.header("1. Get historical match data")
source = st.radio("Data source", ["Upload CSV", "Import multiple seasons"], horizontal=True)
frames = []
source_name = "Uploaded CSV"

if source == "Upload CSV":
    template = "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HC,AC,HS,AS,HST,AST,HY,AY,HR,AR,HF,AF\n2025-08-16,Arsenal,Leeds,2,0,H,7,3,15,7,6,2,1,2,0,0,9,12\n"
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
                frame, url = download_season(LEAGUES[league_name], season)
                frame["ImportedSeason"] = season
                frames.append(frame)
            except Exception as error:
                errors.append(f"{season}: {error}")
            progress.progress((index + 1) / max(len(chosen_seasons), 1))
        if errors:
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
    matches[column] = pd.to_numeric(matches[column], errors="coerce")
for label, pair in STAT_PAIRS.items():
    for column in pair:
        if column in matches.columns:
            matches[column] = pd.to_numeric(matches[column], errors="coerce")

errors = []
if matches["Date"].isna().any(): errors.append("Some dates are invalid.")
if matches[["FTHG", "FTAG"]].isna().any().any(): errors.append("Some goal values are missing or invalid.")
if (matches[["FTHG", "FTAG"]] < 0).any().any(): errors.append("Goals cannot be negative.")
if not matches["FTR"].isin(["H", "D", "A"]).all(): errors.append("FTR must be H, D or A.")
if errors:
    st.error("Validation issues found:")
    for error in errors: st.write(f"- {error}")
    st.stop()

matches = matches.dropna(subset=["Date", "FTHG", "FTAG"]).copy()
matches["FTHG"] = matches["FTHG"].astype(int)
matches["FTAG"] = matches["FTAG"].astype(int)
matches["TotalGoals"] = matches["FTHG"] + matches["FTAG"]
matches["BTTS"] = (matches["FTHG"] > 0) & (matches["FTAG"] > 0)
matches = matches.sort_values("Date").reset_index(drop=True)

available_stats = {label: pair for label, pair in STAT_PAIRS.items() if all(column in matches.columns for column in pair)}
odds_columns = [column for column in matches.columns if re.search(r"(^B365|^BW|^IW|^PS|^WH|^VC|^Max|^Avg|_C$|Odds|odds)", str(column))]

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
    st.success(f"Historical odds detected: {len(odds_columns)} columns. These can support price-aware backtesting.")
else:
    st.warning("No odds columns detected. Profitability cannot be tested without historical prices.")

st.download_button("Download combined dataset", matches.to_csv(index=False), "combined_football_dataset.csv", "text/csv")
st.subheader("Recent matches")
st.dataframe(matches.sort_values("Date", ascending=False).head(100), use_container_width=True, hide_index=True)

st.header("3. Result breakdown")
counts = matches["FTR"].value_counts().reindex(["H", "D", "A"], fill_value=0)
st.dataframe(pd.DataFrame({"Result": ["Home wins", "Draws", "Away wins"], "Matches": counts.values, "Percentage": (counts.values / len(matches) * 100).round(1)}), use_container_width=True, hide_index=True)

st.header("4. Team form and performance")
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

st.caption("Next: market-specific odds mapping and time-ordered backtesting. No future information is used in the current summaries.")
