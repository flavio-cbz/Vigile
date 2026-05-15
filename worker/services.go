package main

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
)

// handleListServices lists all systemd services.
func handleListServices(intent Intent) IntentResult {
	cmd := exec.Command("systemctl", "list-units", "--type=service", "--no-pager", "--no-legend")
	out, err := cmd.Output()
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("systemctl failed: %v", err)}
	}

	type serviceInfo struct {
		Name   string `json:"name"`
		State  string `json:"state"`
		Status string `json:"status"`
	}
	var services []serviceInfo
	for _, line := range strings.Split(string(out), "\n") {
		fields := strings.Fields(line)
		if len(fields) < 4 {
			continue
		}
		// systemctl output: UNIT LOAD ACTIVE SUB DESCRIPTION
		// e.g. "ssh.service loaded active running OpenSSH Daemon"
		name := fields[0]
		active := fields[2] // active, inactive, etc.
		sub := fields[3]    // running, exited, dead, etc.
		services = append(services, serviceInfo{Name: name, State: active, Status: sub})
	}
	if services == nil {
		services = []serviceInfo{} // Return [] not null
	}

	outJSON, _ := json.Marshal(services)
	return IntentResult{Success: true, Output: string(outJSON)}
}

// handleStatusService gets the status of a specific systemd service.
func handleStatusService(intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}

	cmd := exec.Command("systemctl", "is-active", service)
	active, _ := cmd.Output()

	cmd2 := exec.Command("systemctl", "is-enabled", service)
	enabled, _ := cmd2.Output()

	result := map[string]string{
		"service": service,
		"active":  strings.TrimSpace(string(active)),
		"enabled": strings.TrimSpace(string(enabled)),
	}
	out, _ := json.Marshal(result)
	return IntentResult{Success: true, Output: string(out)}
}

// handleRestartService restarts a systemd service.
func handleRestartService(intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}

	cmd := exec.Command("systemctl", "restart", service)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return IntentResult{
			Success: false,
			Error:   fmt.Sprintf("restart failed: %v: %s", err, strings.TrimSpace(string(output))),
		}
	}
	return IntentResult{Success: true, Output: fmt.Sprintf("Service %s restarted", service)}
}
