# PregnancyTracker AI Coding Agent Instructions

## Architecture Overview

This is a dual-platform fertility/pregnancy tracker with:
- **Primary target**: Pythonista iOS app (native `ui` module)
- **Fallback**: macOS Tkinter UI for testing
- **Core modules**: `main.py` (UI), `storage.py` (JSON persistence), `models.py` (predictions)

**Critical**: `main.py` adds its own directory to `sys.path` at startup to ensure local modules (`storage.py`, `models.py`) are imported from the same location, not from other copies that might exist elsewhere in the file system.

Data flows: UI → `storage.py` functions → JSON file → UI refresh

## Data Model & Storage

**Critical**: The app uses a **per-day intensity mapping** system (`period_levels`) that auto-generates `periods` entries:
- `period_levels`: `{"YYYY-MM-DD": 1-3}` where 1=light, 2=medium, 3=heavy
- `periods`: Auto-generated from `period_levels` via `_levels_to_periods()` (groups consecutive days)
- When saving, `save_data()` ALWAYS regenerates `periods` from `period_levels`

**Never manually edit the `periods` array** - always modify `period_levels` instead. Use `toggle_period_day()` which cycles: 0→1→2→3→0.

Legacy `period_days` key may exist in old data - use `migrate_period_days_to_levels()` to convert.

## Undo/Redo System

In-memory undo/redo stacks (non-persistent, reset on exit):
- Call `_record_undo_state()` BEFORE any mutation in `storage.py`
- Already implemented in all mutating functions (`toggle_period_day`, `add_sex`, etc.)
- Stack bounded to 50 entries to prevent memory bloat

## Platform Detection & UI Rendering

Platform detection in `main.py`:
```python
_HAS_PYTHONISTA = True if 'ui' module imports successfully
_HAS_TK = True if 'tkinter' imports successfully
```

**Color theming**: Use `get_palette(theme)` for all color values. Theme stored in `settings['theme']` ('light' or 'dark').

**Prediction visualization**: Gradient backgrounds on predicted period days using `_blend_hex()` - darker = closer to predicted start.

## Prediction Algorithm (models.py)

Formula: `ovulation_date = period_start + (cycle_length - luteal_phase)`
- Fertile window: ovulation - 5 days to ovulation + 1 day
- `predict_from_periods()` returns future predictions with `lookahead_months` parameter
- Uses NumPy for cycle averaging if available, falls back to pure Python

## Key Conventions

1. **Date handling**: Always use ISO format (`YYYY-MM-DD` strings) for storage, convert to `datetime.date` objects for calculations
2. **UI refresh**: After any data mutation, reload data and call `build_grid()` (Pythonista) or `refresh_calendar()` (Tkinter)
3. **Status computation**: `day_status_for_month()` returns `{iso_date: set(['period', 'sex', 'ovulation', 'fertile'])}` for calendar coloring
4. **Toggle buttons**: Only show period/sex toggles for today and past dates (no future editing)

## Common Tasks

**Add new feature to calendar cell**:
1. Modify `day_status_for_month()` to compute new status
2. Add color to palette in `get_palette()`
3. Update cell background logic in both `CalendarView.build_grid()` (Pythonista) and `refresh_calendar()` (Tkinter)

**Change period intensity behavior**:
- Modify `toggle_period_day()` cycle logic in `storage.py`
- Update `period_shades` color arrays in both UI implementations

**Testing**: Run `main.py` - auto-detects platform. Use `sample_data.json` for test data (copy to `data.json`).

**Debugging in Pythonista**: If data isn't loading, run this in the Pythonista console:
```python
from storage import debug_path_info
print(debug_path_info())
```

## File Roles

- `main.py`: UI entry point, dual-platform calendar rendering, color utilities
- `storage.py`: JSON persistence, undo/redo, all data mutations
- `models.py`: Pure prediction logic, no storage access
- `fix_periods.py`: One-time migration script (legacy, kept for reference)
- `data.json`: Runtime data file (auto-created from defaults)
