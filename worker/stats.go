package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"
)

var ignoredDiskFilesystemTypes = map[string]struct{}{
	"autofs":      {},
	"binfmt_misc": {},
	"bpf":         {},
	"cgroup":      {},
	"cgroup2":     {},
	"configfs":    {},
	"debugfs":     {},
	"devpts":      {},
	"devtmpfs":    {},
	"fusectl":     {},
	"hugetlbfs":   {},
	"mqueue":      {},
	"nsfs":        {},
	"overlay":     {},
	"pstore":      {},
	"proc":        {},
	"ramfs":       {},
	"rpc_pipefs":  {},
	"securityfs":  {},
	"squashfs":    {},
	"sysfs":       {},
	"tmpfs":       {},
	"tracefs":     {},
}

// DiskMount describes a single mounted filesystem's usage.
type DiskMount struct {
	MountPoint string  `json:"mount_point"`
	FsType     string  `json:"fs_type"`
	Device     string  `json:"device"`
	TotalBytes int64   `json:"total_bytes"`
	UsedBytes  int64   `json:"used_bytes"`
	Percent    float64 `json:"percent"`
}

// MetricsSnapshot contains the system metrics collected from /proc.
type MetricsSnapshot struct {
	CPUPercent    float64     `json:"cpu_percent"`
	CPULoad1m     float64     `json:"cpu_load_1m,omitempty"`
	CPULoad5m     float64     `json:"cpu_load_5m,omitempty"`
	CPULoad15m    float64     `json:"cpu_load_15m,omitempty"`
	CPUCores      int         `json:"cpu_cores,omitempty"`
	MemTotalBytes int64       `json:"mem_total_bytes"`
	MemUsedBytes  int64       `json:"mem_used_bytes"`
	MemPercent    float64     `json:"mem_percent"`
	SwapTotal     int64       `json:"swap_total_bytes"`
	SwapUsed      int64       `json:"swap_used_bytes"`
	DiskTotal     int64       `json:"disk_total_bytes"`
	DiskUsed      int64       `json:"disk_used_bytes"`
	DiskPercent   float64     `json:"disk_percent"`
	Disks         []DiskMount `json:"disks,omitempty"`
	UptimeSeconds float64     `json:"uptime_seconds"`
	Processes     int         `json:"processes,omitempty"`
	CollectedAt   float64     `json:"collected_at"`
}

// collectMetrics gathers all system metrics from /proc (Linux) or sysctl/ps (macOS).
func collectMetrics() MetricsSnapshot {
	now := float64(time.Now().UnixMicro()) / 1_000_000
	if runtime.GOOS == "darwin" {
		return collectDarwinMetrics(now)
	}
	diskTotal, diskUsed, diskPercent, disks := getDiskMetrics()
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
		DiskTotal:     diskTotal,
		DiskUsed:      diskUsed,
		DiskPercent:   diskPercent,
		Disks:         disks,
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
			if i == 3 || i == 4 { // idle + iowait (fields 4 and 5 in /proc/stat)
				idle += v
			}
		}
		if prevTotal.Load() == 0 {
			prevIdle.Store(idle)
			prevTotal.Store(total)
			time.Sleep(500 * time.Millisecond)
			return getCPUPercent()
		}
		diffIdle := idle - prevIdle.Load()
		diffTotal := total - prevTotal.Load()
		prevIdle.Store(idle)
		prevTotal.Store(total)
		if diffTotal == 0 {
			return 0
		}
		return math.Round((1-float64(diffIdle)/float64(diffTotal))*1000) / 10
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
	return runtime.NumCPU()
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

// ── Disk (all mounted filesystems on Linux, root fallback elsewhere) ──────

func getDiskMetrics() (int64, int64, float64, []DiskMount) {
	if runtime.GOOS == "darwin" {
		return getDarwinDiskMetrics()
	}
	return getLinuxDiskMetrics()
}

func getDarwinDiskMetrics() (int64, int64, float64, []DiskMount) {
	total, used, percent := getRootDiskMetrics("/")
	return total, used, percent, nil
}

func getLinuxDiskMetrics() (int64, int64, float64, []DiskMount) {
	file, err := os.Open("/proc/mounts")
	if err != nil {
		total, used, percent := getRootDiskMetrics("/")
		return total, used, percent, nil
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	seenDevices := make(map[string]struct{})
	var total, used int64
	var disks []DiskMount

	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) < 3 {
			continue
		}
		device := fields[0]
		mountPoint := unescapeMountField(fields[1])
		fsType := fields[2]
		if _, ignored := ignoredDiskFilesystemTypes[fsType]; ignored {
			continue
		}

		// Deduplicate by device to prevent double-counting disks with multiple mount points
		if _, exists := seenDevices[device]; exists {
			continue
		}
		seenDevices[device] = struct{}{}

		mountTotal, mountUsed, mountPercent := getRootDiskMetrics(mountPoint)
		if mountTotal <= 0 {
			continue
		}
		total += mountTotal
		used += mountUsed
		disks = append(disks, DiskMount{
			MountPoint: mountPoint,
			FsType:     fsType,
			Device:     device,
			TotalBytes: mountTotal,
			UsedBytes:  mountUsed,
			Percent:    mountPercent,
		})
	}

	if total <= 0 {
		rootTotal, rootUsed, rootPercent := getRootDiskMetrics("/")
		return rootTotal, rootUsed, rootPercent, nil
	}
	return total, used, math.Round(float64(used)/float64(total)*1000) / 10, disks
}

func getRootDiskMetrics(path string) (int64, int64, float64) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return 0, 0, 0
	}
	total := int64(stat.Blocks) * int64(stat.Bsize)
	free := int64(stat.Bavail) * int64(stat.Bsize)
	used := total - free
	if used < 0 {
		used = 0
	}
	if total == 0 {
		return 0, 0, 0
	}
	return total, used, math.Round(float64(used)/float64(total)*1000) / 10
}

func unescapeMountField(value string) string {
	replacer := strings.NewReplacer(
		`\040`, " ",
		`\011`, "\t",
		`\012`, "\n",
		`\134`, `\`,
	)
	return replacer.Replace(value)
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
		"type":             "STATUS_REPORT",
		"version":          Version,
		"cpu_percent":      m.CPUPercent,
		"cpu_load_1m":      m.CPULoad1m,
		"cpu_load_5m":      m.CPULoad5m,
		"cpu_load_15m":     m.CPULoad15m,
		"cpu_cores":        m.CPUCores,
		"mem_total_bytes":  m.MemTotalBytes,
		"mem_used_bytes":   m.MemUsedBytes,
		"mem_percent":      m.MemPercent,
		"swap_total_bytes": m.SwapTotal,
		"swap_used_bytes":  m.SwapUsed,
		"disk_total_bytes": m.DiskTotal,
		"disk_used_bytes":  m.DiskUsed,
		"disk_percent":     m.DiskPercent,
		"disks":            m.Disks,
		"uptime_seconds":   m.UptimeSeconds,
		"processes":        m.Processes,
		"collected_at":     m.CollectedAt,
	}
}

// ── Darwin (macOS) Fallback Metrics Helpers ──────────────────────────

func collectDarwinMetrics(now float64) MetricsSnapshot {
	cores := runtime.NumCPU()
	diskTotal, diskUsed, diskPercent, disks := getDiskMetrics()

	cpuPercent := getDarwinCPUPercent()
	load1, load5, load15 := getDarwinLoadAvg()
	memTotal, memUsed, memPercent := getDarwinMem()
	swapTotal, swapUsed := getDarwinSwap()
	uptime := getDarwinUptime()
	procCount := getDarwinProcessCount()

	return MetricsSnapshot{
		CPUPercent:    cpuPercent,
		CPULoad1m:     load1,
		CPULoad5m:     load5,
		CPULoad15m:    load15,
		CPUCores:      cores,
		MemTotalBytes: memTotal,
		MemUsedBytes:  memUsed,
		MemPercent:    memPercent,
		SwapTotal:     swapTotal,
		SwapUsed:      swapUsed,
		DiskTotal:     diskTotal,
		DiskUsed:      diskUsed,
		DiskPercent:   diskPercent,
		Disks:         disks,
		UptimeSeconds: uptime,
		Processes:     procCount,
		CollectedAt:   now,
	}
}

func getDarwinCPUPercent() float64 {
	cmd := exec.Command("ps", "-A", "-o", "%cpu")
	out, err := cmd.Output()
	if err != nil {
		return 0
	}
	lines := strings.Split(string(out), "\n")
	var sum float64
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || line == "%CPU" {
			continue
		}
		val, err := strconv.ParseFloat(line, 64)
		if err == nil {
			sum += val
		}
	}
	cores := float64(runtime.NumCPU())
	if cores <= 0 {
		cores = 1
	}
	percent := sum / cores
	if percent > 100.0 {
		percent = 100.0
	}
	return math.Round(percent*100) / 100
}

func getDarwinLoadAvg() (float64, float64, float64) {
	cmd := exec.Command("sysctl", "-n", "vm.loadavg")
	out, err := cmd.Output()
	if err != nil {
		return 0, 0, 0
	}
	s := strings.TrimSpace(string(out))
	s = strings.Trim(s, "{}")
	fields := strings.Fields(s)
	if len(fields) < 3 {
		return 0, 0, 0
	}
	l1, _ := strconv.ParseFloat(fields[0], 64)
	l5, _ := strconv.ParseFloat(fields[1], 64)
	l15, _ := strconv.ParseFloat(fields[2], 64)
	return l1, l5, l15
}

func getDarwinMem() (int64, int64, float64) {
	cmd := exec.Command("sysctl", "-n", "hw.memsize")
	out, err := cmd.Output()
	if err != nil {
		return 0, 0, 0
	}
	total, err := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64)
	if err != nil {
		return 0, 0, 0
	}

	cmdStats := exec.Command("vm_stat")
	statsOut, err := cmdStats.Output()
	if err != nil {
		return total, 0, 0
	}

	pageSize := int64(4096)
	var freePages, inactivePages, speculativePages int64

	scanner := bufio.NewScanner(strings.NewReader(string(statsOut)))
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "page size of") {
			parts := strings.Fields(line)
			if len(parts) >= 5 {
				ps, err := strconv.ParseInt(parts[4], 10, 64)
				if err == nil {
					pageSize = ps
				}
			}
		} else if strings.HasPrefix(line, "Pages free:") {
			freePages = extractVmStatValue(line)
		} else if strings.HasPrefix(line, "Pages inactive:") {
			inactivePages = extractVmStatValue(line)
		} else if strings.HasPrefix(line, "Pages speculative:") {
			speculativePages = extractVmStatValue(line)
		}
	}

	freeBytes := (freePages + inactivePages + speculativePages) * pageSize
	usedBytes := total - freeBytes
	if usedBytes < 0 {
		usedBytes = 0
	}
	percent := float64(usedBytes) / float64(total) * 100
	return total, usedBytes, math.Round(percent*10) / 10
}

func extractVmStatValue(line string) int64 {
	parts := strings.Fields(line)
	if len(parts) < 2 {
		return 0
	}
	valStr := strings.TrimSuffix(parts[len(parts)-1], ".")
	val, _ := strconv.ParseInt(valStr, 10, 64)
	return val
}

func getDarwinSwap() (int64, int64) {
	cmd := exec.Command("sysctl", "-n", "vm.swapusage")
	out, err := cmd.Output()
	if err != nil {
		return 0, 0
	}
	s := strings.TrimSpace(string(out))
	fields := strings.Fields(s)
	var totalBytes, usedBytes int64
	for i, f := range fields {
		if f == "total" && i+2 < len(fields) {
			totalBytes = parseSwapVal(fields[i+2])
		}
		if f == "used" && i+2 < len(fields) {
			usedBytes = parseSwapVal(fields[i+2])
		}
	}
	return totalBytes, usedBytes
}

func parseSwapVal(s string) int64 {
	if s == "" {
		return 0
	}
	unit := s[len(s)-1]
	valStr := s[:len(s)-1]
	val, err := strconv.ParseFloat(valStr, 64)
	if err != nil {
		return 0
	}
	switch unit {
	case 'G', 'g':
		return int64(val * 1024 * 1024 * 1024)
	case 'M', 'm':
		return int64(val * 1024 * 1024)
	case 'K', 'k':
		return int64(val * 1024)
	default:
		return int64(val)
	}
}

func getDarwinUptime() float64 {
	cmd := exec.Command("sysctl", "-n", "kern.boottime")
	out, err := cmd.Output()
	if err != nil {
		return 0
	}
	s := string(out)
	idx := strings.Index(s, "sec =")
	if idx == -1 {
		return 0
	}
	sub := s[idx+5:]
	comma := strings.Index(sub, ",")
	if comma == -1 {
		return 0
	}
	secStr := strings.TrimSpace(sub[:comma])
	sec, err := strconv.ParseInt(secStr, 10, 64)
	if err != nil {
		return 0
	}
	uptime := time.Now().Unix() - sec
	if uptime < 0 {
		return 0
	}
	return float64(uptime)
}

func getDarwinProcessCount() int {
	cmd := exec.Command("ps", "-A")
	out, err := cmd.Output()
	if err != nil {
		return 0
	}
	lines := strings.Split(string(out), "\n")
	count := 0
	for _, l := range lines {
		if strings.TrimSpace(l) != "" {
			count++
		}
	}
	if count > 0 {
		count-- // exclude header
	}
	return count
}
