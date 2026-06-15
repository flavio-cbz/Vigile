package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
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
	memTotal, memUsed, memPercent, swapTotal, swapUsed := getMemStats()
	diskTotal, diskUsed, diskPercent := getDiskStats()
	return MetricsSnapshot{
		CPUPercent:    getCPUPercent(),
		CPULoad1m:     getLoadAvg(0),
		CPULoad5m:     getLoadAvg(1),
		CPULoad15m:    getLoadAvg(2),
		CPUCores:      getCPUCores(),
		MemTotalBytes: memTotal,
		MemUsedBytes:  memUsed,
		MemPercent:    memPercent,
		SwapTotal:     swapTotal,
		SwapUsed:      swapUsed,
		DiskTotal:     diskTotal,
		DiskUsed:      diskUsed,
		DiskPercent:   diskPercent,
		UptimeSeconds: getUptime(),
		Processes:     getProcessCount(),
		CollectedAt:   now,
	}
}

// ── CPU ──────────────────────────────────────────────────────────────

var prevIdle, prevTotal atomic.Uint64

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
		if prevTotal.Load() == 0 {
			prevIdle.Store(idle)
			prevTotal.Store(total)
			return 0
		}
		diffIdle := idle - prevIdle.Load()
		diffTotal := total - prevTotal.Load()
		prevIdle.Store(idle)
		prevTotal.Store(total)
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

func getMemStats() (total int64, used int64, percent float64, swapTotal int64, swapUsed int64) {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0, 0, 0, 0, 0
	}
	fields := make(map[string]int64)
	for _, line := range strings.Split(string(data), "\n") {
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			field := strings.TrimSuffix(parts[0], ":")
			v, _ := strconv.ParseInt(parts[1], 10, 64)
			fields[field] = v * 1024 // kB -> bytes
		}
	}
	total = fields["MemTotal"]
	available := fields["MemAvailable"]
	if available > 0 {
		used = total - available
	} else {
		used = total - fields["MemFree"] - fields["Buffers"] - fields["Cached"]
	}
	if total > 0 {
		percent = math.Round(float64(used)/float64(total)*1000) / 10
	}
	swapTotal = fields["SwapTotal"]
	swapUsed = swapTotal - fields["SwapFree"]
	return total, used, percent, swapTotal, swapUsed
}

// ── Disk (root partition) ────────────────────────────────────────────

func getDiskStats() (total int64, used int64, percent float64) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs("/", &stat); err != nil {
		return 0, 0, 0
	}
	total = int64(stat.Blocks) * stat.Bsize
	free := int64(stat.Bavail) * stat.Bsize
	used = total - free
	if total > 0 {
		percent = math.Round(float64(used)/float64(total)*1000) / 10
	}
	return total, used, percent
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
	out, _ := json.Marshal(m)
	var report map[string]interface{}
	_ = json.Unmarshal(out, &report)
	report["type"] = "STATUS_REPORT"
	return report
}
