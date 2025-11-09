# PregnancyTracker (Pythonista)

This is a small pregnancy/fertility tracker app designed to run inside the Pythonista app on iPhone/iPad. It uses only Python standard libraries and NumPy, so no external pip installs are required when running inside Pythonista (NumPy is available in recent Pythonista versions; if not present, the app will still run but numeric helpers that use NumPy will gracefully fall back to Python lists).

Features
- Log period start dates and durations
- Log sex events
- Predict ovulation and fertile windows using cycle length and luteal phase
- Calendar view with colored days: period, fertile window, ovulation, sex
- Simple stats view: average cycle length, last N cycles

Files
- `main.py` — main UI script to open in Pythonista
- `storage.py` — load/save JSON storage
- `models.py` — fertility prediction logic
- `sample_data.json` — optional sample data to copy into data file

How to run
1. Copy the files into Pythonista's file browser (you can open this repository folder in iCloud Drive or use iTunes file sharing). Alternatively, paste the contents into a new Pythonista script named `main.py` and the other modules as separate files.
2. Open `main.py` in Pythonista and run it.

Basic usage
- Tap a day to view details. Use the toolbar buttons to add a period start or a sex event. Change settings (cycle length, luteal phase) inside the app.

Notes and assumptions
- Prediction algorithm: ovulation = period_start + (cycle_length - luteal_phase). Fertile window = ovulation - 5 days through ovulation + 1 day. Luteal phase default: 14 days.
- This tool is educational; it does not replace medical advice.

If you want enhancements (e.g., graphs, export/import, push reminders, better calendar navigation), tell me which features you'd like next.
