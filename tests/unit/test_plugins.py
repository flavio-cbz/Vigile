#!/usr/bin/env python3
"""
YouCloud AI Admin — Sprint 2 Plugin Test Suite

Tests all Master-side plugins in isolation via the PluginManager.
No server or WebSocket required.
"""

import os
import sys
import tempfile
import time

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []


def check(name: str, condition: bool, detail: str = ""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition


# ─── 1. MetricsSnapshot Model ────────────────────────────────────────────
print("\n📊 MetricsSnapshot Model")

from master.plugins.metrics_plugin import MetricsSnapshot

# Valid full snapshot
snap = MetricsSnapshot(
    cpu_percent=45.2,
    cpu_load_1m=2.1,
    cpu_cores=8,
    mem_total_bytes=16_000_000_000,
    mem_used_bytes=8_000_000_000,
    mem_percent=50.0,
    disk_total_bytes=500_000_000_000,
    disk_used_bytes=250_000_000_000,
    disk_percent=50.0,
    uptime_seconds=3600 * 72,
    processes=245,
)
check("MetricsSnapshot: cpu_percent", snap.cpu_percent == 45.2)
check("MetricsSnapshot: mem_percent", snap.mem_percent == 50.0)
check("MetricsSnapshot: disk_percent", snap.disk_percent == 50.0)
check("MetricsSnapshot: uptime", snap.uptime_seconds == 259200.0)
check("MetricsSnapshot: mem_free derived", snap.mem_free_bytes == 8_000_000_000)
check("MetricsSnapshot: disk_free derived", snap.disk_free_bytes == 250_000_000_000)
check("MetricsSnapshot: processes", snap.processes == 245)
check("MetricsSnapshot: collected_at auto", snap.collected_at > 0)

# Default values (empty snapshot)
default_snap = MetricsSnapshot()
check("MetricsSnapshot: defaults cpu_percent=0", default_snap.cpu_percent == 0.0)
check("MetricsSnapshot: defaults mem_percent=0", default_snap.mem_percent == 0.0)
check("MetricsSnapshot: defaults disk_percent=0", default_snap.disk_percent == 0.0)
check("MetricsSnapshot: defaults uptime=0", default_snap.uptime_seconds == 0.0)
check("MetricsSnapshot: defaults mem_free=0", default_snap.mem_free_bytes == 0)
check("MetricsSnapshot: defaults disk_free=0", default_snap.disk_free_bytes == 0)
check("MetricsSnapshot: defaults cpu_cores=None", default_snap.cpu_cores is None)
check("MetricsSnapshot: defaults processes=None", default_snap.processes is None)

# Boundary validation
try:
    MetricsSnapshot(cpu_percent=-1)
    check("MetricsSnapshot: negative cpu_percent rejected", False)
except Exception:
    check("MetricsSnapshot: negative cpu_percent rejected", True)

try:
    MetricsSnapshot(cpu_percent=101)
    check("MetricsSnapshot: cpu_percent > 100 rejected", False)
except Exception:
    check("MetricsSnapshot: cpu_percent > 100 rejected", True)

try:
    MetricsSnapshot(mem_total_bytes=-100)
    check("MetricsSnapshot: negative mem_total rejected", False)
except Exception:
    check("MetricsSnapshot: negative mem_total rejected", True)

# Partial snapshot (only some fields)
partial = MetricsSnapshot(cpu_percent=80.0, mem_percent=70.0)
check("MetricsSnapshot: partial has cpu", partial.cpu_percent == 80.0)
check("MetricsSnapshot: partial has mem", partial.mem_percent == 70.0)
check("MetricsSnapshot: partial missing disk=0", partial.disk_percent == 0.0)
check("MetricsSnapshot: partial missing uptime=0", partial.uptime_seconds == 0.0)

# to_prometheus_labels
labels = snap.to_prometheus_labels()
check("Prometheus labels: cpu_percent", labels["cpu_percent"] == 45.2)
check("Prometheus labels: mem_percent", labels["mem_percent"] == 50.0)
check("Prometheus labels: uptime", labels["uptime_seconds"] == 259200.0)
check("Prometheus labels: has all keys",
      set(labels.keys()) == {"cpu_percent", "cpu_load_1m", "mem_percent",
                              "mem_used_bytes", "disk_percent", "disk_used_bytes",
                              "uptime_seconds"})

# model_dump_flat
flat = snap.model_dump_flat()
check("model_dump_flat: is dict", isinstance(flat, dict))
check("model_dump_flat: has cpu_percent", flat.get("cpu_percent") == 45.2)
check("model_dump_flat: has mem_total_bytes", flat.get("mem_total_bytes") == 16_000_000_000)


# ─── 2. Plugin Registration ──────────────────────────────────────────────
print("\n🔌 Plugin Registration")

from master.core.plugin_manager import PluginManager
from master.plugins.metrics_plugin import register as register_metrics

pm = PluginManager()
register_metrics(pm)

# Check hooks are registered
hooks = pm.get_hooks()
check("Plugin: 3 hooks registered", len(hooks) == 3, str(list(hooks.keys())))
check("Plugin: has get_supported_actions hook", "get_supported_actions" in hooks)
check("Plugin: has normalize_status_report hook", "normalize_status_report" in hooks)
check("Plugin: has on_status_report hook", "on_status_report" in hooks)

# Check each hook has the metrics plugin registered
for hook_name in ["get_supported_actions", "normalize_status_report", "on_status_report"]:
    check(f"Plugin: {hook_name} from 'metrics'", "metrics" in hooks[hook_name])


# ─── 3. Hook: get_supported_actions ──────────────────────────────────────
print("\n⚡ Hook: get_supported_actions")

actions = pm.call_first("get_supported_actions")
check("get_supported_actions returns list", isinstance(actions, list))
check("get_supported_actions has GET_STATS", "GET_STATS" in actions)

# Multiple calls return the same result
actions2 = pm.call_first("get_supported_actions")
check("get_supported_actions is stable", actions == actions2)

# Unknown plugin doesn't interfere
check("Empty hook returns None", pm.call_first("nonexistent_hook") is None)


# ─── 4. Hook: normalize_status_report ────────────────────────────────────
print("\n🔍 Hook: normalize_status_report")

# Valid flat report
flat_report = {
    "cpu_percent": 55.5,
    "mem_percent": 62.3,
    "mem_total_bytes": 8_000_000_000,
    "mem_used_bytes": 4_976_000_000,
    "disk_percent": 45.0,
    "disk_total_bytes": 250_000_000_000,
    "disk_used_bytes": 112_500_000_000,
    "uptime_seconds": 86400.0,
}
result = pm.call_first("normalize_status_report", raw_report=flat_report)
check("normalize: flat report valid", result is not None)
if result:
    check("normalize: cpu_percent preserved", result["cpu_percent"] == 55.5)
    check("normalize: mem_percent preserved", result["mem_percent"] == 62.3)
    check("normalize: disk_percent preserved", result["disk_percent"] == 45.0)

# Valid nested report (Worker sends { "type": "STATUS_REPORT", "metrics": {...} })
nested_report = {
    "type": "STATUS_REPORT",
    "node_id": "node-abc",
    "metrics": {
        "cpu_percent": 10.0,
        "mem_percent": 30.0,
        "mem_total_bytes": 4_000_000_000,
        "mem_used_bytes": 1_200_000_000,
        "disk_percent": 20.0,
        "disk_total_bytes": 100_000_000_000,
        "disk_used_bytes": 20_000_000_000,
        "uptime_seconds": 3600.0,
    },
}
result2 = pm.call_first("normalize_status_report", raw_report=nested_report)
check("normalize: nested report valid", result2 is not None)
if result2:
    check("normalize: nested cpu=10.0", result2["cpu_percent"] == 10.0)
    check("normalize: nested uptime=3600", result2["uptime_seconds"] == 3600.0)

# Invalid: None
result3 = pm.call_first("normalize_status_report", raw_report=None)
check("normalize: None rejected", result3 is None)

# Invalid: string
result4 = pm.call_first("normalize_status_report", raw_report="not a dict")
check("normalize: string rejected", result4 is None)

# Invalid: empty dict (all defaults — still valid since defaults are 0)
result5 = pm.call_first("normalize_status_report", raw_report={})
check("normalize: empty dict is valid (defaults)", result5 is not None)
if result5:
    check("normalize: empty dict cpu=0", result5["cpu_percent"] == 0.0)
    check("normalize: empty dict mem=0", result5["mem_percent"] == 0.0)

# Invalid: wrong field types (string where number expected)
result6 = pm.call_first("normalize_status_report",
                        raw_report={"cpu_percent": "not_a_number"})
check("normalize: wrong types rejected", result6 is None)

# Invalid: out of range
result7 = pm.call_first("normalize_status_report",
                        raw_report={"cpu_percent": 200.0})
check("normalize: out of range rejected", result7 is None)

# Very large numbers should be fine
result8 = pm.call_first("normalize_status_report", raw_report={
    "cpu_percent": 0.0,
    "mem_total_bytes": 10**15,
    "mem_used_bytes": 5 * 10**14,
    "mem_percent": 0.0,
    "disk_total_bytes": 10**15,
    "disk_used_bytes": 5 * 10**14,
    "disk_percent": 0.0,
    "uptime_seconds": 10**8,
})
check("normalize: large numbers OK", result8 is not None)

# Half-empty report still normalizes
result9 = pm.call_first("normalize_status_report", raw_report={
    "cpu_percent": 99.9,
    "uptime_seconds": 999999.0,
})
check("normalize: partial report OK", result9 is not None)
if result9:
    check("normalize: partial cpu=99.9", result9["cpu_percent"] == 99.9)
    check("normalize: partial uptime=999999", result9["uptime_seconds"] == 999999.0)
    # Defaults for missing fields
    check("normalize: partial defaults mem=0", result9["mem_percent"] == 0.0)
    check("normalize: partial defaults disk=0", result9["disk_percent"] == 0.0)


# ─── 5. Hook: on_status_report (async, persists to DB) ───────────────────
print("\n📝 Hook: on_status_report (async)")

import asyncio
from master.plugins.metrics_plugin import _on_status_report

# Valid call (db=None = graceful degradation: just logs)
async def test_on_status():
    try:
        await _on_status_report("node-test-01", result, db=None)
        check("on_status_report: valid call succeeds", True)
    except Exception:
        check("on_status_report: valid call succeeds", False)

    # Empty snapshot (all defaults)
    try:
        await _on_status_report("node-test-02", result5, db=None)
        check("on_status_report: empty snapshot succeeds", True)
    except Exception:
        check("on_status_report: empty snapshot succeeds", False)

    # via plugin manager async call
    try:
        await pm.async_call("on_status_report", node_id="node-async", snapshot=result, db=None)
        check("on_status_report: async_call succeeds", True)
    except Exception:
        check("on_status_report: async_call succeeds", False)

asyncio.run(test_on_status())


# ─── 6. Plugin loading from directory ────────────────────────────────────
print("\n📂 Plugin loading from directory")

# Create a real plugin dir with our metrics_plugin
with tempfile.TemporaryDirectory() as plugin_dir:
    import shutil
    plugin_src = os.path.join(PROJECT_ROOT, "master", "plugins", "metrics_plugin.py")
    plugin_dst = os.path.join(plugin_dir, "metrics_plugin.py")
    shutil.copy2(plugin_src, plugin_dst)

    pm2 = PluginManager()
    loaded = pm2.load_plugins_from_dir(plugin_dir)
    check("metrics_plugin loaded from dir", "metrics_plugin" in loaded, str(loaded))

    # Verify hooks work after loading
    actions = pm2.call_first("get_supported_actions")
    check("loaded plugin: get_supported_actions works",
          actions is not None and "GET_STATS" in actions)

    norm = pm2.call_first("normalize_status_report", raw_report=flat_report)
    check("loaded plugin: normalize_status_report works", norm is not None)


# ─── 7. Edge cases ───────────────────────────────────────────────────────
print("\n⚠️  Edge cases")

# MetricsSnapshot with only collected_at should work
ts_snap = MetricsSnapshot(collected_at=1234567890.0)
check("MetricsSnapshot: custom collected_at", ts_snap.collected_at == 1234567890.0)

# to_prometheus_labels with None values
none_labels = default_snap.to_prometheus_labels()
check("default prometheus labels: cpu_load_1m=0",
      none_labels["cpu_load_1m"] == 0.0)

# model_dump_flat includes all fields
all_keys = {
    "cpu_percent", "cpu_load_1m", "cpu_load_5m", "cpu_load_15m",
    "cpu_cores", "mem_total_bytes", "mem_used_bytes", "mem_percent",
    "swap_total_bytes", "swap_used_bytes",
    "disk_total_bytes", "disk_used_bytes", "disk_percent",
    "uptime_seconds", "processes", "collected_at",
}
flat_default = default_snap.model_dump_flat()
check("model_dump_flat: all fields present",
      set(flat_default.keys()) == all_keys,
      f"missing: {all_keys - set(flat_default.keys())}")

# Multiple normalizations from plugin manager
norm_a = pm.call_first("normalize_status_report", raw_report={
    "cpu_percent": 10.0, "mem_percent": 20.0,
    "mem_total_bytes": 1000, "mem_used_bytes": 200,
    "disk_total_bytes": 1000, "disk_used_bytes": 300,
    "disk_percent": 30.0, "uptime_seconds": 100.0,
})
norm_b = pm.call_first("normalize_status_report", raw_report={
    "cpu_percent": 90.0, "mem_percent": 80.0,
    "mem_total_bytes": 1000, "mem_used_bytes": 800,
    "disk_total_bytes": 1000, "disk_used_bytes": 900,
    "disk_percent": 90.0, "uptime_seconds": 200.0,
})
check("Multiple normalizations: different results", norm_a != norm_b)
check("Multiple normalizations: result A cpu=10", norm_a["cpu_percent"] == 10.0)
check("Multiple normalizations: result B cpu=90", norm_b["cpu_percent"] == 90.0)


# ─── 8. Integration: full STATUS_REPORT pipeline ─────────────────────────
print("\n🔄 Integration: full STATUS_REPORT pipeline")

# Simulate what _run_operational does:
#   raw msg → normalize_status_report → on_status_report
async def simulate_operational_status_report(pm, node_id: str, raw_msg: dict) -> bool:
    """Replicate the exact logic from worker_handler.py _run_operational."""
    snapshot = pm.call_first("normalize_status_report", raw_report=raw_msg)
    if snapshot is None:
        return False
    await pm.async_call("on_status_report", node_id=node_id, snapshot=snapshot, db=None)
    return True


# Valid STATUS_REPORT (flat format, as Worker would send it)
valid_msg = {
    "type": "STATUS_REPORT",
    "cpu_percent": 35.0,
    "mem_percent": 45.0,
    "mem_total_bytes": 8_000_000_000,
    "mem_used_bytes": 3_600_000_000,
    "disk_percent": 55.0,
    "disk_total_bytes": 500_000_000_000,
    "disk_used_bytes": 275_000_000_000,
    "uptime_seconds": 172800.0,
    "processes": 312,
}
async def run_integration():
    r = await simulate_operational_status_report(pm, "node-integration-01", valid_msg)
    check("Integration: valid STATUS_REPORT accepted", r)

    # Invalid STATUS_REPORT (cpu > 100)
    invalid_msg = {"type": "STATUS_REPORT", "cpu_percent": 150.0}
    r = await simulate_operational_status_report(pm, "node-integration-02", invalid_msg)
    check("Integration: invalid STATUS_REPORT rejected", not r)

    # STATUS_REPORT with nested metrics (alternative format)
    nested_msg = {
        "type": "STATUS_REPORT",
        "metrics": {
            "cpu_percent": 12.5,
            "mem_percent": 65.0,
            "mem_total_bytes": 16_000_000_000,
            "mem_used_bytes": 10_400_000_000,
            "disk_percent": 30.0,
            "disk_total_bytes": 1_000_000_000_000,
            "disk_used_bytes": 300_000_000_000,
            "uptime_seconds": 3600.0,
        },
    }
    r = await simulate_operational_status_report(pm, "node-integration-03", nested_msg)
    check("Integration: nested STATUS_REPORT accepted", r)

    # Minimal STATUS_REPORT (only required fields)
    minimal_msg = {"type": "STATUS_REPORT", "cpu_percent": 5.0, "mem_percent": 10.0}
    r = await simulate_operational_status_report(pm, "node-integration-04", minimal_msg)
    check("Integration: minimal STATUS_REPORT accepted", r)

    # STATUS_REPORT with extra fields (should be ignored, not crash)
    extra_msg = {
        "type": "STATUS_REPORT",
        "cpu_percent": 50.0,
        "mem_percent": 50.0,
        "unknown_field_1": "whatever",
        "nested_extra": {"a": 1},
    }
    r = await simulate_operational_status_report(pm, "node-integration-05", extra_msg)
    check("Integration: extra fields don't crash", r)

    # STATUS_REPORT with empty body (all defaults — still accepted)
    empty_msg = {"type": "STATUS_REPORT"}
    r = await simulate_operational_status_report(pm, "node-integration-06", empty_msg)
    check("Integration: empty STATUS_REPORT accepted (defaults)", r)

    # STATUS_REPORT with partially null values
    null_msg = {
        "type": "STATUS_REPORT",
        "cpu_percent": 0.0, "cpu_cores": None,
        "mem_percent": 0.0, "mem_total_bytes": 0, "mem_used_bytes": 0,
        "disk_percent": 0.0, "disk_total_bytes": 0, "disk_used_bytes": 0,
        "uptime_seconds": 0.0, "processes": None,
    }
    r = await simulate_operational_status_report(pm, "node-integration-07", null_msg)
    check("Integration: null values accepted", r)

asyncio.run(run_integration())


# ─── 9. Stress: rapid-fire STATUS_REPORT (10 in sequence) ────────────────
print("\n⚡ Stress: rapid-fire STATUS_REPORT (10 reports)")

reports = [
    {"cpu_percent": float(i * 10), "mem_percent": float(100 - i * 10),
     "mem_total_bytes": 1000, "mem_used_bytes": i * 100,
     "disk_total_bytes": 1000, "disk_used_bytes": i * 50,
     "disk_percent": float(i * 5), "uptime_seconds": float(i * 100)}
    for i in range(10)
]

async def run_stress():
    all_ok = True
    for report in reports:
        snap = pm.call_first("normalize_status_report", raw_report=report)
        if snap is None:
            all_ok = False
            break
        await pm.async_call("on_status_report", node_id="node-stress", snapshot=snap, db=None)
    return all_ok

all_accepted = asyncio.run(run_stress())
check(f"Stress: {len(reports)} sequential reports all accepted", all_accepted)

# Verify last report has correct values
final_snap = pm.call_first("normalize_status_report", raw_report=reports[-1])
check("Stress: last report cpu=90", final_snap["cpu_percent"] == 90.0)
check("Stress: last report mem=10", final_snap["mem_percent"] == 10.0)
check("Stress: last report disk=45", final_snap["disk_percent"] == 45.0)
check("Stress: last report uptime=900", final_snap["uptime_seconds"] == 900.0)


# ─── 10. Graceful degradation: no plugin loaded ──────────────────────────
print("\n🛡️  Graceful degradation: no plugin loaded")

pm_empty = PluginManager()
# No plugins registered

# Should return None, not crash
noop_snap = pm_empty.call_first("normalize_status_report", raw_report=valid_msg)
check("No plugin: normalize returns None", noop_snap is None)

# Should return [], not crash
async def test_noop_async():
    noop_results = await pm_empty.async_call("on_status_report", node_id="test", snapshot={})
    check("No plugin: async_call returns []", noop_results == [])

asyncio.run(test_noop_async())

# call_first with nonexistent hook returns None
check("No plugin: call_first nonexistent returns None",
      pm_empty.call_first("get_supported_actions") is None)


# ─── Summary ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    print("\nFailed tests:")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
    sys.exit(1)
else:
    print(" 🎉")
