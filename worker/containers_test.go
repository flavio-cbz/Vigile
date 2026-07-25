package main

import (
	"context"
	"testing"
)

func TestHandleRestartContainerSkipsRequestedByCheck(t *testing.T) {
	intent := Intent{
		IntentID:    "test-001",
		Action:      "RESTART_CONTAINER",
		RequestedBy: "",
		Params:      map[string]interface{}{"container_id": "abc123"},
	}
	result := handleRestartContainer(context.Background(), intent)
	// The function no longer rejects empty requested_by.
	// It proceeds to the Docker API call, which fails with a different error
	// (Docker socket not found) in the test environment.
	if result.Error == "missing requested_by context" {
		t.Fatal("expected handler to not reject empty requested_by")
	}
}

func TestHandleRestartContainerProceedsWithRequestedBy(t *testing.T) {
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
