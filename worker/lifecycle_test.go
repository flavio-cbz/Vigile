package main

import (
	"context"
	"strings"
	"testing"
)

func TestCanonicalServiceName(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"ssh.service", "ssh"},
		{"SSH.SERVICE", "ssh"},
		{"ssh", "ssh"},
		{"  sshd.service  ", "sshd"},
		{"NetworkManager.service", "networkmanager"},
		{"systemd-resolved.service", "systemd-resolved"},
		{"docker.socket", "docker"},
		{"docker.target", "docker"},
		{"docker.timer", "docker"},
		{"docker.slice", "docker"},
		{"nginx.service", "nginx"},
	}

	for _, tt := range tests {
		got := canonicalServiceName(tt.input)
		if got != tt.expected {
			t.Errorf("canonicalServiceName(%q) = %q, want %q", tt.input, got, tt.expected)
		}
	}
}

func TestIsProtectedService(t *testing.T) {
	protected := []string{
		"ssh", "ssh.service", "ssh.socket", "sshd", "sshd.service",
		"docker", "docker.service", "docker.socket", "dockerd", "dockerd.service", "containerd",
		"networking", "systemd-networkd", "NetworkManager", "networkmanager.service",
		"systemd-resolved", "systemd-journald", "systemd-journald.socket", "systemd-logind", "dbus",
		"vigile", "vigile-worker", "vigile-worker.service",
	}

	for _, s := range protected {
		if !isProtectedService(s) {
			t.Errorf("expected service %q to be protected, but isProtectedService returned false", s)
		}
	}

	unprotected := []string{
		"nginx", "nginx.service", "redis", "apache2", "my-custom-app.service",
	}

	for _, s := range unprotected {
		if isProtectedService(s) {
			t.Errorf("expected service %q to NOT be protected, but isProtectedService returned true", s)
		}
	}
}

func TestHandleStopServiceRejectsProtected(t *testing.T) {
	tests := []string{"ssh", "ssh.service", "sshd", "docker", "systemd-resolved", "vigile-worker"}
	for _, s := range tests {
		intent := Intent{
			IntentID:    "test-stop-protected",
			Action:      "STOP_SERVICE",
			RequestedBy: "admin",
			Params:      map[string]interface{}{"service": s},
		}
		res := handleStopService(context.Background(), intent)
		if res.Success {
			t.Errorf("handleStopService(%q) succeeded, expected error", s)
		}
		if !strings.Contains(res.Error, "protected") {
			t.Errorf("handleStopService(%q) error = %q, expected error mentioning 'protected'", s, res.Error)
		}
	}
}

func TestHandleStopServiceRejectsInvalidName(t *testing.T) {
	invalid := []string{
		"--kill-who=all", "-s", "; rm -rf /", "ssh service", "my$ervice",
	}
	for _, s := range invalid {
		intent := Intent{
			IntentID:    "test-stop-invalid",
			Action:      "STOP_SERVICE",
			RequestedBy: "admin",
			Params:      map[string]interface{}{"service": s},
		}
		res := handleStopService(context.Background(), intent)
		if res.Success {
			t.Errorf("handleStopService(%q) succeeded, expected invalid format error", s)
		}
		if !strings.Contains(res.Error, "invalid service name format") {
			t.Errorf("handleStopService(%q) error = %q, expected 'invalid service name format'", s, res.Error)
		}
	}
}

func TestContainerIDRegex(t *testing.T) {
	valid := []string{
		"a1b2c3d4e5f6",
		"4f5e6d7c8b9a0123456789abcdef0123456789abcdef0123456789abcdef0123",
		"my-container-123",
		"container_under_score",
	}
	for _, id := range valid {
		if !containerIDRegex.MatchString(id) {
			t.Errorf("containerIDRegex should match valid ID %q", id)
		}
	}

	invalid := []string{
		"../../bin/sh",
		"container;id",
		"foo/bar",
		"id with spaces",
		"",
	}
	for _, id := range invalid {
		if containerIDRegex.MatchString(id) {
			t.Errorf("containerIDRegex should NOT match invalid ID %q", id)
		}
	}
}

func TestHandleDeleteContainerRejectsInvalidID(t *testing.T) {
	intent := Intent{
		IntentID:    "test-del-invalid",
		Action:      "DELETE_CONTAINER",
		RequestedBy: "admin",
		Params:      map[string]interface{}{"container_id": "../../etc/passwd"},
	}
	res := handleDeleteContainer(context.Background(), intent)
	if res.Success {
		t.Fatal("expected delete container with path traversal ID to fail")
	}
	if !strings.Contains(res.Error, "invalid container_id format") {
		t.Fatalf("expected error mentioning invalid container_id format, got: %q", res.Error)
	}
}

func TestHandleDeleteContainerRejectsEmptyName(t *testing.T) {
	tests := []string{"", "   ", "/"}
	for _, name := range tests {
		intent := Intent{
			IntentID:    "test-del-empty-name",
			Action:      "DELETE_CONTAINER",
			RequestedBy: "admin",
			Params: map[string]interface{}{
				"container_id":   "abc123def456",
				"container_name": name,
			},
		}
		res := handleDeleteContainer(context.Background(), intent)
		if res.Success {
			t.Fatalf("expected delete container with name %q to fail", name)
		}
		if res.Error != "container_name parameter required for delete" {
			t.Fatalf("expected 'container_name parameter required for delete', got %q", res.Error)
		}
	}
}

func TestHandleStatusServiceRejectsInvalidName(t *testing.T) {
	invalid := []string{"", "--flag", "; cat /etc/passwd", "service with spaces"}
	for _, s := range invalid {
		intent := Intent{
			IntentID:    "test-status-invalid",
			Action:      "STATUS_SERVICE",
			RequestedBy: "admin",
			Params:      map[string]interface{}{"service": s},
		}
		res := handleStatusService(context.Background(), intent)
		if res.Success {
			t.Fatalf("expected handleStatusService(%q) to fail", s)
		}
	}
}

