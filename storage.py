"""Simple JSON storage for PregnancyTracker

Stores a dictionary with keys:
- "periods": list of dicts {"start": "YYYY-MM-DD", "duration": int}
- "sex": list of date strings "YYYY-MM-DD"
- "settings": {"cycle_length": int, "luteal_phase": int}
"""
from __future__ import annotations
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Dict, Any, List
import copy

DATA_FILENAME = "data.json"


def debug_path_info() -> dict:
    """Debug helper to see what paths are being detected. Call this from Pythonista console."""
    info = {}
    try:
        info['__file__'] = __file__
        info['__file___realpath'] = os.path.realpath(__file__)
        info['__file___dirname'] = os.path.dirname(os.path.realpath(__file__))
    except (NameError, Exception) as e:
        info['__file__'] = f"ERROR: {e}"
    
    try:
        info['sys.argv[0]'] = sys.argv[0] if sys.argv else "None"
        if sys.argv and sys.argv[0]:
            info['sys.argv[0]_realpath'] = os.path.realpath(sys.argv[0])
            info['sys.argv[0]_dirname'] = os.path.dirname(os.path.realpath(sys.argv[0]))
    except Exception as e:
        info['sys.argv[0]'] = f"ERROR: {e}"
    
    try:
        info['os.getcwd()'] = os.getcwd()
    except Exception as e:
        info['os.getcwd()'] = f"ERROR: {e}"
    
    info['expanduser(~/Documents)'] = os.path.expanduser('~/Documents')
    info['final_data_path'] = _data_path()
    return info


def _data_path() -> str:
    """Get the path to data.json, trying multiple strategies for cross-platform compatibility."""
    base = None
    
    # Strategy 1: Use __file__ if available (works in most Python environments)
    try:
        base = os.path.dirname(os.path.realpath(__file__))
        if base and os.path.isdir(base):
            return os.path.join(base, DATA_FILENAME)
    except (NameError, Exception):
        pass
    
    # Strategy 2: Use sys.argv[0] (works when script is run directly)
    try:
        if sys.argv and sys.argv[0]:
            base = os.path.dirname(os.path.realpath(sys.argv[0]))
            if base and os.path.isdir(base):
                return os.path.join(base, DATA_FILENAME)
    except Exception:
        pass
    
    # Strategy 3: Use current working directory
    try:
        base = os.getcwd()
        if base and os.path.isdir(base):
            return os.path.join(base, DATA_FILENAME)
    except Exception:
        pass
    
    # Strategy 4: Fallback to home Documents folder (Pythonista default)
    base = os.path.expanduser('~/Documents')
    return os.path.join(base, DATA_FILENAME)


def default_data() -> Dict[str, Any]:
    return {
        "periods": [],
        # per-day intensity mapping: {"YYYY-MM-DD": intensity}, intensity: 1=light,2=medium,3=heavy
        "period_levels": {},
        "sex": [],
        "settings": {"cycle_length": 28, "luteal_phase": 14},
    }


def load_data() -> Dict[str, Any]:
    path = _data_path()
    if not os.path.exists(path):
        data = default_data()
        save_data(data)
        return data
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception:
        data = default_data()
        save_data(data)
    # ensure keys exist
    data.setdefault("periods", [])
    # new per-day intensity mapping
    data.setdefault("period_levels", {})
    data.setdefault("sex", [])
    data.setdefault("settings", {"cycle_length": 28, "luteal_phase": 14})
    return data


def _levels_to_periods(levels: Dict[str, int]) -> List[dict]:
    """Convert a mapping of date->intensity into period entries (start + duration).
    Any date with intensity > 0 is considered a period day. Groups consecutive days.
    """
    # Extract days with intensity > 0
    days = [datetime.strptime(d, '%Y-%m-%d').date() for d, v in levels.items() if v and int(v) > 0]
    days = sorted(days)
    if not days:
        return []

    periods = []
    start = days[0]
    prev = start
    duration = 1
    for d in days[1:]:
        if (d - prev).days == 1:
            duration += 1
        else:
            periods.append({'start': start.isoformat(), 'duration': duration})
            start = d
            duration = 1
        prev = d

    periods.append({'start': start.isoformat(), 'duration': duration})
    return periods


# --- Simple in-memory undo/redo stacks (non-persistent) ---
# We keep deep copies of the full data dict. They are reset on process exit.
_undo_stack: List[Dict[str, Any]] = []
_redo_stack: List[Dict[str, Any]] = []


def _record_undo_state() -> None:
    """Record current data snapshot on the undo stack and clear redo stack.

    This should be called before any mutating operation.
    """
    try:
        data = load_data()
        _undo_stack.append(copy.deepcopy(data))
        # keep the stack bounded to avoid unbounded memory use
        if len(_undo_stack) > 50:
            _undo_stack.pop(0)
        _redo_stack.clear()
    except Exception:
        # best-effort; don't raise to callers
        return


def undo() -> bool:
    """Restore the previous data snapshot. Returns True if an undo occurred."""
    if not _undo_stack:
        return False
    try:
        current = load_data()
        _redo_stack.append(copy.deepcopy(current))
        prev = _undo_stack.pop()
        save_data(prev)
        return True
    except Exception:
        return False


def redo() -> bool:
    """Restore the next data snapshot (after an undo). Returns True if a redo occurred."""
    if not _redo_stack:
        return False
    try:
        current = load_data()
        _undo_stack.append(copy.deepcopy(current))
        nxt = _redo_stack.pop()
        save_data(nxt)
        return True
    except Exception:
        return False


def migrate_period_days_to_levels() -> bool:
    """One-time migration helper.

    If a legacy `period_days` key exists in the data, convert each listed day
    into `period_levels` with intensity=1 (unless a stronger intensity already
    exists). Removes the `period_days` key afterwards and saves.

    Returns True if migration happened, False otherwise.
    """
    data = load_data()
    legacy = data.get('period_days')
    if not legacy:
        return False

    # record undo state before changing
    _record_undo_state()

    levels = data.setdefault('period_levels', {})
    for d in legacy:
        try:
            if d not in levels or int(levels.get(d, 0)) < 1:
                levels[d] = 1
        except Exception:
            # ignore malformed dates but continue
            continue

    # remove legacy key and save
    try:
        del data['period_days']
    except Exception:
        pass
    save_data(data)
    return True


def save_data(data: Dict[str, Any]) -> None:
    """Save data to JSON, updating periods from period_days."""
    # First update periods based on per-day intensity mapping
    data['periods'] = _levels_to_periods(data.get('period_levels', {}))
    
    path = _data_path()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def add_period(start: date, duration: int = 5) -> None:
    """Add a period with start date and duration."""
    # record undo snapshot before mutating
    _record_undo_state()
    data = load_data()
    # Add days to period_levels mapping (default intensity = 1)
    levels = data.setdefault('period_levels', {})
    for i in range(int(duration)):
        d = (start + timedelta(days=i)).isoformat()
        levels[d] = max(int(levels.get(d, 0)), 1)
    save_data(data)


def remove_period(start: date) -> None:
    """Remove a period by removing its period_days. The periods array will update automatically."""
    _record_undo_state()
    data = load_data()
    s = start.isoformat()
    # Find the matching period to get its duration
    period = next((p for p in data.get('periods', []) if p.get('start') == s), None)
    levels = data.setdefault('period_levels', {})
    if period:
        # Remove the period_days for this period's duration
        try:
            pd = datetime.fromisoformat(s).date()
            dur = int(period.get('duration', 5))
            for i in range(dur):
                d = (pd + timedelta(days=i)).isoformat()
                if d in levels:
                    del levels[d]
        except Exception:
            pass
    save_data(data)


def edit_period(start: date, new_duration: int) -> None:
    """Edit a period's duration by removing old period_days and adding new ones."""
    _record_undo_state()
    data = load_data()
    s = start.isoformat()
    levels = data.setdefault('period_levels', {})
    # Find the period to edit
    period = next((p for p in data.get('periods', []) if p.get('start') == s), None)
    if period:
        # Remove old period_days
        try:
            pd = datetime.fromisoformat(s).date()
            old_dur = int(period.get('duration', 5))
            for i in range(old_dur):
                d = (pd + timedelta(days=i)).isoformat()
                if d in levels:
                    del levels[d]
        except Exception:
            pass
        
        # Add new period_days (default intensity 1)
        for i in range(new_duration):
            d = (start + timedelta(days=i)).isoformat()
            levels[d] = max(int(levels.get(d, 0)), 1)
    
    save_data(data)


def add_sex(d: date) -> None:
    _record_undo_state()
    data = load_data()
    s = d.isoformat()
    if s not in data["sex"]:
        data["sex"].append(s)
    save_data(data)


def toggle_period_day(d: date) -> None:
    """Toggle a single day marked as period day."""
    _record_undo_state()
    data = load_data()
    s = d.isoformat()
    levels = data.setdefault('period_levels', {})
    cur = int(levels.get(s, 0))
    # cycle: 0 -> 1 (light) -> 2 (medium) -> 3 (heavy) -> 0 (remove)
    if cur >= 3:
        # remove
        if s in levels:
            del levels[s]
    else:
        levels[s] = cur + 1
    save_data(data)


def toggle_sex(d: date) -> None:
    """Toggle a sex event on a single day."""
    _record_undo_state()
    data = load_data()
    s = d.isoformat()
    sexes = data.setdefault("sex", [])
    if s in sexes:
        sexes.remove(s)
    else:
        sexes.append(s)
    save_data(data)


def set_settings(cycle_length: int, luteal_phase: int, theme: str | None = None) -> None:
    _record_undo_state()
    data = load_data()
    data["settings"]["cycle_length"] = int(cycle_length)
    data["settings"]["luteal_phase"] = int(luteal_phase)
    if theme is not None:
        data["settings"]["theme"] = str(theme)
    save_data(data)


def clear_all() -> None:
    _record_undo_state()
    data = default_data()
    save_data(data)
