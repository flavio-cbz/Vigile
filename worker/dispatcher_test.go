package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

// newTestWC creates a minimal WorkerConn for dispatch tests.
// It uses a background context so handlers don't fail on cancellation.
func newTestWC(t *testing.T) *WorkerConn {
	t.Helper()
	ctx := context.Background()
	wc := NewWorkerConn(ctx, "", "", "", nil, nil, Fingerprint{})
	t.Cleanup(func() { wc.Stop() })
	return wc
}

// ── ALLOWED_ACTIONS ────────────────────────────────────────────────────────

func TestAllowedActionsContainsExpected(t *testing.T) {
	expected := []string{
		"GET_STATS",
		"READ_LOGS",
		"RESTART_CONTAINER",
		"LIST_CONTAINERS",
		"LIST_SERVICES",
		"STATUS_SERVICE",
		"RESTART_SERVICE",
		"READ_LOGS_SERVICE",
		"UPDATE_WORKER",
		"TOKEN_ROTATION",
		"DISK_SCAN",
	}
	for _, action := range expected {
		if !ALLOWED_ACTIONS[action] {
			t.Errorf("ALLOWED_ACTIONS missing expected action %q", action)
		}
	}
	if len(ALLOWED_ACTIONS) != len(expected) {
		t.Errorf("ALLOWED_ACTIONS has %d entries, expected %d", len(ALLOWED_ACTIONS), len(expected))
	}
}

// ── mustJSON ───────────────────────────────────────────────────────────────

func TestMustJSON(t *testing.T) {
	t.Run("serializes IntentResult correctly", func(t *testing.T) {
		r := IntentResult{IntentID: "i-1", Success: true, Output: "ok"}
		data := mustJSON(r)

		var got IntentResult
		if err := json.Unmarshal(data, &got); err != nil {
			t.Fatalf("unmarshal failed: %v", err)
		}
		if got.IntentID != "i-1" {
			t.Errorf("IntentID = %q, want %q", got.IntentID, "i-1")
		}
		if !got.Success {
			t.Error("Success = false, want true")
		}
		if got.Output != "ok" {
			t.Errorf("Output = %q, want %q", got.Output, "ok")
		}
	})

	t.Run("serializes Intent with omitempty params", func(t *testing.T) {
		r := Intent{IntentID: "i-2", Action: "GET_STATS"}
		data := mustJSON(r)

		var got Intent
		if err := json.Unmarshal(data, &got); err != nil {
			t.Fatalf("unmarshal failed: %v", err)
		}
		if got.IntentID != "i-2" {
			t.Errorf("IntentID = %q, want %q", got.IntentID, "i-2")
		}
		if got.Action != "GET_STATS" {
			t.Errorf("Action = %q, want %q", got.Action, "GET_STATS")
		}
		// Params is omitted when nil
		if strings.Contains(string(data), "params") {
			t.Error("params should be omitted for nil map")
		}
	})
}

// ── dispatchIntent ─────────────────────────────────────────────────────────

func TestDispatchIntent(t *testing.T) {
	wc := newTestWC(t)

	t.Run("rejects invalid JSON", func(t *testing.T) {
		raw := []byte(`{not valid json`)
		result := dispatchIntent(wc, raw)

		var got IntentResult
		if err := json.Unmarshal(result, &got); err != nil {
			t.Fatalf("result is not valid JSON: %v", err)
		}
		if got.Success {
			t.Error("Success = true, want false")
		}
		if got.Error == "" {
			t.Error("Error should not be empty for invalid JSON")
		}
	})

	t.Run("rejects action not in whitelist", func(t *testing.T) {
		intent := Intent{
			IntentID: "whitelist-test",
			Action:   "FAKE_ACTION",
		}
		raw, _ := json.Marshal(intent)
		result := dispatchIntent(wc, raw)

		var got IntentResult
		if err := json.Unmarshal(result, &got); err != nil {
			t.Fatalf("result is not valid JSON: %v", err)
		}
		if got.Success {
			t.Error("Success = true, want false for non-whitelisted action")
		}
		if got.Error == "" {
			t.Error("Error should not be empty")
		}
		if !strings.Contains(got.Error, "FAKE_ACTION") {
			t.Errorf("Error should mention the rejected action, got: %q", got.Error)
		}
	})

	t.Run("preserves intent_id in error result", func(t *testing.T) {
		intent := Intent{
			IntentID: "preserve-123",
			Action:   "NOPE_ACTION",
		}
		raw, _ := json.Marshal(intent)
		result := dispatchIntent(wc, raw)

		var got IntentResult
		if err := json.Unmarshal(result, &got); err != nil {
			t.Fatalf("result is not valid JSON: %v", err)
		}
		if got.IntentID != "preserve-123" {
			t.Errorf("IntentID = %q, want %q", got.IntentID, "preserve-123")
		}
	})

	t.Run("dispatches valid action and preserves intent_id", func(t *testing.T) {
		intent := Intent{
			IntentID: "dispatch-ok-42",
			Action:   "STATUS_SERVICE",
			Params:   map[string]interface{}{"service": "nonexistent-svc"},
		}
		raw, _ := json.Marshal(intent)
		result := dispatchIntent(wc, raw)

		var got IntentResult
		if err := json.Unmarshal(result, &got); err != nil {
			t.Fatalf("result is not valid JSON: %v", err)
		}
		if got.IntentID != "dispatch-ok-42" {
			t.Errorf("IntentID = %q, want %q", got.IntentID, "dispatch-ok-42")
		}
		// The handler ran and produced a result (success or failure doesn't matter
		// for dispatch testing — we just verify routing and intent_id preservation).
		t.Logf("STATUS_SERVICE result: success=%v output=%q error=%q", got.Success, got.Output, got.Error)
	})

	t.Run("unknown action not in whitelist returns error not default", func(t *testing.T) {
		intent := Intent{
			IntentID: "gate-test",
			Action:   "DELETE_EVERYTHING",
		}
		raw, _ := json.Marshal(intent)
		result := dispatchIntent(wc, raw)

		var got IntentResult
		if err := json.Unmarshal(result, &got); err != nil {
			t.Fatalf("result is not valid JSON: %v", err)
		}
		if got.Success {
			t.Error("Success = true, want false")
		}
		if !strings.Contains(got.Error, "not allowed") {
			t.Errorf("Error should say 'not allowed', got: %q", got.Error)
		}
	})
}

// ── Intent JSON round-trip ────────────────────────────────────────────────

func TestIntentJSONRoundTrip(t *testing.T) {
	original := Intent{
		IntentID:    "rt-1",
		Action:      "LIST_SERVICES",
		Params:      map[string]interface{}{"filter": "active"},
		RequestedBy: "admin",
	}

	data := mustJSON(original)
	var got Intent
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if got.IntentID != original.IntentID {
		t.Errorf("IntentID = %q, want %q", got.IntentID, original.IntentID)
	}
	if got.Action != original.Action {
		t.Errorf("Action = %q, want %q", got.Action, original.Action)
	}
	if got.RequestedBy != original.RequestedBy {
		t.Errorf("RequestedBy = %q, want %q", got.RequestedBy, original.RequestedBy)
	}
	if got.Params["filter"] != "active" {
		t.Errorf("Params[filter] = %v, want %q", got.Params["filter"], "active")
	}
}

func TestIntentJSONRoundTripOmitsEmptyFields(t *testing.T) {
	original := Intent{IntentID: "rt-2", Action: "GET_STATS"}

	data := mustJSON(original)
	var got Intent
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if got.Params != nil {
		t.Errorf("Params should be nil when omitted, got %v", got.Params)
	}
	if got.RequestedBy != "" {
		t.Errorf("RequestedBy should be empty when omitted, got %q", got.RequestedBy)
	}
}
