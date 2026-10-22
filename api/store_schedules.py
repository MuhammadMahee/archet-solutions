"""Recurring store hours transcribed from the supplied two-sheet workbook.

The checked-in data makes report generation independent of a local Excel path.
Unmatched workbook stores are preserved as source data, not added to the roster.
"""
from datetime import time
from functools import lru_cache
import json
from pathlib import Path

PERIOD_LABELS = {'weekday': 'Monday–Friday', 'saturday': 'Saturday', 'sunday': 'Sunday'}


@lru_cache(maxsize=1)
def schedule_catalog():
    data = json.loads(Path(__file__).with_name('store_schedules.json').read_text(encoding='utf-8'))
    catalog = {}
    for row in data['stores']:
        if not row['portal_store_id']:
            continue
        key = row['portal_dealer'], row['portal_store_id']
        if key in catalog:
            raise ValueError('Duplicate store schedule')
        catalog[key] = {period: {field: time.fromisoformat(value) for field, value in row[period].items()}
                        for period in PERIOD_LABELS}
    return catalog


def scheduled_hours(store, day):
    period = 'sunday' if day.weekday() == 6 else 'saturday' if day.weekday() == 5 else 'weekday'
    entry = schedule_catalog().get((store['dealer'], store['store_id']), {}).get(period, {})
    return {**entry, 'period': PERIOD_LABELS[period]}
