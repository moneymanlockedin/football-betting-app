"""Small API-Football client used by the Streamlit dashboard."""

from datetime import date

import requests
import streamlit as st

BASE_URL = "https://v3.football.api-sports.io"


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
    return api_get("fixtures", {"date": selected_date.isoformat(), "timezone": "Europe/London"})


def live_fixtures():
    return api_get("fixtures", {"live": "all", "timezone": "Europe/London"})


def prediction_for_fixture(fixture_id):
    return api_get("predictions", {"fixture": fixture_id})


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
    predictions = item.get("predictions", {})
    percent = predictions.get("percent", {}) or {}
    return {
        "Advice": predictions.get("advice"),
        "Under/Over": predictions.get("under_over"),
        "Home probability": percent.get("home"),
        "Draw probability": percent.get("draw"),
        "Away probability": percent.get("away"),
    }
