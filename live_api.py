"""API-Football client used by the Streamlit dashboard."""

from datetime import date

import requests
import streamlit as st

BASE_URL = "https://v3.football.api-sports.io"
PREMIER_LEAGUE_ID = 39


def api_key():
    try:
        return st.secrets.get("API_FOOTBALL_KEY", "").strip()
    except Exception:
        return ""


@st.cache_data(ttl=60, show_spinner=False)
def api_get(endpoint, params=None):
    key = api_key()
    if not key:
        return None, "API_FOOTBALL_KEY is not configured in Streamlit Secrets."
    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint.lstrip('/')}",
            headers={"x-apisports-key": key},
            params=params or {},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors") or {}
        if errors:
            return None, str(errors)
        return payload.get("response", []), None
    except requests.RequestException as exc:
        return None, f"API request failed: {exc}"
    except ValueError:
        return None, "The API returned an invalid JSON response."


def fixtures_for_date(selected_date: date):
    return api_get(
        "fixtures",
        {
            "date": selected_date.isoformat(),
            "league": PREMIER_LEAGUE_ID,
            "timezone": "Europe/London",
        },
    )


def live_fixtures():
    return api_get(
        "fixtures",
        {
            "live": "all",
            "league": PREMIER_LEAGUE_ID,
            "timezone": "Europe/London",
        },
    )


def prediction_for_fixture(fixture_id):
    return api_get("predictions", {"fixture": fixture_id})


def odds_for_fixture(fixture_id):
    return api_get("odds", {"fixture": fixture_id})


def statistics_for_fixture(fixture_id):
    return api_get("fixtures/statistics", {"fixture": fixture_id})


def events_for_fixture(fixture_id):
    return api_get("fixtures/events", {"fixture": fixture_id})


def fixture_rows(fixtures):
    rows = []
    for item in fixtures or []:
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        league = item.get("league", {})
        status = fixture.get("status", {})
        rows.append(
            {
                "Fixture ID": fixture.get("id"),
                "Kick-off (UK)": fixture.get("date", "").replace("T", " ")[:16],
                "League": league.get("name"),
                "Home": (teams.get("home") or {}).get("name"),
                "Away": (teams.get("away") or {}).get("name"),
                "Home score": goals.get("home"),
                "Away score": goals.get("away"),
                "Status": status.get("long") or status.get("short"),
                "Elapsed": status.get("elapsed"),
            }
        )
    return rows


def prediction_summary(payload):
    if not payload:
        return None
    item = payload[0] if isinstance(payload, list) else payload
    predictions = item.get("predictions", {}) or {}
    percent = predictions.get("percent", {}) or {}
    goals = predictions.get("goals", {}) or {}
    return {
        "Advice": predictions.get("advice"),
        "Under/Over": predictions.get("under_over"),
        "Home probability": percent.get("home"),
        "Draw probability": percent.get("draw"),
        "Away probability": percent.get("away"),
        "Predicted home goals": goals.get("home"),
        "Predicted away goals": goals.get("away"),
    }


def odds_rows(payload):
    """Flatten API-Football odds into one row per offered selection."""
    rows = []
    for item in payload or []:
        bookmakers = item.get("bookmakers") or []
        for bookmaker in bookmakers:
            bookmaker_name = bookmaker.get("name") or bookmaker.get("id")
            for bet in bookmaker.get("bets") or []:
                market = bet.get("name") or bet.get("id")
                for value in bet.get("values") or []:
                    rows.append(
                        {
                            "Bookmaker": bookmaker_name,
                            "Market": market,
                            "Selection": value.get("value"),
                            "Odd": value.get("odd"),
                        }
                    )
    return rows


def statistics_rows(payload):
    rows = []
    for team_block in payload or []:
        team = (team_block.get("team") or {}).get("name")
        for stat in team_block.get("statistics") or []:
            rows.append({"Team": team, "Statistic": stat.get("type"), "Value": stat.get("value")})
    return rows


def event_rows(payload):
    rows = []
    for event in payload or []:
        team = (event.get("team") or {}).get("name")
        player = (event.get("player") or {}).get("name")
        assist = (event.get("assist") or {}).get("name")
        rows.append(
            {
                "Minute": event.get("time", {}).get("elapsed"),
                "Team": team,
                "Type": event.get("type"),
                "Detail": event.get("detail"),
                "Player": player,
                "Assist": assist,
            }
        )
    return rows
