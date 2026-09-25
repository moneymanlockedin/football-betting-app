# Football Betting Research Lab

A small Python and Streamlit app for exploring football match probability estimates. This starter version displays illustrative sample data only; it does not fetch live odds, place bets, or promise results.

## Run it on your computer

1. Install Python.
2. Open a terminal in this repository folder.
3. Create and activate a virtual environment.

   **Windows PowerShell**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS or Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install the app's packages and start it:

   ```bash
   python -m pip install -r requirements.txt
   streamlit run app.py
   ```

Streamlit will print a local address (usually http://localhost:8501). Open that address in your browser. Stop the app with Ctrl+C in the terminal.

## View it online

To publish a demo, create a Streamlit Community Cloud app connected to this GitHub repository, choose the `main` branch and `app.py` as the main file, then deploy. The repository includes `requirements.txt` for dependency installation.

## Current scope

The dashboard shows three fictional sample fixtures with home-win, draw, and away-win probabilities. These are placeholders for demonstrating the interface, not predictions. Later research work can add historical results, a documented baseline model, probability calibration, and time-ordered backtesting. No betting automation or real-money features are included.
