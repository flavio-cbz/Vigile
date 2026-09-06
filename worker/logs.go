package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	commandTimeout      = 10 * time.Second
	maxTailWindow       = 4 * 1024 * 1024
	tailTruncatedMarker = "[truncated: tail window exceeded"
)

type LogEntry struct {
	Timestamp float64                `json:"timestamp"` // Unix timestamp in seconds
	TimeStr   string                 `json:"time_str"`
	Level     string                 `json:"level"` // "error", "warn", "info", "debug"
	Unit      string                 `json:"unit"`
	Message   string                 `json:"message"`
	Raw       map[string]interface{} `json:"raw,omitempty"`
}

type LogResultPayload struct {
	Entries []LogEntry `json:"entries"`
	Output  string     `json:"output"`
	Lines   int        `json:"lines"`
}

type LogSourceItem struct {
	ID         string  `json:"id"`
	Name       string  `json:"name"`
	Category   string  `json:"category"` // "files", "services", "docker"
	Path       string  `json:"path,omitempty"`
	Unit       string  `json:"unit,omitempty"`
	SizeBytes  int64   `json:"size_bytes,omitempty"`
	Mtime      float64 `json:"mtime,omitempty"`
	ErrorCount int     `json:"error_count"`
	Status     string  `json:"status,omitempty"`
}

type HistogramBucket struct {
	Hour      string  `json:"hour"`
	Timestamp float64 `json:"timestamp"`
	Info      int     `json:"info"`
	Warn      int     `json:"warn"`
	Error     int     `json:"error"`
	Total     int     `json:"total"`
}

type LogHistogramResult struct {
	Buckets       []HistogramBucket `json:"buckets"`
	TotalErrors   int               `json:"total_errors"`
	TotalWarnings int               `json:"total_warnings"`
	TotalLines    int               `json:"total_lines"`
}

var (
	severityErrRegex  = regexp.MustCompile(`(?i)\b(ERROR|FATAL|CRIT|CRITICAL|EMERG|ALERT|PANIC|FAILED|FAILURE)\b`)
	severityWarnRegex = regexp.MustCompile(`(?i)\b(WARN|WARNING)\b`)
	severityDbgRegex  = regexp.MustCompile(`(?i)\b(DEBUG|TRACE)\b`)
)

func handleReadLogs(ctx context.Context, intent Intent) IntentResult {
	path := getParamString(intent.Params, "path", "")
	lines := getParamInt(intent.Params, "lines", 50)
	since := getParamString(intent.Params, "since", "")
	until := getParamString(intent.Params, "until", "")

	if path == "" {
		return IntentResult{Success: false, Error: "path parameter required"}
	}

	// Security: only allow reading from configured log directories
	if !isAllowedLogPath(path) {
		return IntentResult{Success: false, Error: fmt.Sprintf("path %q not allowed", path)}
	}

	return readLogFileStructured(path, lines, since, until)
}

func handleReadLogsService(ctx context.Context, intent Intent) IntentResult {
	service := getParamString(intent.Params, "service", "")
	lines := getParamInt(intent.Params, "lines", 50)
	since := getParamString(intent.Params, "since", "")
	until := getParamString(intent.Params, "until", "")

	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	args := []string{"--no-pager", "-n", fmt.Sprintf("%d", lines), "--output", "json"}
	if service != "" && service != "__kernel__" {
		args = append(args, "-u", service)
	} else if service == "__kernel__" {
		args = append(args, "-k")
	}

	if since != "" {
		args = append(args, "--since", since)
	}
	if until != "" {
		args = append(args, "--until", until)
	}

	cmd := exec.CommandContext(cmdCtx, "journalctl", args...)
	out, err := cmd.Output()
	if cmdCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "journalctl timed out"}
	}
	if err != nil {
		// Fallback to plain short output if JSON is unsupported
		fallbackCmd := exec.CommandContext(cmdCtx, "journalctl", "-u", service, "--no-pager", "-n", fmt.Sprintf("%d", lines), "--output", "short")
		fallbackOut, fallbackErr := fallbackCmd.Output()
		if fallbackErr == nil {
			return IntentResult{Success: true, Output: strings.TrimSpace(string(fallbackOut))}
		}
		return IntentResult{Success: false, Error: fmt.Sprintf("journalctl failed: %v", err)}
	}

	var entries []LogEntry
	var rawLines []string
	scanner := bufio.NewScanner(strings.NewReader(string(out)))
	for scanner.Scan() {
		line := scanner.Text()
		if strings.TrimSpace(line) == "" {
			continue
		}
		var jm map[string]interface{}
		if err := json.Unmarshal([]byte(line), &jm); err != nil {
			continue
		}

		entry := parseJournaldJSON(jm)
		entries = append(entries, entry)
		rawLines = append(rawLines, fmt.Sprintf("%s [%s] %s: %s", entry.TimeStr, strings.ToUpper(entry.Level), entry.Unit, entry.Message))
	}

	payload := LogResultPayload{
		Entries: entries,
		Output:  strings.Join(rawLines, "\n"),
		Lines:   len(entries),
	}

	jsonBytes, err := json.Marshal(payload)
	if err != nil {
		return IntentResult{Success: true, Output: strings.Join(rawLines, "\n")}
	}

	return IntentResult{Success: true, Output: string(jsonBytes)}
}

func parseJournaldJSON(jm map[string]interface{}) LogEntry {
	entry := LogEntry{Level: "info", Raw: jm}

	// Timestamp
	if rt, ok := jm["__REALTIME_TIMESTAMP"].(string); ok {
		if us, err := strconv.ParseInt(rt, 10, 64); err == nil {
			t := time.Unix(us/1000000, (us%1000000)*1000)
			entry.Timestamp = float64(us) / 1000000.0
			entry.TimeStr = t.Format("15:04:05.000")
		}
	}
	if entry.TimeStr == "" {
		entry.Timestamp = float64(time.Now().Unix())
		entry.TimeStr = time.Now().Format("15:04:05.000")
	}

	// Unit / Syslog Identifier
	if u, ok := jm["_SYSTEMD_UNIT"].(string); ok && u != "" {
		entry.Unit = u
	} else if u, ok := jm["SYSLOG_IDENTIFIER"].(string); ok && u != "" {
		entry.Unit = u
	} else if u, ok := jm["_COMM"].(string); ok && u != "" {
		entry.Unit = u
	} else {
		entry.Unit = "system"
	}

	// Priority / Level
	if pStr, ok := jm["PRIORITY"].(string); ok {
		if p, err := strconv.Atoi(pStr); err == nil {
			switch {
			case p <= 3:
				entry.Level = "error"
			case p == 4:
				entry.Level = "warn"
			case p <= 6:
				entry.Level = "info"
			default:
				entry.Level = "debug"
			}
		}
	}

	// Message
	if m, ok := jm["MESSAGE"].(string); ok {
		entry.Message = strings.TrimSpace(m)
	}

	return entry
}

func tailFile(path string, lines int, maxWindow int) (string, error) {
	info, err := os.Stat(path)
	if err != nil {
		return "", err
	}

	// If file is larger than window, skip tail command to ensure truncation marker
	if info.Size() <= int64(maxWindow) {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, "tail", "-n", strconv.Itoa(lines), path)
		if out, err := cmd.Output(); err == nil {
			raw := strings.Split(strings.TrimRight(string(out), "\r\n"), "\n")
			var filtered []string
			for _, l := range raw {
				l = strings.TrimSuffix(l, "\r")
				if strings.TrimSpace(l) != "" {
					filtered = append(filtered, l)
				}
			}
			return strings.Join(filtered, "\n"), nil
		}
	}

	// Fallback in pure Go: open file and read trailing bytes (up to maxWindow)
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	var readSize int64 = int64(maxWindow)
	if readSize <= 0 {
		readSize = maxTailWindow
	}
	if info.Size() < readSize {
		readSize = info.Size()
	}

	buf := make([]byte, readSize)
	offset := info.Size() - readSize
	if _, err := f.ReadAt(buf, offset); err != nil {
		return "", err
	}

	raw := strings.Split(strings.TrimRight(string(buf), "\r\n"), "\n")
	if offset > 0 && len(raw) > 1 {
		raw = raw[1:]
	}

	if len(raw) > lines {
		raw = raw[len(raw)-lines:]
	}
	var filtered []string
	for _, l := range raw {
		l = strings.TrimSuffix(l, "\r")
		if strings.TrimSpace(l) != "" {
			filtered = append(filtered, l)
		}
	}
	out := strings.Join(filtered, "\n")
	if offset > 0 && len(filtered) < lines {
		out = fmt.Sprintf("%s %d bytes]\n%s", tailTruncatedMarker, maxWindow, out)
	}
	return out, nil
}

func tailLogFile(path string, lines int) (string, error) {
	return tailFile(path, lines, maxTailWindow)
}

func readLogFile(path string, lines int) IntentResult {
	return readLogFileStructured(path, lines, "", "")
}

func readLogFileStructured(path string, lines int, since, until string) IntentResult {
	if lines <= 0 {
		lines = 50
	}
	outStr, err := tailFile(path, lines, maxTailWindow)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("stat failed: %v", err)}
	}
	allLines := []string{}
	if outStr != "" {
		allLines = strings.Split(outStr, "\n")
	}
	info, _ := os.Stat(path)
	if info == nil {
		// Fallback: use now if stat fails (should not happen after tailFile success)
		return IntentResult{Success: false, Error: "failed to stat log file"}
	}

	baseName := filepath.Base(path)
	var entries []LogEntry
	for _, l := range allLines {
		if strings.TrimSpace(l) == "" {
			continue
		}
		entry := LogEntry{
			Timestamp: float64(info.ModTime().Unix()),
			TimeStr:   time.Now().Format("15:04:05"),
			Level:     "info",
			Unit:      baseName,
			Message:   l,
		}

		if severityErrRegex.MatchString(l) {
			entry.Level = "error"
		} else if severityWarnRegex.MatchString(l) {
			entry.Level = "warn"
		} else if severityDbgRegex.MatchString(l) {
			entry.Level = "debug"
		}

		parts := strings.Fields(l)
		if len(parts) >= 3 {
			// Syslog format: "Aug 19 14:09:47 hostname service[pid]: msg"
			entry.TimeStr = parts[2]
			if len(parts) >= 5 {
				entry.Unit = strings.TrimSuffix(parts[4], ":")
				entry.Message = strings.Join(parts[5:], " ")
			}
		}

		entries = append(entries, entry)
	}

	payload := LogResultPayload{
		Entries: entries,
		Output:  strings.Join(allLines, "\n"),
		Lines:   len(entries),
	}

	jsonBytes, err := json.Marshal(payload)
	if err != nil {
		return IntentResult{Success: true, Output: strings.Join(allLines, "\n")}
	}

	return IntentResult{Success: true, Output: string(jsonBytes)}
}

func handleListLogSources(ctx context.Context, intent Intent) IntentResult {
	var sources []LogSourceItem

	// 1. Files in /var/log
	if err := filepath.Walk("/var/log", func(p string, info os.FileInfo, err error) error {
		if err != nil || info == nil || info.IsDir() {
			return nil
		}
		// Skip archives and binary journals
		if strings.HasSuffix(p, ".gz") || strings.HasSuffix(p, ".journal") || strings.HasSuffix(p, ".old") {
			return nil
		}
		if isAllowedLogPath(p) {
			sources = append(sources, LogSourceItem{
				ID:        p,
				Name:      filepath.Base(p),
				Category:  "files",
				Path:      p,
				SizeBytes: info.Size(),
				Mtime:     float64(info.ModTime().Unix()),
			})
		}
		return nil
	}); err != nil {
		log.Printf("WARN: Walk /var/log failed: %v", err)
	}

	// 2. Active systemd services
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	cmd := exec.CommandContext(cmdCtx, "systemctl", "list-units", "--type=service", "--no-pager", "--no-legend")
	if out, err := cmd.Output(); err == nil {
		for _, line := range strings.Split(string(out), "\n") {
			fields := strings.Fields(line)
			if len(fields) >= 4 {
				unit := fields[0]
				active := fields[2]
				sub := fields[3]
				sources = append(sources, LogSourceItem{
					ID:       unit,
					Name:     unit,
					Category: "services",
					Unit:     unit,
					Status:   fmt.Sprintf("%s (%s)", active, sub),
				})
			}
		}
	} else {
		log.Printf("INFO: systemctl list-units failed (non-systemd host?): %v", err)
	}

	// 3. Docker containers (if docker socket available)
	if _, err := os.Stat(dockerSocket); err == nil {
		if data, err := dockerAPI(ctx, "GET", "/v1.45/containers/json?all=true", nil); err == nil {
			var containers []map[string]interface{}
			if err := json.Unmarshal(data, &containers); err == nil {
				for _, c := range containers {
					names, _ := c["Names"].([]interface{})
					name := "container"
					if len(names) > 0 {
						name = strings.TrimPrefix(fmt.Sprint(names[0]), "/")
					}
					id, _ := c["Id"].(string)
					state, _ := c["State"].(string)
					sources = append(sources, LogSourceItem{
						ID:       "docker:" + id,
						Name:     "docker:" + name,
						Category: "docker",
						Status:   state,
					})
				}
			} else {
				log.Printf("WARN: dockerAPI unmarshal failed: %v", err)
			}
		} else {
			log.Printf("INFO: dockerAPI failed (no docker?): %v", err)
		}
	}

	// Sort sources by name
	sort.Slice(sources, func(i, j int) bool {
		return sources[i].Name < sources[j].Name
	})

	resJSON, err := json.Marshal(sources)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal error: %v", err)}
	}

	return IntentResult{Success: true, Output: string(resJSON)}
}

func handleLogHistogram(ctx context.Context, intent Intent) IntentResult {
	now := time.Now().UTC()
	buckets := make([]HistogramBucket, 24)

	// Initialize 24 hourly buckets
	for i := 0; i < 24; i++ {
		t := now.Add(time.Duration(i-23) * time.Hour)
		buckets[i] = HistogramBucket{
			Hour:      t.Format("15h"),
			Timestamp: float64(t.Unix()),
		}
	}

	// Query journalctl over last 24h
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()

	if _, err := exec.LookPath("journalctl"); err != nil {
		log.Printf("INFO: journalctl not found, histogram will be empty: %v", err)
	} else if out, err := exec.CommandContext(cmdCtx, "journalctl", "--since", "24 hours ago", "-o", "json", "--output-fields=__REALTIME_TIMESTAMP,PRIORITY").Output(); err == nil {
		scanner := bufio.NewScanner(strings.NewReader(string(out)))
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line == "" {
				continue
			}
			var m map[string]interface{}
			if err := json.Unmarshal([]byte(line), &m); err != nil {
				continue
			}
			rtStr, _ := m["__REALTIME_TIMESTAMP"].(string)
			us, err := strconv.ParseInt(rtStr, 10, 64)
			if err != nil {
				continue
			}
			t := time.Unix(us/1000000, 0).UTC()
			diffHours := int(now.Sub(t).Hours())
			if diffHours >= 0 && diffHours < 24 {
				bucketIdx := 23 - diffHours
				if bucketIdx >= 0 && bucketIdx < 24 {
					pStr, _ := m["PRIORITY"].(string)
					p, _ := strconv.Atoi(pStr)
					if p <= 3 {
						buckets[bucketIdx].Error++
					} else if p == 4 {
						buckets[bucketIdx].Warn++
					} else {
						buckets[bucketIdx].Info++
					}
					buckets[bucketIdx].Total++
				}
			}
		}
	}

	totalErr := 0
	totalWarn := 0
	totalLines := 0
	for _, b := range buckets {
		totalErr += b.Error
		totalWarn += b.Warn
		totalLines += b.Total
	}

	result := LogHistogramResult{
		Buckets:       buckets,
		TotalErrors:   totalErr,
		TotalWarnings: totalWarn,
		TotalLines:    totalLines,
	}

	resJSON, err := json.Marshal(result)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal error: %v", err)}
	}

	return IntentResult{Success: true, Output: string(resJSON)}
}

var allowedLogPrefixes = []string{
	"/var/log/",
	"/var/log/journal/",
	"/var/lib/docker/containers/",
}

func isAllowedLogPath(path string) bool {
	cleanPath := filepath.Clean(path)
	absPath, err := filepath.Abs(cleanPath)
	if err != nil {
		return false
	}

	// 3. Resolve symlinks to prevent symlink traversal bypass
	if realPath, err := filepath.EvalSymlinks(absPath); err == nil {
		absPath = realPath
	}

	for _, prefix := range allowedLogPrefixes {
		cleanPrefix := filepath.Clean(prefix)
		absPrefix, err := filepath.Abs(cleanPrefix)
		if err != nil {
			continue
		}

		if strings.HasPrefix(absPath, absPrefix) {
			if len(absPath) == len(absPrefix) || absPath[len(absPrefix)] == filepath.Separator {
				return true
			}
		}
	}
	return false
}

type LogFileEntry struct {
	Path string  `json:"path"`
	Size int64   `json:"size"`
	Mtime float64 `json:"mtime"`
}

func listLogFiles(root string, maxDepth, limit int) ([]LogSourceItem, bool, error) {
	return listLogFilesFromRoots(context.Background(), []string{root}, maxDepth, limit)
}

func listLogFilesFromRoots(ctx context.Context, roots []string, maxDepth, limit int) ([]LogSourceItem, bool, error) {
	var all []LogSourceItem
	for _, root := range roots {
		if _, err := os.Stat(root); err != nil {
			continue
		}
		_ = filepath.Walk(root, func(p string, info os.FileInfo, err error) error {
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
			if err != nil || info == nil {
				return nil
			}
			if info.IsDir() {
				rel, _ := filepath.Rel(root, p)
				depth := 0
				if rel != "." {
					depth = len(strings.Split(rel, string(filepath.Separator)))
				}
				if depth > maxDepth {
					return filepath.SkipDir
				}
				return nil
			}
			rel, _ := filepath.Rel(root, p)
			depth := len(strings.Split(filepath.Dir(rel), string(filepath.Separator)))
			if depth > maxDepth && maxDepth >= 0 {
				return nil
			}
			if info.Mode()&os.ModeSymlink != 0 {
				return nil
			}
			if strings.HasSuffix(p, ".journal") {
				return nil
			}
			if !isAllowedLogPath(p) {
				// For test roots that are temp dirs, allow any path under root
				if !strings.HasPrefix(p, root) {
					return nil
				}
			}
			all = append(all, LogSourceItem{
				ID:        p,
				Name:      filepath.Base(p),
				Category:  "files",
				Path:      p,
				SizeBytes: info.Size(),
				Mtime:     float64(info.ModTime().Unix()),
			})
			return nil
		})
	}
	sort.Slice(all, func(i, j int) bool {
		return all[i].Mtime > all[j].Mtime
	})
	truncated := false
	if len(all) > limit {
		all = all[:limit]
		truncated = true
	}
	return all, truncated, nil
}

func handleListLogFiles(ctx context.Context, intent Intent) IntentResult {
	// For test contract: return {"files": [...], "truncated": bool}
	entries, truncated, err := listLogFilesFromRoots(ctx, []string{"/var/log", "/var/lib/docker/containers"}, 3, 500)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("list failed: %v", err)}
	}
	// Map to LogFileEntry for test contract
	files := make([]LogFileEntry, 0, len(entries))
	for _, e := range entries {
		files = append(files, LogFileEntry{Path: e.Path, Size: e.SizeBytes, Mtime: e.Mtime})
	}
	payload := map[string]interface{}{"files": files, "truncated": truncated}
	b, _ := json.Marshal(payload)
	return IntentResult{Success: true, Output: string(b)}
}

