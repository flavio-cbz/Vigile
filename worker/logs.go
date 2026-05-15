package main

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// handleReadLogs handles the READ_LOGS intent.
func handleReadLogs(intent Intent) IntentResult {
	path := getParamString(intent.Params, "path", "")
	lines := getParamInt(intent.Params, "lines", 50)

	if path == "" {
		return IntentResult{Success: false, Error: "path parameter required"}
	}

	// Security: only allow reading from configured log directories
	if !isAllowedLogPath(path) {
		return IntentResult{Success: false, Error: fmt.Sprintf("path %q not allowed", path)}
	}

	return readLogFile(path, lines)
}

func handleReadLogsService(intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	lines := getParamInt(intent.Params, "lines", 50)

	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}

	// Use journalctl for systemd services
	cmd := exec.Command("journalctl", "-u", service, "--no-pager", "-n", fmt.Sprintf("%d", lines), "--output", "short")
	out, err := cmd.Output()
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("journalctl failed: %v", err)}
	}

	return IntentResult{Success: true, Output: strings.TrimSpace(string(out))}
}

func readLogFile(path string, lines int) IntentResult {
	data, err := os.ReadFile(path)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("read failed: %v", err)}
	}

	allLines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(allLines) > lines {
		allLines = allLines[len(allLines)-lines:]
	}
	return IntentResult{Success: true, Output: strings.Join(allLines, "\n")}
}

var allowedLogPrefixes = []string{
	"/var/log/",
	"/var/log/journal/",
}

func isAllowedLogPath(path string) bool {
	for _, prefix := range allowedLogPrefixes {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}
