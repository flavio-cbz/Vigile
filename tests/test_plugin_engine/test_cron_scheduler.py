from __future__ import annotations

import pytest
from master.core.cron_parser import CronExpression, parse_cron_field


def test_parse_cron_field():
    # Simple values
    assert parse_cron_field("5", 0, 59) == {5}
    assert parse_cron_field("1,5", 0, 59) == {1, 5}
    
    # Ranges
    assert parse_cron_field("1-5", 0, 59) == {1, 2, 3, 4, 5}
    
    # Steps
    assert parse_cron_field("*/15", 0, 59) == {0, 15, 30, 45}
    assert parse_cron_field("1-10/3", 0, 59) == {1, 4, 7, 10}
    
    # Validation errors
    with pytest.raises(ValueError):
        parse_cron_field("60", 0, 59)
    with pytest.raises(ValueError):
        parse_cron_field("10-5", 0, 59)
    with pytest.raises(ValueError):
        parse_cron_field("*/0", 0, 59)


def test_cron_expression_valid():
    # Every minute
    cron = CronExpression("* * * * *")
    assert len(cron.minutes) == 60
    assert len(cron.hours) == 24
    
    # Complex expression: every 5 minutes during working hours on weekdays
    cron = CronExpression("*/5 9-17 * * 1-5")
    assert 0 in cron.minutes
    assert 5 in cron.minutes
    assert 9 in cron.hours
    assert 17 in cron.hours
    assert 18 not in cron.hours
    assert 0 not in cron.dow # Sunday excluded
    assert 1 in cron.dow # Monday included


def test_cron_next_trigger():
    # Every hour at 30 minutes past
    cron = CronExpression("30 * * * *")
    
    # reference: Tuesday 2026-07-14 10:15:00 UTC (timestamp 1784024100)
    ref_time = 1784024100
    
    # Next should be 2026-07-14 10:30:00 UTC
    next_run = cron.next_trigger(ref_time)
    assert next_run == ref_time + 15 * 60
    
    # From 10:35, next should be 11:30
    next_run2 = cron.next_trigger(ref_time + 20 * 60)
    assert next_run2 == ref_time + 75 * 60

