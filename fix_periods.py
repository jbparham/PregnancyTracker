"""Quick fix to convert period_days into proper period entries"""
from datetime import datetime, timedelta
import json
from typing import List

def days_to_periods(days: List[str]) -> List[dict]:
    # Sort the days
    days = sorted([datetime.strptime(d, '%Y-%m-%d').date() for d in days])
    if not days:
        return []
    
    # Group consecutive days
    periods = []
    start = days[0]
    prev = start
    duration = 1
    
    for d in days[1:]:
        if (d - prev).days == 1:
            # Consecutive day
            duration += 1
        else:
            # Gap found, save previous period and start new one
            periods.append({
                'start': start.isoformat(),
                'duration': duration
            })
            start = d
            duration = 1
        prev = d
    
    # Add the last period
    periods.append({
        'start': start.isoformat(),
        'duration': duration
    })
    
    return periods

# Load current data
with open('data.json', 'r') as f:
    data = json.load(f)

# Convert period_days to proper period entries
data['periods'] = days_to_periods(data['period_days'])

# Save back
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2, sort_keys=True)