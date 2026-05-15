package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// MetricsSnapshot contains the system metrics collected from /proc.
type MetricsSnapshot struct {
	CPUPercent    float64 `json:"cpu_percent"`
	CPULoad1m     float64 `json:"cpu_load_1m,omitempty"`
	CPULoad5m     float64 `json:"cpu_load_5m,omitempty"`
	CPULoad15m    float64 `json:"cpu_load_15m,omitempty"`
	CPUCores      int     `json:"cpu_cores,omitempty"`
	MemTotalBytes int64   `json:"mem_total_bytes"`
	MemUsedBytes  int64   `json:"mem_used_bytes"`
	MemPercent    float64 `json:"mem_percent"`
	SwapTotal     int64   `json:"swap_total_bytes"`
	SwapUsed      int64   `json:"swap_used_bytes"`
	DiskTotal     int64   `json:"disk_total_bytes"`
	DiskUsed      int64   `json:"disk_used_bytes"`
	DiskPercent   float64 `json:"disk_percent"`
	UptimeSeconds float64 `json:"uptime_seconds"`
	Processes     int     `json:"processes,omitempty"`
	CollectedAt   float64 `json:"collected_at"`
}

// collectMetrics gathers all system metrics from /proc (Linux).
func collectMetrics() MetricsSnapshot {
	now := float64(time.Now().UnixMicro()) / 1_000_000
	return MetricsSnapshot{
		CPUPercent:    getCPUPercent(),
		CPULoad1m:     getLoadAvg(0),
		CPULoad5m:     getLoadAvg(1),
		CPULoad15m:    getLoadAvg(2),
		CPUCores:      getCPUCores(),
		MemTotalBytes: getMemField("MemTotal"),
		MemUsedBytes:  getMemUsed(),
		MemPercent:    getMemPercent(),
		SwapTotal:     getMemField("SwapTotal"),
		SwapUsed:      getSwapUsed(),
		DiskTotal:     getDiskTotal(),
		DiskUsed:      getDiskUsed(),
		DiskPercent:   getDiskPercent(),
		UptimeSeconds: getUptime(),
		Processes:     getProcessCount(),
		CollectedAt:   now,
	}
}

// ── CPU ──────────────────────────────────────────────────────────────

var prevIdle, prevTotal uint64

func getCPUPercent() float64 {
	data, err := os.ReadFile("/proc/stat")
	if err != nil {
		return 0
	}
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "cpu ") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 5 {
			return 0
		}
		var idle, total uint64
		for i, f := range fields[1:] {
			v, _ := strconv.ParseUint(f, 10, 64)
			total += v
			if i == 3 { // idle (field 4 in /proc/stat: user nice system idle)
				idle = v
			}
		}
		if prevTotal == 0 {
			prevIdle, prevTotal = idle, total
			return 0
		}
		diffIdle := idle - prevIdle
		diffTotal := total - prevTotal
		prevIdle, prevTotal = idle, total
		if diffTotal == 0 {
			return 0
		}
		return math.Round((1-float64(diffIdle)/float64(diffTotal))*100) / 100
	}
	return 0
}

func getLoadAvg(index int) float64 {
	data, err := os.ReadFile("/proc/loadavg")
	if err != nil {
		return 0
	}
	fields := strings.Fields(string(data))
	if len(fields) < 3 {
		return 0
	}
	v, _ := strconv.ParseFloat(fields[index], 64)
	return v
}

func getCPUCores() int {
	data, err := os.ReadFile("/proc/cpuinfo")
	if err != nil {
		return 0
	}
	count := 0
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "processor") {
			count++
		}
	}
	if count == 0 {
		count = 1
	}
	return count
}

// ── Memory ───────────────────────────────────────────────────────────

func getMemField(field string) int64 {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0
	}
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, field+":") {
			parts := strings.Fields(line)
			if len(parts) >= 2 {
				v, _ := strconv.ParseInt(parts[1], 10, 64)
				return v * 1024 // kB → bytes
			}
		}
	}
	return 0
}

func getMemUsed() int64 {
	total := getMemField("MemTotal")
	available := getMemField("MemAvailable")
	if available > 0 {
		return total - available
	}
	free := getMemField("MemFree")
	buffers := getMemField("Buffers")
	cached := getMemField("Cached")
	return total - free - buffers - cached
}

func getMemPercent() float64 {
	total := getMemField("MemTotal")
	if total == 0 {
		return 0
	}
	used := getMemUsed()
	return math.Round(float64(used)/float64(total)*1000) / 10
}

func getSwapUsed() int64 {
	total := getMemField("SwapTotal")
	free := getMemField("SwapFree")
	if total <= 0 {
		return 0
	}
	return total - free
}

// ── Disk (root partition) ────────────────────────────────────────────

func getDiskTotal() int64 {
	var stat syscall.Statfs_t
	if err := syscall.Statfs("/", &stat); err != nil {
		return 0
	}
	return int64(stat.Blocks) * stat.Bsize
}

func getDiskUsed() int64 {
	var stat syscall.Statfs_t
	if err := syscall.Statfs("/", &stat); err != nil {
		return 0
	}
	total := int64(stat.Blocks) * stat.Bsize
	free := int64(stat.Bavail) * stat.Bsize
	return total - free
}

func getDiskPercent() float64 {
	total := getDiskTotal()
	if total == 0 {
		return 0
	}
	used := getDiskUsed()
	return math.Round(float64(used)/float64(total)*1000) / 10
}

// ── System ───────────────────────────────────────────────────────────

func getUptime() float64 {
	data, err := os.ReadFile("/proc/uptime")
	if err != nil {
		return 0
	}
	fields := strings.Fields(string(data))
	if len(fields) == 0 {
		return 0
	}
	v, _ := strconv.ParseFloat(fields[0], 64)
	return v
}

func getProcessCount() int {
	d, err := os.Open("/proc")
	if err != nil {
		return 0
	}
	defer d.Close()
	entries, err := d.Readdirnames(-1)
	if err != nil {
		return 0
	}
	count := 0
	for _, name := range entries {
		if isNumeric(name) {
			count++
		}
	}
	return count
}

func isNumeric(s string) bool {
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return len(s) > 0
}

// ── Intent handler ───────────────────────────────────────────────────

// handleGetStats collects metrics and returns them as a STATUS_REPORT.
func handleGetStats(intent Intent) IntentResult {
	metrics := collectMetrics()
	out, err := json.Marshal(metrics)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal error: %v", err)}
	}
	return IntentResult{Success: true, Output: string(out)}
}

// buildStatusReport builds a STATUS_REPORT message from metrics.
func buildStatusReport() map[string]interface{} {
	m := collectMetrics()
	return map[string]interface{}{
		"type":            "STATUS_REPORT",
		"cpu_percent":     m.CPUPercent,
		"cpu_load_1m":     m.CPULoad1m,
		"cpu_load_5m":     m.CPULoad5m,
		"cpu_load_15m":    m.CPULoad15m,
		"cpu_cores":       m.CPUCores,
		"mem_total_bytes": m.MemTotalBytes,
		"mem_used_bytes":  m.MemUsedBytes,
		"mem_percent":     m.MemPercent,
		"swap_total_bytes": m.SwapTotal,
		"swap_used_bytes": m.SwapUsed,
		"disk_total_bytes": m.DiskTotal,
		"disk_used_bytes": m.DiskUsed,
		"disk_percent":    m.DiskPercent,
		"uptime_seconds":  m.UptimeSeconds,
		"processes":       m.Processes,
		"collected_at":    m.CollectedAt,
	}
}
