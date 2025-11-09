"""Fertility prediction utilities

Simple rules:
- ovulation = period_start + (cycle_length - luteal_phase)
- fertile window = ovulation - 5 .. ovulation + 1

Functions accept and return datetime.date objects and ISO date strings.
"""
from __future__ import annotations
from datetime import date, timedelta, datetime
from typing import List, Tuple
try:
    import numpy as _np
except Exception:
    _np = None


def to_date(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def iso(d: date) -> str:
    return d.isoformat()


def predict_from_periods(period_starts: List[str], cycle_length: int = 28, luteal_phase: int = 14, lookahead_months: int = 6) -> dict:
    """Given recorded period start ISO strings, return predicted fertile windows and ovulation days.

    Returns a dict with keys:
    - "ovulations": list of ISO dates
    - "fertile_windows": list of (start_iso, end_iso) tuples
    - "predicted_cycles": list of period start ISO dates (including predicted future starts)
    """
    # parse inputs
    starts = sorted([to_date(s) for s in period_starts])
    if not starts:
        return {"ovulations": [], "fertile_windows": [], "predicted_cycles": []}

    # use numpy for average cycle length if many cycles are present
    if len(starts) >= 2:
        ords = [d.toordinal() for d in starts]
        if _np is not None:
            diffs = _np.diff(_np.array(ords))
            avg_cycle = int(round(_np.mean(diffs)))
        else:
            diffs = [ords[i+1] - ords[i] for i in range(len(ords)-1)]
            avg_cycle = int(round(sum(diffs) / len(diffs)))
    else:
        avg_cycle = int(cycle_length)

    # predicted next cycles: take last start and extrapolate for lookahead_months (~30 days per month)
    last = starts[-1]
    days_to_predict = lookahead_months * 31
    predicted = []
    cur = last
    while (cur - last).days <= days_to_predict:
        predicted.append(cur)
        cur = cur + timedelta(days=avg_cycle)

    # compute ovulations and fertile windows for recorded + predicted starts
    ovulations = []
    fertile_windows = []
    for s in predicted:
        ov = s + timedelta(days=(avg_cycle - luteal_phase))
        ovulations.append(ov)
        fw_start = ov - timedelta(days=5)
        fw_end = ov + timedelta(days=1)
        fertile_windows.append((fw_start, fw_end))

    return {
        "ovulations": [iso(d) for d in ovulations],
        "fertile_windows": [(iso(a), iso(b)) for a, b in fertile_windows],
        "predicted_cycles": [iso(d) for d in predicted],
        "avg_cycle": int(avg_cycle),
    }


def day_status_for_month(periods: List[dict], period_days: List[str], sex_dates: List[str], cycle_length: int, luteal_phase: int, year: int, month: int) -> dict:
    """Return a mapping ISO date -> set of status strings for the given month.

    Status strings: 'period', 'sex', 'ovulation', 'fertile'.
    """
    from calendar import monthrange

    _, ndays = monthrange(year, month)
    # build predicted windows from periods
    # For predictions we use the period start dates (if available)
    period_starts = [p["start"] for p in periods] if periods else []
    pred = predict_from_periods(period_starts, cycle_length, luteal_phase, lookahead_months=6)
    fw = [(to_date(a), to_date(b)) for a, b in pred["fertile_windows"]]
    ov = [to_date(d) for d in pred["ovulations"]]

    status = {}
    for d in range(1, ndays + 1):
        cur = date(year, month, d)
        sset = set()
        # period days: explicit per-day markings
        for pd_str in period_days:
            if to_date(pd_str) == cur:
                sset.add("period")
        # period days: check recorded period starts and durations
        for p in periods:
            try:
                pd = to_date(p.get('start'))
                dur = int(p.get('duration', 5))
            except Exception:
                continue
            if pd <= cur < pd + timedelta(days=dur):
                sset.add("period")
        # sex
        if cur.isoformat() in sex_dates:
            sset.add("sex")
        # ovulation
        if cur in ov:
            sset.add("ovulation")
        # fertile windows
        for a, b in fw:
            if a <= cur <= b:
                sset.add("fertile")
        if sset:
            status[cur.isoformat()] = sset
    return status
