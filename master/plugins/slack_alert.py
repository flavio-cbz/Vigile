"""
Vigile — Slack Alerts Plugin
Sends real-time warning alerts to a Slack channel webhook if resource limits are exceeded.
"""

import json
import sys
from typing import Any

# Default settings
DEFAULT_CPU_LIMIT = 85
DEFAULT_MEM_LIMIT = 85


def register(pm) -> None:
    pm.register("on_status_report", _on_status_report, plugin_name="slack_alert")
    pm.register("get_supported_actions", _get_supported_actions, plugin_name="slack_alert")


def get_config_schema() -> dict[str, Any]:
    return {
        "name": "Slack Alerts",
        "description": "Send alert notifications to a Slack webhook on high resource usage.",
        "category": "Notifications",
        "schema": {
            "webhook_url": {
                "type": "string",
                "title": "Webhook URL",
                "default": "",
                "description": "Slack Incoming Webhook URL (starts with https://hooks.slack.com/services/)",
            },
            "cpu_threshold": {
                "type": "integer",
                "title": "CPU Usage Threshold (%)",
                "default": DEFAULT_CPU_LIMIT,
                "description": "Trigger an alert if CPU usage exceeds this threshold.",
            },
            "mem_threshold": {
                "type": "integer",
                "title": "Memory Usage Threshold (%)",
                "default": DEFAULT_MEM_LIMIT,
                "description": "Trigger an alert if memory usage exceeds this threshold.",
            },
        },
    }


def _get_supported_actions() -> list[str]:
    return []


async def _on_status_report(node_id: str, snapshot: dict, db=None) -> None:
    if not db:
        return

    # 1. Fetch plugin config from DB
    try:
        cursor = await db.execute(
            "SELECT config_json FROM plugin_configs WHERE plugin_id = 'slack_alert'"
        )
        row = await cursor.fetchone()
        if not row:
            return
        config = json.loads(row["config_json"])
    except Exception as e:
        print(f"slack_alert: Failed to query config: {e}", file=sys.stderr)
        return

    webhook_url = config.get("webhook_url", "").strip()
    if not webhook_url or not webhook_url.startswith("http"):
        return

    cpu_threshold = config.get("cpu_threshold", DEFAULT_CPU_LIMIT)
    mem_threshold = config.get("mem_threshold", DEFAULT_MEM_LIMIT)

    cpu = snapshot.get("cpu_percent", 0.0)
    mem = snapshot.get("mem_percent", 0.0)

    alerts = []
    if cpu > cpu_threshold:
        alerts.append(f"• *CPU critique* : {cpu:.1f}% (seuil : {cpu_threshold}%)")
    if mem > mem_threshold:
        alerts.append(f"• *Mémoire critique* : {mem:.1f}% (seuil : {mem_threshold}%)")

    if not alerts:
        return

    # 2. Build Slack Blocks payload
    import httpx

    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🚨 *Alerte Vigile — Serveur `{node_id}`* 🚨",
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(alerts)},
            },
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(webhook_url, json=payload)
            if res.status_code >= 400:
                print(
                    f"slack_alert: Slack returned status {res.status_code}: {res.text}",
                    file=sys.stderr,
                )
    except Exception as e:
        print(f"slack_alert: Failed to deliver alert to Slack: {e}", file=sys.stderr)
