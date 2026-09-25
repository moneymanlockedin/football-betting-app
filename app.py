# Main entrypoint for the Football Betting Research Lab.
# The historical research dashboard remains in app_locked.py.
exec(compile(open("app_locked.py", "r", encoding="utf-8").read(), "app_locked.py", "exec"))

from integrated_analysis import render_integrated_section

render_integrated_section(data)
