package main

import (
	"context"
	"testing"
)

func TestHandleRestartServiceSkipsRequestedByCheck(t *testing.T) {
	intent := Intent{
		IntentID:    "test-001",
		Action:      "RESTART_SERVICE",
		RequestedBy: "",
		Params:      map[string]interface{}{"service": "ssh"},
	}
	result := handleRestartService(context.Background(), intent)
	// The function no longer rejects empty requested_by.
	// It proceeds to the systemctl call, which fails with a different error
	// (no systemd) in the test environment.
	if result.Error == "missing requested_by context" {
		t.Fatal("expected handler to not reject empty requested_by")
	}
}

func TestHandleRestartServiceProceedsWithRequestedBy(t *testing.T) {
	intent := Intent{
		IntentID:    "test-002",
		Action:      "RESTART_SERVICE",
		RequestedBy: "admin",
		Params:      map[string]interface{}{"service": "ssh"},
	}
	result := handleRestartService(context.Background(), intent)
	if result.Error == "missing requested_by context" {
		t.Fatal("expected restart to proceed when requested_by is set")
	}
}
