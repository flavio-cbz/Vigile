package main

import (
	"context"
	"testing"
)

func TestHandleRestartContainerRejectsEmptyRequestedBy(t *testing.T) {
	intent := Intent{
		IntentID:    "test-001",
		Action:      "RESTART_CONTAINER",
		RequestedBy: "",
		Params:      map[string]interface{}{"container_id": "abc123"},
	}
	result := handleRestartContainer(context.Background(), intent)
	if result.Success {
		t.Fatal("expected restart to be rejected when requested_by is empty")
	}
	if result.Error != "missing requested_by context" {
		t.Fatalf("unexpected error message: %q", result.Error)
	}
}

func TestHandleRestartContainerAllowsWithRequestedBy(t *testing.T) {
	intent := Intent{
		IntentID:    "test-002",
		Action:      "RESTART_CONTAINER",
		RequestedBy: "admin",
		Params:      map[string]interface{}{"container_id": "abc123"},
	}
	result := handleRestartContainer(context.Background(), intent)
	if result.Error == "missing requested_by context" {
		t.Fatal("expected restart to proceed when requested_by is set")
	}
}
