package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os/exec"
	"strings"
)

// handleListServices lists all systemd services.
func handleListServices(ctx context.Context, intent Intent) IntentResult {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "list-units", "--type=service", "--no-pager", "--no-legend")
	out, err := cmd.Output()
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl timed out"}
	}
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

	outJSON, err := json.Marshal(services)
	if err != nil {
		logger.Printf("services: marshal list: %v", err)
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal error: %v", err)}
	}
	return IntentResult{Success: true, Output: string(outJSON)}
}

// handleStatusService gets the status of a specific systemd service.
func handleStatusService(ctx context.Context, intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}

	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "is-active", service)
	active, err := cmd.Output()
	if err != nil {
		logger.Printf("services: systemctl is-active %s: %v", service, err)
	}
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl is-active timed out"}
	}

	cmd2 := exec.CommandContext(cmdCtx, "systemctl", "is-enabled", service)
	enabled, err := cmd2.Output()
	if err != nil {
		logger.Printf("services: systemctl is-enabled %s: %v", service, err)
	}
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl is-enabled timed out"}
	}

	result := map[string]string{
		"service": service,
		"active":  strings.TrimSpace(string(active)),
		"enabled": strings.TrimSpace(string(enabled)),
	}
	out, err := json.Marshal(result)
	if err != nil {
		logger.Printf("services: marshal status: %v", err)
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal error: %v", err)}
	}
	return IntentResult{Success: true, Output: string(out)}
}

// handleRestartService restarts a systemd service.
func handleRestartService(ctx context.Context, intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	approvalID := getParamString(intent.Params, "approval_id", "")
	log.Printf("executing action action=RESTART_SERVICE service=%s node_id=%s requested_by=%q approval_id=%s intent_id=%s",
		service, nodeID, intent.RequestedBy, approvalID, intent.IntentID)

	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "restart", service)
	output, err := cmd.CombinedOutput()
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl restart timed out"}
	}
	if err != nil {
		return IntentResult{
			Success: false,
			Error:   fmt.Sprintf("restart failed: %v: %s", err, strings.TrimSpace(string(output))),
		}
	}
	return IntentResult{Success: true, Output: fmt.Sprintf("Service %s restarted", service)}
}
