package main

import (
	"context"
	"strings"
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

func TestParseServicesOutputWithAllAndBullet(t *testing.T) {
	out := "ssh.service                loaded active running OpenSSH Daemon\n" +
		"● nginx.service              loaded failed failed  A high performance web server\n" +
		"docker.service             loaded active running Docker Application Container Engine\n" +
		"not-a-service              loaded active running bogus\n" +
		"my-app@1.service           loaded active running My App Instance\n"
	svcs := parseServicesOutput(out)
	if len(svcs) != 4 {
		t.Fatalf("expected 4 services, got %d: %+v", len(svcs), svcs)
	}
	// First entry
	if svcs[0].Name != "ssh.service" || svcs[0].State != "active" || svcs[0].Status != "running" {
		t.Fatalf("unexpected first service: %+v", svcs[0])
	}
	// Bullet entry (●)
	if svcs[1].Name != "nginx.service" || svcs[1].State != "failed" || svcs[1].Status != "failed" {
		t.Fatalf("unexpected bullet service: %+v", svcs[1])
	}
	// Invalid name filtered
	for _, s := range svcs {
		if s.Name == "not-a-service" {
			t.Fatalf("should have filtered invalid service name not-a-service")
		}
	}
	// @ instance
	found := false
	for _, s := range svcs {
		if s.Name == "my-app@1.service" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected my-app@1.service to be parsed")
	}
}

func TestParseServicesOutputLimit500(t *testing.T) {
	var sb strings.Builder
	for i := 0; i < 600; i++ {
		sb.WriteString("svc" + strings.Repeat("a", 5) + ".service loaded active running Test\n")
	}
	// Actually need unique names that match regex: use svc000.service etc
	sb.Reset()
	for i := 0; i < 600; i++ {
		sb.WriteString("svc-" + strings.ReplaceAll(strings.Repeat("x", 3), "x", "a") + ".service loaded active running Test\n")
	}
	// Simpler: generate 600 lines with incremental index in name (allowed chars)
	sb.Reset()
	for i := 0; i < 600; i++ {
		sb.WriteString("a.service loaded active running Test\n")
	}
	svcs := parseServicesOutput(sb.String())
	if len(svcs) != 500 {
		t.Fatalf("expected 500 capped services, got %d", len(svcs))
	}
}

func TestServiceNameRegex(t *testing.T) {
	cases := map[string]bool{
		"ssh.service":         true,
		"my-app@1.service":    true,
		"a_b.service":         true,
		"a.service":           true,
		"not-a-service":       false,
		"evil.service; rm":    false,
		"foo.socket":          false,
		"":                    false,
	}
	for name, want := range cases {
		got := serviceNameRegex.MatchString(name)
		if got != want {
			t.Fatalf("regex for %q: got %v want %v", name, got, want)
		}
	}
}
