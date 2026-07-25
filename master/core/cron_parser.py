from __future__ import annotations

import datetime
import re
from typing import Set

# Regular expressions for validation
_FIELD_PART_RE = re.compile(
    r'^(\*|(?:\d+(?:-\d+)?(?:/\d+)?))(?:,(\*|(?:\d+(?:-\d+)?(?:/\d+)?)))*$'
)


def parse_cron_field(field: str, min_val: int, max_val: int) -> Set[int]:
    """Parse a single cron field expression into a set of allowed integers.

    Supports:
      - '*' (all values)
      - Lists with commas: '1,5,10'
      - Intervals: '1-5'
      - Steps: '*/5', '1-10/2'
    """
    field = field.strip()
    if not field:
        raise ValueError("Empty cron field")

    allowed: Set[int] = set()

    for part in field.split(','):
        if not part:
            raise ValueError("Empty field component in list")

        step = 1
        val_part = part

        if '/' in part:
            val_part, step_str = part.split('/')
            try:
                step = int(step_str)
                if step <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Invalid cron step value: '{step_str}'")

        if val_part == '*':
            start, end = min_val, max_val
        elif '-' in val_part:
            start_str, end_str = val_part.split('-')
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                raise ValueError(f"Invalid cron range values: '{start_str}-{end_str}'")
        else:
            try:
                start = int(val_part)
                end = start
            except ValueError:
                raise ValueError(f"Invalid cron integer value: '{val_part}'")

        # Range boundaries checks
        if start < min_val or start > max_val or end < min_val or end > max_val:
            raise ValueError(
                f"Cron value out of boundaries [{min_val}-{max_val}]: '{part}'"
            )
        if start > end:
            raise ValueError(f"Cron range start exceeds end: '{start}-{end}'")

        allowed.update(range(start, end + 1, step))

    return allowed


class CronExpression:
    """A standard 5-field CRON expression parser.

    Format: minute hour day-of-month month day-of-week
    """

    def __init__(self, expr: str) -> None:
        self.expr = expr
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression: '{expr}'. Must have exactly 5 fields."
            )

        try:
            self.minutes = parse_cron_field(parts[0], 0, 59)
            self.hours = parse_cron_field(parts[1], 0, 23)
            self.dom = parse_cron_field(parts[2], 1, 31)
            self.months = parse_cron_field(parts[3], 1, 12)
            # 0 or 7 is Sunday, 1 is Monday, ..., 6 is Saturday
            self.dow = parse_cron_field(parts[4], 0, 7)
            # Map 7 (Sunday) to 0 (Sunday) to unify sets lookup
            if 7 in self.dow:
                self.dow.discard(7)
                self.dow.add(0)
        except ValueError as e:
            raise ValueError(f"Failed parsing cron expression '{expr}': {e}") from e

    def next_trigger(self, from_timestamp: float) -> float:
        """Calculate the next execution timestamp (UTC) after the given timestamp."""
        # Convert timestamp to timezone-aware datetime in UTC
        dt = datetime.datetime.fromtimestamp(from_timestamp, datetime.timezone.utc)
        # Look ahead starting from the next minute
        dt = dt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

        # Look up to 1 year ahead (525600 minutes) to avoid infinite loop
        for _ in range(525600):
            # Python: 0=Monday ... 6=Sunday
            # Standard cron: 0=Sunday, 1=Monday ... 6=Saturday
            cron_dow = (dt.weekday() + 1) % 7

            if (
                dt.minute in self.minutes
                and dt.hour in self.hours
                and dt.day in self.dom
                and dt.month in self.months
                and cron_dow in self.dow
            ):
                return dt.timestamp()

            dt += datetime.timedelta(minutes=1)

        raise ValueError("No matching execution time found within 1 year.")
