import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Football Betting Research Lab",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Football Betting Research Lab")
st.write("A transparent research dashboard for exploring football results, team form and match statistics.")

st.info(
    "This is a research tool using historical data. It does not place bets or guarantee profit. "
    "Statistics describe past results and are not certain predictions."
)

st.header("1. Upload historical match results")
st.write(
    "Upload a CSV with one row per match. The six core columns are required; the additional statistics are optional."
)

sample_csv = (
    "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HC,AC,HS,AS,HST,AST,HY,AY,HR,AR,HPoss,APoss,HF,AF\n"
    "2025-08-16,Arsenal,Leeds,2,0,H,7,3,15,7,6,2,1,2,0,0,58,42,9,12\n"
    "2025-08-17,Chelsea,Fulham,1,1,D,5,4,12,10,4,4,2,3,0,0,54,46,11,10\n"
    "2025-08-18,Liverpool,Newcastle,3,1,H,8,2,18,8,8,3,1,1,0,0,61,39,7,14\n"
)

st.download_button(
    "Download example CSV template",
    data=sample_csv,
    file_name="football_results_template_stage2.csv",
    mime="text/csv",
)

uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])

if uploaded_file is None:
    st.warning("Upload a CSV file to begin analysing your historical results.")
    st.subheader("Required columns")
    st.code("Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR")
    st.subheader("Optional statistics supported")
    st.write(
        "Corners: HC, AC · Shots: HS, AS · Shots on target: HST, AST · "
        "Yellow cards: HY, AY · Red cards: HR, AR · Possession: HPoss, APoss · "
        "Fouls: HF, AF · Offsides: HO, AO · Saves: HSave, ASave · "
        "Passes: HPass, APass · Expected goals: HxG, AxG"
    )
    st.stop()

try:
    matches = pd.read_csv(uploaded_file)
except Exception as error:
    st.error(f"The CSV could not be read: {error}")
    st.stop()

required_columns = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
missing_columns = [column for column in required_columns if column not in matches.columns]

if missing_columns:
    st.error("Your CSV is missing these required columns: " + ", ".join(missing_columns))
    st.write("Columns found in your file:", ", ".join(matches.columns.astype(str)))
    st.stop()

optional_stat_pairs = {
    "Corners": ("HC", "AC"),
    "Shots": ("HS", "AS"),
    "Shots on target": ("HST", "AST"),
    "Yellow cards": ("HY", "AY"),
    "Red cards": ("HR", "AR"),
    "Possession %": ("HPoss", "APoss"),
    "Fouls": ("HF", "AF"),
    "Offsides": ("HO", "AO"),
    "Saves": ("HSave", "ASave"),
    "Passes": ("HPass", "APass"),
    "Expected goals": ("HxG", "AxG"),
}

base_columns = required_columns.copy()
available_stat_pairs = {}
for label, (home_col, away_col) in optional_stat_pairs.items():
    if home_col in matches.columns and away_col in matches.columns:
        available_stat_pairs[label] = (home_col, away_col)
        base_columns.extend([home_col, away_col])

matches = matches[base_columns].copy()
matches["Date"] = pd.to_datetime(matches["Date"], errors="coerce", dayfirst=True)
matches["FTHG"] = pd.to_numeric(matches["FTHG"], errors="coerce")
matches["FTAG"] = pd.to_numeric(matches["FTAG"], errors="coerce")
matches["FTR"] = matches["FTR"].astype(str).str.upper().str.strip()

validation_errors = []

if matches["Date"].isna().any():
    validation_errors.append("Some Date values could not be understood.")
if matches[["FTHG", "FTAG"]].isna().any().any():
    validation_errors.append("Some home or away goal values are missing or invalid.")
if (matches[["FTHG", "FTAG"]] < 0).any().any():
    validation_errors.append("Goals cannot be negative.")
if not matches["FTR"].isin(["H", "D", "A"]).all():
    validation_errors.append("FTR must contain only H (home win), D (draw), or A (away win).")
if matches["HomeTeam"].astype(str).str.strip().eq("").any() or matches["AwayTeam"].astype(str).str.strip().eq("").any():
    validation_errors.append("HomeTeam and AwayTeam cannot be blank.")

for label, (home_col, away_col) in available_stat_pairs.items():
    matches[home_col] = pd.to_numeric(matches[home_col], errors="coerce")
    matches[away_col] = pd.to_numeric(matches[away_col], errors="coerce")
    if matches[[home_col, away_col]].isna().any().any():
        validation_errors.append(f"Some {label.lower()} values are missing or invalid.")
    if label != "Possession %" and (matches[[home_col, away_col]] < 0).any().any():
        validation_errors.append(f"{label} values cannot be negative.")

if "Possession %" in available_stat_pairs:
    home_possession, away_possession = available_stat_pairs["Possession %"]
    if ((matches[[home_possession, away_possession]] < 0) | (matches[[home_possession, away_possession]] > 100)).any().any():
        validation_errors.append("Possession values must be between 0 and 100.")

if validation_errors:
    st.error("Please fix the following validation issues:")
    for error in validation_errors:
        st.write(f"- {error}")
    st.stop()

matches = matches.dropna(subset=["Date", "FTHG", "FTAG"]).copy()
matches["FTHG"] = matches["FTHG"].astype(int)
matches["FTAG"] = matches["FTAG"].astype(int)
matches["TotalGoals"] = matches["FTHG"] + matches["FTAG"]
matches["BTTS"] = (matches["FTHG"] > 0) & (matches["FTAG"] > 0)
matches = matches.sort_values("Date").reset_index(drop=True)

st.success(f"Validation passed: {len(matches):,} matches loaded.")

st.header("2. Dataset overview")
metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Matches", f"{len(matches):,}")
metric_2.metric("Teams", f"{pd.unique(matches[['HomeTeam', 'AwayTeam']].values.ravel()).size:,}")
metric_3.metric("Average goals", f"{matches['TotalGoals'].mean():.2f}")
metric_4.metric("Both teams scored", f"{matches['BTTS'].mean() * 100:.1f}%")

if available_stat_pairs:
    st.success("Additional statistics detected: " + ", ".join(available_stat_pairs.keys()))
else:
    st.warning("No optional statistics were detected. Add matching home/away columns to unlock deeper analysis.")

st.subheader("Recent uploaded matches")
st.dataframe(
    matches.sort_values("Date", ascending=False).head(25),
    use_container_width=True,
    hide_index=True,
)

st.header("3. Result breakdown")
result_counts = matches["FTR"].value_counts().reindex(["H", "D", "A"], fill_value=0)
result_labels = {"H": "Home wins", "D": "Draws", "A": "Away wins"}
result_breakdown = pd.DataFrame(
    {
        "Result": [result_labels[key] for key in result_counts.index],
        "Matches": result_counts.values,
        "Percentage": (result_counts.values / len(matches) * 100).round(1),
    }
)
st.dataframe(result_breakdown, use_container_width=True, hide_index=True)

st.header("4. Team form and performance")
team_names = sorted(pd.unique(matches[["HomeTeam", "AwayTeam"]].values.ravel()))
selected_team = st.selectbox("Choose a team", team_names)

home_matches = matches[matches["HomeTeam"] == selected_team].copy()
away_matches = matches[matches["AwayTeam"] == selected_team].copy()

home_matches["TeamGoalsFor"] = home_matches["FTHG"]
home_matches["TeamGoalsAgainst"] = home_matches["FTAG"]
home_matches["TeamResult"] = home_matches["FTR"].map({"H": "W", "D": "D", "A": "L"})
away_matches["TeamGoalsFor"] = away_matches["FTAG"]
away_matches["TeamGoalsAgainst"] = away_matches["FTHG"]
away_matches["TeamResult"] = away_matches["FTR"].map({"A": "W", "D": "D", "H": "L"})

team_matches = pd.concat([home_matches, away_matches], ignore_index=True).sort_values("Date", ascending=False)
team_games = len(team_matches)
team_wins = int((team_matches["TeamResult"] == "W").sum())
team_draws = int((team_matches["TeamResult"] == "D").sum())
team_losses = int((team_matches["TeamResult"] == "L").sum())
team_goals_for = int(team_matches["TeamGoalsFor"].sum())
team_goals_against = int(team_matches["TeamGoalsAgainst"].sum())

team_metric_1, team_metric_2, team_metric_3, team_metric_4 = st.columns(4)
team_metric_1.metric("Games", team_games)
team_metric_2.metric("Wins", team_wins)
team_metric_3.metric("Draws", team_draws)
team_metric_4.metric("Losses", team_losses)

if team_games:
    points = team_wins * 3 + team_draws
    st.write(
        f"**{selected_team}:** {points} points from {team_games} games · "
        f"{team_goals_for} scored · {team_goals_against} conceded · "
        f"{team_goals_for / team_games:.2f} goals scored per game."
    )

st.subheader("Last five matches")
last_five = team_matches.head(5).copy()
last_five["Date"] = last_five["Date"].dt.strftime("%Y-%m-%d")
st.dataframe(
    last_five[["Date", "HomeTeam", "AwayTeam", "TeamGoalsFor", "TeamGoalsAgainst", "TeamResult"]],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Available team statistics")
if available_stat_pairs and team_games:
    stat_rows = []
    for label, (home_col, away_col) in available_stat_pairs.items():
        home_values = team_matches[home_col] if "HomeTeam" in team_matches.columns else pd.Series(dtype=float)
        away_values = team_matches[away_col] if "AwayTeam" in team_matches.columns else pd.Series(dtype=float)
        values = []
        for _, row in team_matches.iterrows():
            if row["HomeTeam"] == selected_team:
                values.append(row[home_col])
            else:
                values.append(row[away_col])
        stat_rows.append({"Statistic": label, "Average per match": round(pd.Series(values).mean(), 2)})
    st.dataframe(pd.DataFrame(stat_rows), use_container_width=True, hide_index=True)
else:
    st.info("Upload optional statistics to see team-level averages for corners, shots, cards, possession and more.")

st.caption(
    "Next stage: add opponent-adjusted team ratings, bookmaker odds, probability estimates and time-ordered backtesting."
)
