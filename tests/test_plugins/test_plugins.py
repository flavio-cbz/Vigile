from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from master.core.plugin_manager import PluginManager
from master.plugins.metrics import MetricsSnapshot, _on_status_report
from master.plugins.metrics import register as register_metrics


# 1. MetricsSnapshot Model Tests
def test_metrics_snapshot_valid():
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
    assert snap.cpu_percent == 45.2
    assert snap.mem_percent == 50.0
    assert snap.disk_percent == 50.0
    assert snap.uptime_seconds == 259200.0
    assert snap.mem_free_bytes == 8_000_000_000
    assert snap.disk_free_bytes == 250_000_000_000
    assert snap.processes == 245
    assert snap.collected_at > 0


def test_metrics_snapshot_defaults():
    default_snap = MetricsSnapshot()
    assert default_snap.cpu_percent == 0.0
    assert default_snap.mem_percent == 0.0
    assert default_snap.disk_percent == 0.0
    assert default_snap.uptime_seconds == 0.0
    assert default_snap.mem_free_bytes == 0
    assert default_snap.disk_free_bytes == 0
    assert default_snap.cpu_cores is None
    assert default_snap.processes is None


def test_metrics_snapshot_validation():
    with pytest.raises(ValidationError):
        MetricsSnapshot(cpu_percent=-1)
    with pytest.raises(ValidationError):
        MetricsSnapshot(cpu_percent=101)
    with pytest.raises(ValidationError):
        MetricsSnapshot(mem_total_bytes=-100)


def test_metrics_snapshot_partial():
    partial = MetricsSnapshot(cpu_percent=80.0, mem_percent=70.0)
    assert partial.cpu_percent == 80.0
    assert partial.mem_percent == 70.0
    assert partial.disk_percent == 0.0
    assert partial.uptime_seconds == 0.0


def test_prometheus_labels():
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
    labels = snap.to_prometheus_labels()
    assert labels["cpu_percent"] == 45.2
    assert labels["mem_percent"] == 50.0
    assert labels["uptime_seconds"] == 259200.0
    assert set(labels.keys()) == {
        "cpu_percent",
        "cpu_load_1m",
        "mem_percent",
        "mem_used_bytes",
        "disk_percent",
        "disk_used_bytes",
        "uptime_seconds",
    }


def test_model_dump_flat():
    snap = MetricsSnapshot(
        cpu_percent=45.2,
        mem_total_bytes=16_000_000_000,
    )
    flat = snap.model_dump_flat()
    assert isinstance(flat, dict)
    assert flat.get("cpu_percent") == 45.2
    assert flat.get("mem_total_bytes") == 16_000_000_000


# 2. Plugin Registration Tests
def test_plugin_registration():
    pm = PluginManager()
    register_metrics(pm)
    hooks = pm.get_hooks()
    assert len(hooks) == 3
    assert "get_supported_actions" in hooks
    assert "normalize_status_report" in hooks
    assert "on_status_report" in hooks
    for hook_name in ["get_supported_actions", "normalize_status_report", "on_status_report"]:
        assert "metrics" in hooks[hook_name]


# 3. Hook get_supported_actions
def test_get_supported_actions():
    pm = PluginManager()
    register_metrics(pm)
    actions = pm.call_first("get_supported_actions")
    assert isinstance(actions, list)
    assert "GET_STATS" in actions

    actions2 = pm.call_first("get_supported_actions")
    assert actions == actions2
    assert pm.call_first("nonexistent_hook") is None


# 4. Hook: normalize_status_report
def test_normalize_status_report():
    pm = PluginManager()
    register_metrics(pm)

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
    assert result is not None
    assert result["cpu_percent"] == 55.5
    assert result["mem_percent"] == 62.3
    assert result["disk_percent"] == 45.0

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
    assert result2 is not None
    assert result2["cpu_percent"] == 10.0
    assert result2["uptime_seconds"] == 3600.0

    assert pm.call_first("normalize_status_report", raw_report=None) is None
    assert pm.call_first("normalize_status_report", raw_report="not a dict") is None

    result5 = pm.call_first("normalize_status_report", raw_report={})
    assert result5 is not None
    assert result5["cpu_percent"] == 0.0
    assert result5["mem_percent"] == 0.0

    assert (
        pm.call_first("normalize_status_report", raw_report={"cpu_percent": "not_a_number"}) is None
    )
    assert pm.call_first("normalize_status_report", raw_report={"cpu_percent": 200.0}) is None

    result8 = pm.call_first(
        "normalize_status_report",
        raw_report={
            "cpu_percent": 0.0,
            "mem_total_bytes": 10**15,
            "mem_used_bytes": 5 * 10**14,
            "mem_percent": 0.0,
            "disk_total_bytes": 10**15,
            "disk_used_bytes": 5 * 10**14,
            "disk_percent": 0.0,
            "uptime_seconds": 10**8,
        },
    )
    assert result8 is not None

    result9 = pm.call_first(
        "normalize_status_report",
        raw_report={
            "cpu_percent": 99.9,
            "uptime_seconds": 999999.0,
        },
    )
    assert result9 is not None
    assert result9["cpu_percent"] == 99.9
    assert result9["uptime_seconds"] == 999999.0
    assert result9["mem_percent"] == 0.0
    assert result9["disk_percent"] == 0.0


# 5. Hook: on_status_report
@pytest.mark.asyncio
async def test_on_status_report():
    pm = PluginManager()
    register_metrics(pm)

    result = {
        "cpu_percent": 55.5,
        "mem_percent": 62.3,
        "uptime_seconds": 86400.0,
    }

    # Valid call (db=None = graceful degradation: just logs)
    await _on_status_report("node-test-01", result, db=None)
    await _on_status_report("node-test-02", {}, db=None)
    await pm.async_call("on_status_report", node_id="node-async", snapshot=result, db=None)


# 6. Plugin loading from directory
@pytest.mark.asyncio
async def test_plugin_loading_from_dir(tmp_path):
    import pathlib

    project_root = pathlib.Path(__file__).parent.parent.parent
    plugin_src = project_root / "master" / "plugins" / "metrics" / "__init__.py"
    plugin_dst = tmp_path / "metrics.py"
    shutil.copy2(plugin_src, plugin_dst)

    pm2 = PluginManager()
    loaded = await pm2.load_plugins_from_dir(str(tmp_path))
    assert "metrics" in loaded

    actions = pm2.call_first("get_supported_actions")
    assert actions is not None
    assert "GET_STATS" in actions

    flat_report = {"cpu_percent": 55.5}
    norm = pm2.call_first("normalize_status_report", raw_report=flat_report)
    assert norm is not None


# 7. Edge cases
def test_plugin_edge_cases():
    default_snap = MetricsSnapshot()
    ts_snap = MetricsSnapshot(collected_at=1234567890.0)
    assert ts_snap.collected_at == 1234567890.0

    none_labels = default_snap.to_prometheus_labels()
    assert none_labels["cpu_load_1m"] == 0.0

    all_keys = {
        # CPU
        "cpu_percent",
        "cpu_load_1m",
        "cpu_load_5m",
        "cpu_load_15m",
        "cpu_cores",
        "cpu_throttled_count",
        # Memory
        "mem_total_bytes",
        "mem_used_bytes",
        "mem_percent",
        # Swap
        "swap_total_bytes",
        "swap_used_bytes",
        # Disk (usage)
        "disk_total_bytes",
        "disk_used_bytes",
        "disk_percent",
        # Disk I/O
        "disk_reads",
        "disk_writes",
        "disk_read_bytes",
        "disk_write_bytes",
        # Network I/O
        "net_bytes_recv",
        "net_bytes_sent",
        "net_packets_recv",
        "net_packets_sent",
        "net_errors_in",
        "net_errors_out",
        "net_drops_in",
        "net_drops_out",
        # Temperature
        "temp_celsius",
        # PSI
        "psi_cpu_avg10",
        "psi_mem_avg10",
        "psi_io_avg10",
        # File handles
        "file_handles_used",
        "file_handles_max",
        # Entropy / Context switches
        "entropy_avail",
        "context_switches",
        # Legacy
        "uptime_seconds",
        "processes",
        "top_processes",
        "collected_at",
        "disks",
    }
    flat_default = default_snap.model_dump_flat()
    assert set(flat_default.keys()) == all_keys

    pm = PluginManager()
    register_metrics(pm)
    norm_a = pm.call_first(
        "normalize_status_report",
        raw_report={
            "cpu_percent": 10.0,
            "mem_percent": 20.0,
            "mem_total_bytes": 1000,
            "mem_used_bytes": 200,
            "disk_total_bytes": 1000,
            "disk_used_bytes": 300,
            "disk_percent": 30.0,
            "uptime_seconds": 100.0,
        },
    )
    norm_b = pm.call_first(
        "normalize_status_report",
        raw_report={
            "cpu_percent": 90.0,
            "mem_percent": 80.0,
            "mem_total_bytes": 1000,
            "mem_used_bytes": 800,
            "disk_total_bytes": 1000,
            "disk_used_bytes": 900,
            "disk_percent": 90.0,
            "uptime_seconds": 200.0,
        },
    )
    assert norm_a != norm_b
    assert norm_a["cpu_percent"] == 10.0
    assert norm_b["cpu_percent"] == 90.0


# 8. Integration: full STATUS_REPORT pipeline
async def simulate_operational_status_report(pm, node_id: str, raw_msg: dict) -> bool:
    snapshot = pm.call_first("normalize_status_report", raw_report=raw_msg)
    if snapshot is None:
        return False
    await pm.async_call("on_status_report", node_id=node_id, snapshot=snapshot, db=None)
    return True


@pytest.mark.asyncio
async def test_integration_pipeline():
    pm = PluginManager()
    register_metrics(pm)

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
    r = await simulate_operational_status_report(pm, "node-integration-01", valid_msg)
    assert r

    invalid_msg = {"type": "STATUS_REPORT", "cpu_percent": 150.0}
    r = await simulate_operational_status_report(pm, "node-integration-02", invalid_msg)
    assert not r

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
    assert r

    minimal_msg = {"type": "STATUS_REPORT", "cpu_percent": 5.0, "mem_percent": 10.0}
    r = await simulate_operational_status_report(pm, "node-integration-04", minimal_msg)
    assert r

    extra_msg = {
        "type": "STATUS_REPORT",
        "cpu_percent": 50.0,
        "mem_percent": 50.0,
        "unknown_field_1": "whatever",
        "nested_extra": {"a": 1},
    }
    r = await simulate_operational_status_report(pm, "node-integration-05", extra_msg)
    assert r

    empty_msg = {"type": "STATUS_REPORT"}
    r = await simulate_operational_status_report(pm, "node-integration-06", empty_msg)
    assert r

    null_msg = {
        "type": "STATUS_REPORT",
        "cpu_percent": 0.0,
        "cpu_cores": None,
        "mem_percent": 0.0,
        "mem_total_bytes": 0,
        "mem_used_bytes": 0,
        "disk_percent": 0.0,
        "disk_total_bytes": 0,
        "disk_used_bytes": 0,
        "uptime_seconds": 0.0,
        "processes": None,
    }
    r = await simulate_operational_status_report(pm, "node-integration-07", null_msg)
    assert r


# 9. Stress Tests
@pytest.mark.asyncio
async def test_stress_sequential_reports():
    pm = PluginManager()
    register_metrics(pm)

    reports = [
        {
            "cpu_percent": float(i * 10),
            "mem_percent": float(100 - i * 10),
            "mem_total_bytes": 1000,
            "mem_used_bytes": i * 100,
            "disk_total_bytes": 1000,
            "disk_used_bytes": i * 50,
            "disk_percent": float(i * 5),
            "uptime_seconds": float(i * 100),
        }
        for i in range(10)
    ]

    all_ok = True
    for report in reports:
        snap = pm.call_first("normalize_status_report", raw_report=report)
        if snap is None:
            all_ok = False
            break
        await pm.async_call("on_status_report", node_id="node-stress", snapshot=snap, db=None)
    assert all_ok

    final_snap = pm.call_first("normalize_status_report", raw_report=reports[-1])
    assert final_snap["cpu_percent"] == 90.0
    assert final_snap["mem_percent"] == 10.0
    assert final_snap["disk_percent"] == 45.0
    assert final_snap["uptime_seconds"] == 900.0


# 10. Graceful Degradation
@pytest.mark.asyncio
async def test_graceful_degradation():
    pm_empty = PluginManager()
    valid_msg = {"cpu_percent": 35.0}

    noop_snap = pm_empty.call_first("normalize_status_report", raw_report=valid_msg)
    assert noop_snap is None

    noop_results = await pm_empty.async_call("on_status_report", node_id="test", snapshot={})
    assert noop_results == []

    assert pm_empty.call_first("get_supported_actions") is None
