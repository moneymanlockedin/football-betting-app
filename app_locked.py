import io
import math
import re
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

CORE = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
LEAGUES = {"England Premier League": "E0", "England Championship": "E1", "England League One": "E2", "England League Two": "E3", "Scotland Premiership": "SC0", "Germany Bundesliga": "D1", "Spain La Liga": "SP1", "Italy Serie A": "I1", "France Ligue 1": "F1", "Netherlands Eredivisie": "N1"}
SEASONS = ["2026/27", "2025/26", "2024/25", "2023/24", "2022/23", "2021/22", "2020/21", "2019/20", "2018/19"]

def num(x): return pd.to_numeric(x, errors="coerce")
def season_code(s):
    a, b = s.split("/"); return a[-2:] + b[-2:]
def max_dd(p):
    c = p.cumsum(); return float((c.cummax() - c).max()) if len(p) else 0.0
def over25_probability(g):
    if pd.isna(g): return None
    g = max(float(g), 0.05)
    return 1 - math.exp(-g) * (1 + g + g*g/2)
def download(code, season):
    u = f"https://www.football-data.co.uk/mmz4281/{season_code(season)}/{code}.csv"
    r = requests.get(u, timeout=30, headers={"User-Agent": "FootballResearchLab/1.0"}); r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content))
def load_data():
    frames = []
    source = st.radio("Data source", ["Import multiple seasons", "Upload CSV"], horizontal=True)
    if source == "Upload CSV":
        f = st.file_uploader("Choose CSV", type=["csv"])
        if f: frames = [pd.read_csv(f)]
    else:
        a, b = st.columns(2)
        with a: league = st.selectbox("League", list(LEAGUES))
        with b: seasons = st.multiselect("Seasons", SEASONS, ["2025/26", "2024/25", "2023/24"])
        if st.button("Import selected seasons", type="primary"):
            errors=[]; progress=st.progress(0)
            for i, s in enumerate(seasons):
                try:
                    f=download(LEAGUES[league], s); f["ImportedSeason"]=s; frames.append(f)
                except Exception as e: errors.append(f"{s}: {e}")
                progress.progress((i+1)/max(len(seasons),1))
            for e in errors: st.warning(e)
            if frames: st.session_state["frames_locked"] = frames; st.session_state["source_locked"] = league
        frames = st.session_state.get("frames_locked", frames)
    if not frames: st.warning("Import or upload match data to begin."); st.stop()
    data = pd.concat(frames, ignore_index=True, sort=False)
    rename={"Home Team":"HomeTeam","Away Team":"AwayTeam","HomeGoals":"FTHG","AwayGoals":"FTAG","FullTimeHomeGoals":"FTHG","FullTimeAwayGoals":"FTAG","FullTimeResult":"FTR"}
    data=data.rename(columns={k:v for k,v in rename.items() if k in data.columns})
    missing=[x for x in CORE if x not in data.columns]
    if missing: st.error("Missing columns: "+", ".join(missing)); st.stop()
    data["Date"]=pd.to_datetime(data["Date"], errors="coerce", dayfirst=True)
    data["FTHG"]=num(data["FTHG"]); data["FTAG"]=num(data["FTAG"]); data["FTR"]=data["FTR"].astype(str).str.upper().str.strip()
    data=data.dropna(subset=["Date","FTHG","FTAG"]); data=data[data["FTR"].isin(["H","D","A"])].copy()
    data["FTHG"]=data["FTHG"].astype(int); data["FTAG"]=data["FTAG"].astype(int); data["TotalGoals"]=data["FTHG"]+data["FTAG"]
    return data.sort_values(["Date","HomeTeam","AwayTeam"]).reset_index(drop=True)
def odds_options(data):
    return [c for c in ["B365>2.5","Avg>2.5","Max>2.5","P>2.5"] if c in data.columns]
def features(data):
    hist={}; rows=[]
    for _,m in data.sort_values(["Date","HomeTeam","AwayTeam"]).iterrows():
        def summary(t):
            h=hist.get(t,[]); return (len(h), sum(x[0] for x in h)/len(h), sum(x[1] for x in h)/len(h)) if h else (0,None,None)
        hg, hf, ha=summary(m.HomeTeam); ag, af, aa=summary(m.AwayTeam)
        eh=sum(x for x in [hf,aa] if x is not None)/len([x for x in [hf,aa] if x is not None]) if any(x is not None for x in [hf,aa]) else None
        ea=sum(x for x in [af,ha] if x is not None)/len([x for x in [af,ha] if x is not None]) if any(x is not None for x in [af,ha]) else None
        et=eh+ea if eh is not None and ea is not None else None
        rows.append({"Date":m.Date,"HomeTeam":m.HomeTeam,"AwayTeam":m.AwayTeam,"PriorHome":hg,"PriorAway":ag,"ExpectedTotal":et,"ModelProb":over25_probability(et)})
        hist.setdefault(m.HomeTeam,[]).append((m.FTHG,m.FTAG)); hist.setdefault(m.AwayTeam,[]).append((m.FTAG,m.FTHG))
    return data.merge(pd.DataFrame(rows), on=["Date","HomeTeam","AwayTeam"], how="left")
def evaluate(data, odds, min_games, edge, min_odds, max_odds, start, end):
    d=features(data); d[odds]=num(d[odds]); d["Implied"]=1/d[odds]; d["Edge"]=d["ModelProb"]-d["Implied"]
    d=d[(d.Date>=pd.Timestamp(start))&(d.Date<=pd.Timestamp(end))&(d.PriorHome>=min_games)&(d.PriorAway>=min_games)&d.ModelProb.notna()&d[odds].notna()&(d[odds]>=min_odds)&(d[odds]<=max_odds)&(d.Edge>=edge)].copy()
    if d.empty: return None,d
    d["Won"]=d.TotalGoals>2; d["Profit"]=d[odds].where(d.Won,0)-1; d["CumulativeProfit"]=d.Profit.cumsum()
    return {"Bets":len(d),"Wins":int(d.Won.sum()),"Strike rate":d.Won.mean()*100,"Profit":d.Profit.sum(),"ROI":d.Profit.mean()*100,"Max drawdown":max_dd(d.Profit)},d

st.set_page_config(page_title="Football Betting Research Lab", page_icon="⚽", layout="wide")
st.title("⚽ Football Betting Research Lab")
st.info("Research only. Results are historical diagnostics, not forecasts or guarantees.")
data=load_data()
st.success(f"Loaded {len(data):,} matches")
st.download_button("Download combined dataset", data.to_csv(index=False), "combined_dataset.csv", "text/csv")
st.header("Market setup")
opts=odds_options(data)
if not opts: st.error("No Over 2.5 odds column found."); st.stop()
col1,col2,col3=st.columns(3)
with col1: odds=st.selectbox("Over 2.5 odds source",opts)
with col2: min_games=st.number_input("Minimum prior games",1,20,5)
with col3: min_odds=st.number_input("Minimum odds",1.01,10.0,1.50,0.05)
max_odds=st.number_input("Maximum odds",1.01,20.0,10.0,0.25)
min_date,max_date=data.Date.min().date(),data.Date.max().date()
a,b=st.columns(2)
with a: start=st.date_input("Analysis start",min_date,min_value=min_date,max_value=max_date)
with b: end=st.date_input("Analysis end",max_date,min_value=min_date,max_value=max_date)
st.header("Walk-forward research")
edge=st.slider("Minimum model edge",0.0,0.20,0.05,0.01)
if st.button("Run walk-forward evaluation", type="primary"):
    result,test=evaluate(data,odds,int(min_games),float(edge),float(min_odds),float(max_odds),start,end)
    if result:
        c=st.columns(6)
        for box,label,value in zip(c,["Bets","Wins","Strike rate","Profit","ROI","Max drawdown"],[result['Bets'],result['Wins'],f"{result['Strike rate']:.1f}%",f"{result['Profit']:+.2f}",f"{result['ROI']:+.2f}%",f"{result['Max drawdown']:.2f}"]): box.metric(label,value)
        st.line_chart(test.set_index("Date")["CumulativeProfit"]); st.dataframe(test.head(200),use_container_width=True,hide_index=True)
    else: st.warning("No qualifying selections.")
st.header("Robustness checks")
if st.button("Run sensitivity grid"):
    rows=[]
    for e in [0.0,0.03,0.05,0.07,0.10]:
        for ceiling in [1.75,2.0,2.5,3.0,5.0]:
            r,t=evaluate(data,odds,int(min_games),e,float(min_odds),ceiling,start,end)
            if r: rows.append({"Minimum edge":e,"Max odds":ceiling,**{k:round(v,2) if isinstance(v,float) else v for k,v in r.items()}})
    if rows: st.dataframe(pd.DataFrame(rows).sort_values(["ROI","Bets"],ascending=False),use_container_width=True,hide_index=True)
    else: st.warning("No configurations produced results.")
st.header("Locked final holdout test")
st.write("Choose a development cutoff. Settings are selected above, then the holdout is evaluated separately and is not used in the sensitivity grid.")
cutoff=st.date_input("Development cutoff", max_date-pd.Timedelta(days=365), min_value=min_date, max_value=max_date)
if st.button("Run locked holdout test", type="primary"):
    train_end=pd.Timestamp(cutoff); holdout_start=(train_end+pd.Timedelta(days=1)).date()
    if holdout_start>end: st.warning("Move the cutoff earlier so a holdout period remains.")
    else:
        r,t=evaluate(data,odds,int(min_games),float(edge),float(min_odds),float(max_odds),holdout_start,end)
        st.subheader("Untouched holdout results")
        st.caption("This test uses the settings currently shown. Do not change them after inspecting the holdout result and call it independent.")
        if r:
            c=st.columns(6)
            for box,label,value in zip(c,["Bets","Wins","Strike rate","Profit","ROI","Max drawdown"],[r['Bets'],r['Wins'],f"{r['Strike rate']:.1f}%",f"{r['Profit']:+.2f}",f"{r['ROI']:+.2f}%",f"{r['Max drawdown']:.2f}"]): box.metric(label,value)
            st.line_chart(t.set_index("Date")["CumulativeProfit"]); st.dataframe(t,use_container_width=True,hide_index=True)
        else: st.warning("No qualifying holdout selections.")
st.caption("Safeguards: chronological features, explicit holdout, sensitivity diagnostics, and warnings against selecting settings after seeing holdout results.")
