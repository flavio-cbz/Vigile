package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const (
	// commandTimeout is the maximum duration for any external command execution.
	commandTimeout = 30 * time.Second
	// maxLogReadSize is the maximum file size (in bytes) allowed for log reading.
	maxLogReadSize = 10 * 1024 * 1024
)

// handleReadLogs handles the READ_LOGS intent.
func handleReadLogs(ctx context.Context, intent Intent) IntentResult {
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

func handleReadLogsService(ctx context.Context, intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	lines := getParamInt(intent.Params, "lines", 50)

	if service == "" {
		return IntentResult{Success: false, Error: "service parameter required"}
	}

	// Use journalctl for systemd services
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "journalctl", "-u", service, "--no-pager", "-n", fmt.Sprintf("%d", lines), "--output", "short")
	out, err := cmd.Output()
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "journalctl timed out"}
	}
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("journalctl failed: %v", err)}
	}

	return IntentResult{Success: true, Output: strings.TrimSpace(string(out))}
}

func readLogFile(path string, lines int) IntentResult {
	info, err := os.Stat(path)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("stat failed: %v", err)}
	}
	if info.Size() > maxLogReadSize {
		return IntentResult{Success: false, Error: fmt.Sprintf("log file too large: %d bytes", info.Size())}
	}

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
	// 1. Clean relative segments
	cleanPath := filepath.Clean(path)

	// 2. Resolve to absolute path
	absPath, err := filepath.Abs(cleanPath)
	if err != nil {
		return false
	}

	// 3. Resolve symlinks to prevent symlink traversal bypass
	if realPath, err := filepath.EvalSymlinks(absPath); err == nil {
		absPath = realPath
	}

	for _, prefix := range allowedLogPrefixes {
		// Clean and resolve the allowed prefix
		cleanPrefix := filepath.Clean(prefix)
		absPrefix, err := filepath.Abs(cleanPrefix)
		if err != nil {
			continue
		}

		// 3. Validate hierarchy: resolved path must start with the prefix
		if strings.HasPrefix(absPath, absPrefix) {
			// Prevent character addition vulnerabilities (e.g. /var/log_backup)
			if len(absPath) == len(absPrefix) || absPath[len(absPrefix)] == filepath.Separator {
				return true
			}
		}
	}
	return false
}
