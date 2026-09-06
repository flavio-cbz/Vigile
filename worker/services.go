package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os/exec"
	"regexp"
	"strings"
)

var serviceNameRegex = regexp.MustCompile(`^[a-zA-Z0-9@._-]+\.service$`)
var serviceTargetRegex = regexp.MustCompile(`^[a-zA-Z0-9@._-]+$`)

var protectedServices = map[string]bool{
	"ssh":              true,
	"sshd":             true,
	"docker":           true,
	"dockerd":          true,
	"containerd":       true,
	"networking":       true,
	"systemd-networkd": true,
	"networkmanager":   true,
	"systemd-resolved": true,
	"systemd-journald": true,
	"systemd-logind":   true,
	"dbus":             true,
	"vigile":           true,
	"vigile-worker":    true,
}

var unitExtensions = []string{".service", ".socket", ".target", ".timer", ".slice"}

func canonicalServiceName(service string) string {
	clean := strings.ToLower(strings.TrimSpace(service))
	for _, ext := range unitExtensions {
		if strings.HasSuffix(clean, ext) {
			clean = strings.TrimSuffix(clean, ext)
			break
		}
	}
	return clean
}

func isProtectedService(service string) bool {
	canonical := canonicalServiceName(service)
	return protectedServices[canonical]
}

type serviceInfo struct {
	Name   string `json:"name"`
	State  string `json:"state"`
	Status string `json:"status"`
}

func parseServicesOutput(out string) []serviceInfo {
	var services []serviceInfo
	for _, line := range strings.Split(out, "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) == 0 {
			continue
		}
		offset := 0
		if fields[0] == "●" {
			if len(fields) < 5 {
				continue
			}
			offset = 1
		} else if len(fields) < 4 {
			continue
		}
		name := fields[0+offset]
		if !serviceNameRegex.MatchString(name) {
			continue
		}
		active := fields[2+offset]
		sub := fields[3+offset]
		services = append(services, serviceInfo{Name: name, State: active, Status: sub})
		if len(services) >= 500 {
			break
		}
	}
	if services == nil {
		services = []serviceInfo{}
	}
	return services
}

// handleListServices lists all systemd services.
func handleListServices(ctx context.Context, intent Intent) IntentResult {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend", "--plain")
	out, err := cmd.Output()
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl timed out"}
	}
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("systemctl failed: %v", err)}
	}

	services := parseServicesOutput(string(out))

	outJSON, err := json.Marshal(services)
	if err != nil {
		slog.Warn("services: marshal list", "error", err)
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
	if strings.HasPrefix(service, "-") || !serviceTargetRegex.MatchString(service) {
		return IntentResult{Success: false, Error: fmt.Sprintf("invalid service name format: %q", service)}
	}

	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "is-active", "--", service)
	active, err := cmd.Output()
	if err != nil {
		slog.Debug("services: systemctl is-active", "service", service, "error", err)
	}
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl is-active timed out"}
	}

	cmd2 := exec.CommandContext(cmdCtx, "systemctl", "is-enabled", "--", service)
	enabled, err := cmd2.Output()
	if err != nil {
		slog.Debug("services: systemctl is-enabled", "service", service, "error", err)
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
		slog.Warn("services: marshal status", "error", err)
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal error: %v", err)}
	}
	return IntentResult{Success: true, Output: string(out)}
}

// handleRestartService restarts a systemd service.
func handleRestartService(ctx context.Context, intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	approvalID := getParamString(intent.Params, "approval_id", "")
	slog.Info("executing action",
		"action", "RESTART_SERVICE",
		"service", service,
		"node_id", nodeID,
		"requested_by", intent.RequestedBy,
		"approval_id", approvalID,
		"intent_id", intent.IntentID)

	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}
	if strings.HasPrefix(service, "-") || !serviceTargetRegex.MatchString(service) {
		return IntentResult{Success: false, Error: fmt.Sprintf("invalid service name format: %q", service)}
	}

	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "restart", "--", service)
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

// handleStopService stops a systemd service (rejects protected services).
func handleStopService(ctx context.Context, intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	approvalID := getParamString(intent.Params, "approval_id", "")
	slog.Info("executing action",
		"action", "STOP_SERVICE",
		"service", service,
		"node_id", nodeID,
		"requested_by", intent.RequestedBy,
		"approval_id", approvalID,
		"intent_id", intent.IntentID)

	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}
	if strings.HasPrefix(service, "-") || !serviceTargetRegex.MatchString(service) {
		return IntentResult{Success: false, Error: fmt.Sprintf("invalid service name format: %q", service)}
	}

	if isProtectedService(service) {
		return IntentResult{Success: false, Error: fmt.Sprintf("service %q is protected and cannot be stopped", service)}
	}

	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "stop", "--", service)
	output, err := cmd.CombinedOutput()
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl stop timed out"}
	}
	if err != nil {
		return IntentResult{
			Success: false,
			Error:   fmt.Sprintf("stop failed: %v: %s", err, strings.TrimSpace(string(output))),
		}
	}
	return IntentResult{Success: true, Output: fmt.Sprintf("Service %s stopped", service)}
}

// handleStartService starts a systemd service.
func handleStartService(ctx context.Context, intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	approvalID := getParamString(intent.Params, "approval_id", "")
	slog.Info("executing action",
		"action", "START_SERVICE",
		"service", service,
		"node_id", nodeID,
		"requested_by", intent.RequestedBy,
		"approval_id", approvalID,
		"intent_id", intent.IntentID)

	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}
	if strings.HasPrefix(service, "-") || !serviceTargetRegex.MatchString(service) {
		return IntentResult{Success: false, Error: fmt.Sprintf("invalid service name format: %q", service)}
	}

	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "systemctl", "start", "--", service)
	output, err := cmd.CombinedOutput()
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "systemctl start timed out"}
	}
	if err != nil {
		return IntentResult{
			Success: false,
			Error:   fmt.Sprintf("start failed: %v: %s", err, strings.TrimSpace(string(output))),
		}
	}
	return IntentResult{Success: true, Output: fmt.Sprintf("Service %s started", service)}
}
