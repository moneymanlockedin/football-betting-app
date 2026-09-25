# Main entrypoint for the Football Betting Research Lab.
# The historical research dashboard remains in app_locked.py.
exec(compile(open("app_locked.py", "r", encoding="utf-8").read(), "app_locked.py", "exec"))

import streamlit as st

from integrated_analysis import render_integrated_section

# Remove any previously cached fixture rows from other competitions that may
# remain in a user's Streamlit session after the league filter is changed.
existing = st.session_state.get("integrated_fixtures")
if existing:
    st.session_state["integrated_fixtures"] = [
        item
        for item in existing
        if (item.get("league") or {}).get("id") == 39
        or str((item.get("league") or {}).get("name", "")).strip().lower() == "premier league"
    ]

render_integrated_section(data)
