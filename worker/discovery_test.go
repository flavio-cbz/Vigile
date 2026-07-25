package main

import (
	"regexp"
	"runtime"
	"testing"
)

func TestDiscoveryCollectFingerprintReturnsAllFields(t *testing.T) {
	origVersion := Version
	defer func() { Version = origVersion }()

	fp := collectFingerprint()

	if fp.Hostname == "" {
		t.Fatal("collectFingerprint: Hostname is empty")
	}
	if fp.MachineID == "" {
		t.Fatal("collectFingerprint: MachineID is empty")
	}
	if fp.Arch != runtime.GOARCH {
		t.Fatalf("collectFingerprint: Arch = %q, want %q", fp.Arch, runtime.GOARCH)
	}
	if fp.OS != runtime.GOOS {
		t.Fatalf("collectFingerprint: OS = %q, want %q", fp.OS, runtime.GOOS)
	}
	if fp.Version != Version {
		t.Fatalf("collectFingerprint: Version = %q, want %q", fp.Version, Version)
	}
}

func TestDiscoveryGetHostnameReturnsNonEmpty(t *testing.T) {
	h := getHostname()
	if h == "" {
		t.Fatal("getHostname returned empty string")
	}
}

func TestDiscoveryGetMachineIDReturnsValidHex(t *testing.T) {
	id := getMachineID()

	if len(id) != 64 {
		t.Fatalf("getMachineID: len = %d, want 64", len(id))
	}
	hexPattern := regexp.MustCompile(`^[0-9a-f]{64}$`)
	if !hexPattern.MatchString(id) {
		t.Fatalf("getMachineID: not a valid 64-char hex string, got %q", id)
	}
}

func TestDiscoveryGetMachineIDDeterministic(t *testing.T) {
	// getMachineID must return the same value on repeated calls
	// (no random component, no time dependency).
	first := getMachineID()
	second := getMachineID()
	if first != second {
		t.Fatalf("getMachineID not deterministic: first=%q, second=%q", first, second)
	}
}

func TestDiscoveryVersionGlobalIsNonEmpty(t *testing.T) {
	if Version == "" {
		t.Fatal("Version global is empty")
	}
}
