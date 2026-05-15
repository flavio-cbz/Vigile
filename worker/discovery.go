package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"runtime"
)

// Fingerprint contains immutable node identity information.
type Fingerprint struct {
	Hostname  string `json:"hostname"`
	MachineID string `json:"machine_id"`
	Arch      string `json:"arch"`
	OS        string `json:"os"`
}

// collectFingerprint gathers the node's identity from the environment.
func collectFingerprint() Fingerprint {
	return Fingerprint{
		Hostname:  getHostname(),
		MachineID: getMachineID(),
		Arch:      runtime.GOARCH,
		OS:        runtime.GOOS,
	}
}

func getHostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "unknown"
	}
	return h
}

func getMachineID() string {
	// Linux: /etc/machine-id, /var/lib/dbus/machine-id
	// macOS: IOPlatformUUID (not easily accessible from Go stdlib)
	// Fallback: sha256 of hostname
	paths := []string{"/etc/machine-id", "/var/lib/dbus/machine-id"}
	for _, p := range paths {
		data, err := os.ReadFile(p)
		if err == nil && len(data) >= 32 {
			return fmt.Sprintf("%x", sha256.Sum256(data[:32]))
		}
	}
	// Fallback: hash of hostname
	h := getHostname()
	return fmt.Sprintf("%x", sha256.Sum256([]byte(h)))
}
