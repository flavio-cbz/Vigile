# Security Review: WP11 (Alert Engine) & WP12 (Code Quality) Changes

**Date:** 2026-07-28  
**Scope:** `master/core/alert_engine.py`, `master/core/automation_engine.py`, `master/core/plugin_helpers.py`, `master/core/plugin_utils.py`, `master/api/services.py`, `master/core/node_manager.py`, `master/core/insights.py`  
**Reviewer:** Automated security analysis  
**Classification:** Internal

---

## Executive Summary

The WP11/WP12 changes introduce several important security improvements (transaction wrapping, LoopBoundLock, SSRF protection, template injection fix, rate limiting). However, the review identified **3 CRITICAL**, **5 HIGH**, **4 MEDIUM**, and **3 LOW** severity issues. The most severe is a **CRITICAL SSRF bypass** in the webhook URL validation that allows domain-name-based attacks against internal services and cloud metadata endpoints.

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 5     |
| MEDIUM   | 4     |
| LOW      | 3     |
| **Total**| **15**|

---

## 1. SSRF Protection in `_is_safe_webhook_url` — CRITICAL

**File:** `master/core/automation_engine.py`, lines 784-808  
**Method:** `AutomationEngine._is_safe_webhook_url`

### Current Implementation

```python
@staticmethod
def _is_safe_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.hostname:
        return False
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    except ValueError:
        if parsed.hostname in ("metadata.google.internal", "169.254.169.254"):
            return False
    return True
```

### Findings

#### CRITICAL-1: Domain names bypass all IP-based checks (no DNS resolution)

When `parsed.hostname` is a domain name (e.g., `evil.com`), `ipaddress.ip_address()` raises `ValueError`, and the code falls into the `except ValueError` branch. This branch only checks for two hardcoded hostnames (`metadata.google.internal` and `169.254.169.254`). It does **not** resolve the domain name to an IP address. An attacker can register a domain that resolves to `127.0.0.1`, `10.0.0.1`, `169.254.169.254`, or any other internal address, completely bypassing the SSRF protection.

**Exploit scenario:**
1. Attacker creates automation rule with webhook URL `http://attacker.com/webhook`
2. `attacker.com` resolves to `169.254.169.254` (AWS metadata endpoint)
3. `_is_safe_webhook_url("http://attacker.com/webhook")` returns `True`
4. `httpx.AsyncClient.post()` sends the request to the metadata endpoint
5. Attacker exfiltrates cloud credentials, IAM tokens, or other sensitive data

**Remediation:** Resolve the hostname via DNS before checking. Use `socket.getaddrinfo()` to resolve the domain, then check all resolved IPs against the private/loopback/link-local/reserved/multicast filters.

#### CRITICAL-2: No DNS rebinding protection

Even if DNS resolution is added, there is no protection against DNS rebinding. An attacker could return a public IP at validation time and switch to a private IP before the HTTP request is sent.

**Remediation:** Resolve the hostname, make the HTTP request, and verify the connection's actual remote address matches the validated IP. Alternatively, use a custom HTTP transport that enforces IP allow-listing at the connection level.

#### CRITICAL-3: Redirect following bypasses SSRF check

`httpx.AsyncClient` follows redirects by default (up to 20 redirects). An attacker can set up a webhook URL that initially returns a `302` redirect to `http://169.254.169.254` or `http://127.0.0.1`. The initial URL passes the SSRF check (it's a public domain), but the redirect target is an internal address.

**Exploit scenario:**
1. Attacker creates automation rule with webhook URL `http://evil.com/redirect`
2. `evil.com/redirect` returns `302 Location: http://169.254.169.254/latest/meta-data/`
3. `_is_safe_webhook_url("http://evil.com/redirect")` returns `True` (evil.com is public)
4. `httpx.AsyncClient` follows the redirect to the metadata endpoint
5. Attacker exfiltrates cloud metadata

**Remediation:** Disable redirect following (`follow_redirects=False`) or validate redirect targets against the same SSRF rules.

### Additional SSRF Issues

#### HIGH-4: No port restriction

The SSRF check does not restrict the port. An attacker can target internal services on any port (e.g., `http://10.0.0.1:6379` for Redis, `http://10.0.0.1:5432` for PostgreSQL). While the IP check would catch `10.0.0.1`, if the domain-name bypass (CRITICAL-1) is exploited, any port is accessible.

**Remediation:** Restrict to common HTTP/HTTPS ports (80, 443, 8080, 8443) or require explicit port allow-listing.

#### HIGH-5: `169.254.169.254` check is dead code

`169.254.169.254` is a valid IP address. `ipaddress.ip_address("169.254.169.254")` succeeds, and `ip.is_link_local` returns `True` (since `169.24.0.0/16` is the link-local range). Therefore, the check `if parsed.hostname in ("metadata.google.internal", "169.254.169.254")` in the `except ValueError` branch is **dead code** for `169.254.169.254` — it would never be reached because the IP is caught by the `ip.is_link_local` check. Only `metadata.google.internal` (a hostname) is actually caught by this branch.

**Remediation:** Remove the dead code and add proper DNS resolution for all hostnames.

---

## 2. Template Injection Fix — MEDIUM

**File:** `master/core/automation_engine.py`, lines 824-838  
**Method:** `AutomationEngine._execute_call_webhook`

### Current Implementation

```python
body_template = action.get("body_template", "{}")
try:
    placeholders = set(re.findall(r"\{(\w+)\}", body_template))
    allowed = {"node_id", "trigger_data"}
    if not placeholders.issubset(allowed):
        raise ValueError(
            f"Unknown placeholders in body_template: {placeholders - allowed}"
        )
    body_str = body_template.format(
        node_id=str(node_id),
        trigger_data=json.dumps(trigger_data),
    )
    body = json.loads(body_str)
except Exception:
    body = {"node_id": node_id, "trigger_data": trigger_data}
```

### Findings

#### MEDIUM-6: Regex does not catch attribute access, item access, or format specs

The regex `\{(\w+)\}` only matches `{word}` patterns. It does **not** match:
- `{node_id.__class__}` — attribute access
- `{node_id[0]}` — item access
- `{node_id:>10}` — format spec

These patterns pass through the placeholder check undetected and are processed by `str.format()`. While the provided objects are strings (limiting the risk), an attacker could use `{trigger_data[0]}` to extract individual characters from the JSON-serialized trigger data, or `{node_id.__class__}` to leak type information.

**Exploit scenario:**
1. Attacker creates automation rule with `body_template = '{"x": "{trigger_data[0]}"}'`
2. Regex finds no placeholders (no `{word}` pattern matches)
3. `str.format()` processes `{trigger_data[0]}`, returning the first character of the JSON string
4. If `trigger_data` contains sensitive information (e.g., node IDs, action params), individual characters could be extracted

**Remediation:** Use a stricter regex that catches all format patterns, or use `string.Formatter().parse()` to enumerate all replacement fields and validate them.

#### MEDIUM-7: Broad `except Exception` silently swallows placeholder validation errors

The `except Exception` block catches both the `ValueError` from the placeholder check AND any `json.JSONDecodeError` from `json.loads()`. When a malicious template with unknown placeholders is detected, the `ValueError` is silently caught and the code falls back to a safe default body. While this is fail-closed (safe), it means:
1. The error is never logged, making attack detection impossible
2. The operator receives no feedback that their template was rejected
3. The webhook receives a generic body instead of the intended payload

**Remediation:** Separate the placeholder validation from the JSON parsing. Log rejected templates and raise a clear error to the operator.

#### MEDIUM-8: No length limit on `body_template`

The `body_template` field has no length restriction. An attacker could provide a very large template string, causing excessive memory usage or slow regex processing.

**Remediation:** Add a maximum length check (e.g., 4096 characters) on `body_template`.

---

## 3. Transaction Wrapping — HIGH

**Files:** `master/core/insights.py`, `master/core/node_manager.py`

### Findings

#### HIGH-9: `insights.py` `_auto_profiling_intent` uses separate transactions for INSERT + UPDATE

**File:** `master/core/insights.py`, lines 257-307

The method performs three separate DB operations:
1. `INSERT INTO action_proposals` (line 257) + `commit()` (line 269)
2. `UPDATE action_proposals` (line 285) + `commit()` (line 295)
3. `log_action` (line 297) — which does its own `INSERT INTO audit_log` + `commit()`

These are **not** wrapped in a `transaction()` context. If the INSERT succeeds but the UPDATE fails, the proposal is left in an inconsistent state (created but not updated with the result). The AGENTS.md explicitly states: "Multi-statement DB mutations in core paths without a `transaction()` context (sequence conflicts on the shared aiosqlite connection)."

**Remediation:** Wrap the INSERT + UPDATE + audit log in a single `transaction()` context.

#### HIGH-10: `insights.py` `generate_profile` not wrapped in transaction

**File:** `master/core/insights.py`, lines 205-222

The `UPDATE nodes` statement is not wrapped in `transaction()`. While it's a single statement, the AGENTS.md convention requires `transaction()` for all DB mutations in core paths.

**Remediation:** Wrap in `transaction()`.

#### HIGH-11: `node_manager.py` multiple methods not wrapped in transaction

**File:** `master/core/node_manager.py`

Several methods perform multi-statement mutations without `transaction()`:
- `transition_state` (line 449): UPDATE + `log_action` (INSERT) — separate commits
- `delete_node` (line 508): `log_action` (INSERT) + DELETE — separate commits
- `set_disabled` (line 613): UPDATE + `transition_state` + `log_action` — separate commits
- `patch_metadata` (line 679): `log_action` (INSERT) + UPDATE — separate commits
- `invalidate_join_tokens` (line 703): SELECT + UPDATE — separate commits

These create TOCTOU windows where the DB state is inconsistent between statements.

**Remediation:** Wrap all multi-statement mutations in `transaction()`.

---

## 4. LoopBoundLock Usage — HIGH

**Files:** `master/core/alert_engine.py`, `master/core/automation_engine.py`, `master/core/node_manager.py`

### Findings

#### HIGH-12: `node_manager.py` `_check_heartbeats` accesses `_connections` outside lock

**File:** `master/core/node_manager.py`, lines 928-972

The `_check_heartbeats` method acquires the lock to snapshot connections (line 933), then iterates over the snapshot outside the lock. During iteration, it calls `self.unregister_connection(node_id)` (line 940) and `self.transition_state(db, node_id, NodeState.LOST)` (line 942). The `unregister_connection` method acquires the lock again, which is safe (asyncio locks are reentrant within the same task). However, `transition_state` does NOT acquire the lock, and it modifies the `nodes` table. If another task is simultaneously modifying the same node's state, a race condition could occur.

More importantly, the `connected_node_ids()` method (line 786) explicitly notes: "snapshot without lock — safe for debugging/admin display only." This method is called from `update_all_nodes_cache` (line 223) and `get_node` (line 984), which access `self._connections` without holding the lock.

**Remediation:** Ensure all access to `_connections` is protected by the lock, or use a thread-safe data structure.

#### HIGH-13: `automation_engine.py` rule list copied under lock but evaluated outside

**File:** `master/core/automation_engine.py`, lines 231-245

The `evaluate_metric_trigger` method copies `self._rules` under the lock (line 232), then evaluates rules outside the lock. During evaluation, `_fire_rule` is called as a spawned task (line 242). If `reload_rules` is called concurrently (which replaces `self._rules`), the spawned task may reference stale rule objects. While this is not a security vulnerability per se, it could lead to inconsistent behavior.

**Remediation:** This is acceptable for the current use case (rules are reloaded infrequently and stale references are harmless). No action needed, but document the behavior.

---

## 5. Information Leakage — MEDIUM

**File:** `master/core/automation_engine.py`

### Findings

#### MEDIUM-14: SSRF rejection error leaks the URL

**File:** `master/core/automation_engine.py`, line 817

```python
raise ValueError(f"Webhook URL blocked by SSRF protection: {url}")
```

The error message includes the full URL, which may contain sensitive information in the query string (e.g., API keys, tokens). This error is raised in `_execute_call_webhook`, which is called from `_execute_action`, which is called from `_fire_rule`. The exception is caught at line 607:

```python
except Exception as exc:
    logger.exception("Action %s in rule %s failed.", action.get("type"), rule_id)
    results.append({"action": action.get("type"), "error": str(exc), "status": "error"})
```

The `str(exc)` is stored in the `results` dict, which is persisted to `automation_logs` (line 629). This means the URL is persisted in the database and could be exposed via the API.

**Remediation:** Do not include the URL in the error message. Use a generic message like "Webhook URL blocked by SSRF protection" and log the URL separately at debug level.

---

## 6. Rate Limiting — LOW

**File:** `master/core/alert_engine.py`

### Findings

#### LOW-15: Rate limiter uses in-memory state, no persistence

**File:** `master/core/alert_engine.py`, lines 604-615

The `_is_rate_limited` method uses an in-memory `defaultdict(list)` for rate limiting. If the process restarts, the rate limiter state is lost, and alert storms can resume. The AGENTS.md notes this is a concern for the DISK_SCAN `force=true` parameter, and the same applies to alert firing.

**Remediation:** This is acceptable for the current implementation. The rate limiter prevents alert storms within a single process lifetime. For cross-process or cross-restart rate limiting, consider persisting the rate limiter state to the DB.

---

## 7. Transaction Wrapping in `alert_engine.py` — Verified Correct

**File:** `master/core/alert_engine.py`

All DB mutations in `alert_engine.py` are properly wrapped in `transaction()`:
- `_fire_alert` (line 507): INSERT into `alerts` — wrapped
- `_resolve_alert` (line 582): UPDATE `alerts` — wrapped
- `cleanup_orphaned_alerts` (line 652): DELETE from `alerts` — wrapped
- `cleanup_old_alerts` (line 697): DELETE from `alerts` — wrapped

No issues found.

---

## 8. Transaction Wrapping in `automation_engine.py` — Verified Correct

**File:** `master/core/automation_engine.py`

All DB mutations in `automation_engine.py` are properly wrapped in `transaction()`:
- `_persist_cooldown` (line 180): INSERT/UPSERT `automation_cooldowns` — wrapped
- `_persist_proposal_update` (line 653): UPDATE `action_proposals` — wrapped
- `_execute_send_intent` (lines 696, 736): INSERT `action_proposals` + `log_action` — wrapped
- `_write_log` (line 857): INSERT `automation_logs` — wrapped

No issues found.

---

## 9. Plugin Helpers and `parse_worker_list` — Verified Correct

**Files:** `master/core/plugin_helpers.py`, `master/core/plugin_utils.py`

The `plugin_helpers.py` re-exports `parse_worker_list`, `parse_worker_object`, and `parse_worker_output` from `plugin_utils.py`. These functions use Pydantic model validation, which provides:
- Type checking on all fields
- `extra="forbid"` rejection (if the model is configured with it)
- Fail-closed behavior on invalid input

The `node_manager.py` and `insights.py` refactors to use `parse_worker_list` are correct and do not introduce new injection vectors.

**Note:** The Pydantic models (`ServiceInfo`, `ContainerSummary`) should be verified to have `extra="forbid"` configured. If they don't, extra fields from malicious workers would be silently ignored rather than rejected.

---

## 10. LoopBoundLock Usage — Verified Correct

**Files:** `master/core/alert_engine.py`, `master/core/automation_engine.py`, `master/core/node_manager.py`, `master/core/audit.py`

All three files correctly use `LoopBoundLock` instead of bare `asyncio.Lock`:
- `alert_engine.py` (line 203): `self._lock = LoopBoundLock()` — protects `_active_alerts`, `_last_snapshot`, `_intent_failures`, `_reconnect_counts`, `_alert_rate_limiter`
- `automation_engine.py` (line 108): `self._lock = LoopBoundLock()` — protects `_rules`, `_cooldowns`
- `node_manager.py` (line 133): `self._lock: Any = LoopBoundLock()` — protects `_connections`, `_pending_intents`, `_intent_nodes`
- `audit.py` (line 75): `_audit_lock = LoopBoundLock()` — serializes audit log writes

No loop-mismatch issues found.

---

## Summary of Remediation Priorities

| Priority | Finding | File | Action |
|----------|---------|------|--------|
| P0 | CRITICAL-1: Domain names bypass SSRF check | `automation_engine.py:784` | Add DNS resolution |
| P0 | CRITICAL-2: No DNS rebinding protection | `automation_engine.py:784` | Validate connection IP |
| P0 | CRITICAL-3: Redirect following bypasses SSRF | `automation_engine.py:840` | Disable redirects |
| P1 | HIGH-9: `_auto_profiling_intent` missing transaction | `insights.py:257` | Wrap in `transaction()` |
| P1 | HIGH-10: `generate_profile` missing transaction | `insights.py:205` | Wrap in `transaction()` |
| P1 | HIGH-11: `node_manager.py` missing transactions | `node_manager.py:449,508,613,679,703` | Wrap in `transaction()` |
| P1 | HIGH-12: `_check_heartbeats` lock scope | `node_manager.py:928` | Review lock scope |
| P2 | MEDIUM-6: Template regex misses attribute access | `automation_engine.py:826` | Use `string.Formatter().parse()` |
| P2 | MEDIUM-7: Broad except swallows errors | `automation_engine.py:837` | Separate error handling |
| P2 | MEDIUM-8: No template length limit | `automation_engine.py:824` | Add max length check |
| P2 | MEDIUM-14: URL leaked in error message | `automation_engine.py:817` | Generic error message |
| P3 | LOW-15: Rate limiter not persisted | `alert_engine.py:604` | Document limitation |

---

## Regression Check

No regressions from previous security fixes were identified. The changes correctly:
- Use `LoopBoundLock` instead of bare `asyncio.Lock` (prevents loop-mismatch errors)
- Wrap DB mutations in `transaction()` contexts (prevents sequence conflicts)
- Implement SSRF protection (though incomplete — see CRITICAL findings)
- Implement template injection prevention (though incomplete — see MEDIUM findings)
- Implement rate limiting for alert firing (prevents alert storms)
- Use Pydantic validation for worker output parsing (fail-closed)
- Spawn supervised background tasks (prevents orphaned tasks on shutdown)
- Persist cooldown state (prevents duplicate automation triggers)
