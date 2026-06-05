package main

import (
	"testing"
)

func TestHandleRestartServiceRejectsEmptyRequestedBy(t *testing.T) {
	intent := Intent{
		IntentID:    "test-001",
		Action:      "RESTART_SERVICE",
		RequestedBy: "",
		Params:      map[string]interface{}{"service": "ssh"},
	}
	result := handleRestartService(intent)
	if result.Success {
		t.Fatal("expected restart to be rejected when requested_by is empty")
	}
	if result.Error != "missing requested_by context" {
		t.Fatalf("unexpected error message: %q", result.Error)
	}
}

func TestHandleRestartServiceAllowsWithRequestedBy(t *testing.T) {
	intent := Intent{
		IntentID:    "test-002",
		Action:      "RESTART_SERVICE",
		RequestedBy: "admin",
		Params:      map[string]interface{}{"service": "ssh"},
	}
	result := handleRestartService(intent)
	if result.Error == "missing requested_by context" {
		t.Fatal("expected restart to proceed when requested_by is set")
	}
}
