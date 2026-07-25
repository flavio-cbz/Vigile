package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
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

var procPrefix = ""

func init() {
	if _, err := os.Stat("/host/proc"); err == nil {
		procPrefix = "/host"
	}
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

// ProcessInfo describes a single running process with its CPU and memory usage.
type ProcessInfo struct {
	PID        int     `json:"pid"`
	Name       string  `json:"name"`
	CPUPercent float64 `json:"cpu_percent"`
	MemRSSKB   int64   `json:"mem_rss_kb"`
	State      string  `json:"state"`
}

// MetricsSnapshot contains the system metrics collected from /proc.
type MetricsSnapshot struct {
	// CPU
	CPUPercent    float64 `json:"cpu_percent"`
	CPULoad1m     float64 `json:"cpu_load_1m,omitempty"`
	CPULoad5m     float64 `json:"cpu_load_5m,omitempty"`
	CPULoad15m    float64 `json:"cpu_load_15m,omitempty"`
	CPUCores      int     `json:"cpu_cores,omitempty"`
	// Memory
	MemTotalBytes int64   `json:"mem_total_bytes"`
	MemUsedBytes  int64   `json:"mem_used_bytes"`
	MemPercent    float64 `json:"mem_percent"`
	// Swap
	SwapTotal int64 `json:"swap_total_bytes"`
	SwapUsed  int64 `json:"swap_used_bytes"`
	// Disk (root partition)
	DiskTotal   int64       `json:"disk_total_bytes"`
	DiskUsed    int64       `json:"disk_used_bytes"`
	DiskPercent float64     `json:"disk_percent"`
	Disks       []DiskMount `json:"disks,omitempty"`
	// System
	UptimeSeconds float64       `json:"uptime_seconds"`
	Processes     int           `json:"processes,omitempty"`
	TopProcesses  []ProcessInfo `json:"top_processes,omitempty"`
	// Network I/O (cumulative since boot, aggregate across non-loopback interfaces)
	NetBytesRecv  int64 `json:"net_bytes_recv,omitempty"`
	NetBytesSent  int64 `json:"net_bytes_sent,omitempty"`
	NetPktRecv    int64 `json:"net_packets_recv,omitempty"`
	NetPktSent    int64 `json:"net_packets_sent,omitempty"`
	NetErrIn      int64 `json:"net_errors_in,omitempty"`
	NetErrOut     int64 `json:"net_errors_out,omitempty"`
	NetDropIn     int64 `json:"net_drops_in,omitempty"`
	NetDropOut    int64 `json:"net_drops_out,omitempty"`
	// Disk I/O (cumulative since boot, aggregate across physical devices)
	DiskReads      int64 `json:"disk_reads,omitempty"`
	DiskWrites     int64 `json:"disk_writes,omitempty"`
	DiskReadBytes  int64 `json:"disk_read_bytes,omitempty"`
	DiskWriteBytes int64 `json:"disk_write_bytes,omitempty"`
	// Temperature (max across thermal zones, in Celsius)
	TempCelsius float64 `json:"temp_celsius,omitempty"`
	// PSI — Pressure Stall Information (avg10)
	PSICPUAvg10 float64 `json:"psi_cpu_avg10,omitempty"`
	PSIMemAvg10 float64 `json:"psi_mem_avg10,omitempty"`
	PSIOAvg10   float64 `json:"psi_io_avg10,omitempty"`
	// File handles / inodes
	FileHandlesUsed int64 `json:"file_handles_used,omitempty"`
	FileHandlesMax  int64 `json:"file_handles_max,omitempty"`
	// Entropy available
	EntropyAvail int64 `json:"entropy_avail,omitempty"`
	// Context switches since boot
	ContextSwitches int64 `json:"context_switches,omitempty"`
	// CPU throttling (aggregate core throttle count)
	CPUThrottledCount int64 `json:"cpu_throttled_count,omitempty"`
	// Timestamp
	CollectedAt float64 `json:"collected_at"`
}

// collectMetrics gathers all system metrics from /proc (Linux) or sysctl/ps (macOS).
func collectMetrics(ctx context.Context) MetricsSnapshot {
	now := float64(time.Now().UnixMicro()) / 1_000_000
	if runtime.GOOS == "darwin" {
		return collectDarwinMetrics(ctx, now)
	}
	diskTotal, diskUsed, diskPercent, disks := getDiskMetrics()
	netBR, netBS, netPR, netPS, netEI, netEO, netDI, netDO := getNetworkStats()
	diskR, diskW, diskRB, diskWB := getDiskIO()
	psiCPU, psiMem, psiIO := getPSI()
	fhUsed, fhMax := getFileHandles()
	return MetricsSnapshot{
		CPUPercent:       getCPUPercent(),
		CPULoad1m:        getLoadAvg(0),
		CPULoad5m:        getLoadAvg(1),
		CPULoad15m:       getLoadAvg(2),
		CPUCores:         getCPUCores(),
		MemTotalBytes:    getMemField("MemTotal"),
		MemUsedBytes:     getMemUsed(),
		MemPercent:       getMemPercent(),
		SwapTotal:        getMemField("SwapTotal"),
		SwapUsed:         getSwapUsed(),
		DiskTotal:        diskTotal,
		DiskUsed:         diskUsed,
		DiskPercent:      diskPercent,
		Disks:            disks,
		UptimeSeconds:    getUptime(),
		Processes:        getProcessCount(),
		TopProcesses:     getTopProcesses(10),
		NetBytesRecv:     netBR,
		NetBytesSent:     netBS,
		NetPktRecv:       netPR,
		NetPktSent:       netPS,
		NetErrIn:         netEI,
		NetErrOut:        netEO,
		NetDropIn:        netDI,
		NetDropOut:       netDO,
		DiskReads:        diskR,
		DiskWrites:       diskW,
		DiskReadBytes:    diskRB,
		DiskWriteBytes:   diskWB,
		TempCelsius:      getTemperature(),
		PSICPUAvg10:      psiCPU,
		PSIMemAvg10:      psiMem,
		PSIOAvg10:        psiIO,
		FileHandlesUsed:  fhUsed,
		FileHandlesMax:   fhMax,
		EntropyAvail:     getEntropy(),
		ContextSwitches:  getContextSwitches(),
		CPUThrottledCount: getCPUThrottling(),
		CollectedAt:      now,
	}
}

// ── CPU ──────────────────────────────────────────────────────────────

var prevIdle, prevTotal atomic.Uint64

// prevProcSamples caches the previous (utime+stime, timestamp) reading per PID
// so that getTopProcesses can compute a delta-based (recent-window) CPU% across
// consecutive worker collection cycles, instead of a misleading lifetime average.
var prevProcSamples sync.Map // key: int (pid) -> procStatSample

type procStatSample struct {
	totalJiffies uint64
	t0           float64
}

func getCPUPercent() float64 {
	data, err := os.ReadFile(procPrefix + "/proc/stat")
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
			v, err := strconv.ParseUint(f, 10, 64)
			if err != nil {
				logger.Printf("stats: parse cpu field %q: %v", f, err)
			}
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
		pct := math.Round((1-float64(diffIdle)/float64(diffTotal))*1000) / 10
		log.Printf("[DEBUG CPU] diffIdle: %d, diffTotal: %d, pct: %.1f", diffIdle, diffTotal, pct)
		return pct
	}
	return 0
}

func getLoadAvg(index int) float64 {
	data, err := os.ReadFile(procPrefix + "/proc/loadavg")
	if err != nil {
		return 0
	}
	fields := strings.Fields(string(data))
	if len(fields) < 3 {
		return 0
	}
	v, err := strconv.ParseFloat(fields[index], 64)
	if err != nil {
		logger.Printf("stats: parse loadavg: %v", err)
	}
	return v
}

func getCPUCores() int {
	return runtime.NumCPU()
}

// ── Memory ───────────────────────────────────────────────────────────

func getMemField(field string) int64 {
	data, err := os.ReadFile(procPrefix + "/proc/meminfo")
	if err != nil {
		return 0
	}
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, field+":") {
			parts := strings.Fields(line)
			if len(parts) >= 2 {
				v, err := strconv.ParseInt(parts[1], 10, 64)
				if err != nil {
					logger.Printf("stats: parse meminfo %q: %v", field, err)
				}
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
	cmd := exec.Command("df", "-k")
	out, err := cmd.Output()
	if err != nil {
		total, used, percent := getRootDiskMetrics("/")
		return total, used, percent, nil
	}

	lines := strings.Split(string(out), "\n")
	var total, used int64
	var disks []DiskMount
	seenDevices := make(map[string]struct{})

	for i, line := range lines {
		if i == 0 || strings.TrimSpace(line) == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 9 {
			continue
		}
		device := fields[0]
		// Ignore virtual filesystems / devfs / map
		if device == "devfs" || strings.HasPrefix(device, "map ") || device == "map" {
			continue
		}
		mountPoint := fields[8]
		// Reconstruct mountPoint if it contains spaces
		if len(fields) > 9 {
			mountPoint = strings.Join(fields[8:], " ")
		}
		// Ignore standard macOS noise partitions
		if strings.HasPrefix(mountPoint, "/System/Volumes/Preboot") ||
			strings.HasPrefix(mountPoint, "/System/Volumes/VM") ||
			strings.HasPrefix(mountPoint, "/System/Volumes/Update") {
			continue
		}

		// Deduplicate by device
		if _, exists := seenDevices[device]; exists {
			continue
		}
		seenDevices[device] = struct{}{}

		totalKB, err := strconv.ParseInt(fields[1], 10, 64)
		if err != nil {
			logger.Printf("stats: parse disk total: %v", err)
		}
		usedKB, err := strconv.ParseInt(fields[2], 10, 64)
		if err != nil {
			logger.Printf("stats: parse disk used: %v", err)
		}

		mountTotal := totalKB * 1024
		mountUsed := usedKB * 1024

		var mountPercent float64
		if mountTotal > 0 {
			mountPercent = math.Round(float64(mountUsed)/float64(mountTotal)*1000) / 10
		}

		total += mountTotal
		used += mountUsed

		disks = append(disks, DiskMount{
			MountPoint: mountPoint,
			FsType:     "apfs",
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

func getLinuxDiskMetrics() (int64, int64, float64, []DiskMount) {
	file, err := os.Open(procPrefix + "/proc/mounts")
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
	data, err := os.ReadFile(procPrefix + "/proc/uptime")
	if err != nil {
		return 0
	}
	fields := strings.Fields(string(data))
	if len(fields) == 0 {
		return 0
	}
	v, err := strconv.ParseFloat(fields[0], 64)
	if err != nil {
		logger.Printf("stats: parse uptime: %v", err)
	}
	return v
}

func getProcessCount() int {
	d, err := os.Open(procPrefix + "/proc")
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

// ── Network I/O ────────────────────────────────────────────────────

func getNetworkStats() (bytesRecv, bytesSent, pktsRecv, pktsSent, errIn, errOut, dropIn, dropOut int64) {
	data, err := os.ReadFile(procPrefix + "/proc/net/dev")
	if err != nil {
		return 0, 0, 0, 0, 0, 0, 0, 0
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		// Skip headers and loopback
		if !strings.Contains(line, ":") || strings.HasPrefix(line, " ") {
			continue
		}
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		iface := strings.TrimSpace(parts[0])
		if iface == "lo" {
			continue
		}
		fields := strings.Fields(parts[1])
		if len(fields) < 16 {
			continue
		}
		// RX: bytes(0), packets(1), errs(2), drop(3)
		// TX: bytes(8), packets(9), errs(10), drop(11)
		bytesRecv += parseInt64(fields[0])
		pktsRecv += parseInt64(fields[1])
		errIn += parseInt64(fields[2])
		dropIn += parseInt64(fields[3])
		bytesSent += parseInt64(fields[8])
		pktsSent += parseInt64(fields[9])
		errOut += parseInt64(fields[10])
		dropOut += parseInt64(fields[11])
	}
	return
}

func parseInt64(s string) int64 {
	v, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		logger.Printf("stats: parse int64 %q: %v", s, err)
	}
	return v
}

// ── Disk I/O ────────────────────────────────────────────────────────

func getDiskIO() (reads, writes, readBytes, writeBytes int64) {
	data, err := os.ReadFile(procPrefix + "/proc/diskstats")
	if err != nil {
		return 0, 0, 0, 0
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		fields := strings.Fields(line)
		if len(fields) < 14 {
			continue
		}
		devName := fields[2]
		// Only aggregate physical devices (sd*, nvme*, vd*, xvd*, mmcblk*)
		if !isPhysicalDisk(devName) {
			continue
		}
		// fields[3] = reads completed, fields[4] = reads merged,
		// fields[5] = sectors read, fields[6] = time reading
		// fields[7] = writes completed, fields[8] = writes merged,
		// fields[9] = sectors written, fields[10] = time writing
		reads += parseInt64(fields[3])
		writes += parseInt64(fields[7])
		readBytes += parseInt64(fields[5]) * 512 // sectors to bytes
		writeBytes += parseInt64(fields[9]) * 512
	}
	return
}

// isPhysicalDisk returns true if the device name looks like a physical disk
// (whole device, not a partition). Partition device names end with a digit
// (e.g. sda1, nvme0n1p1) while whole devices don't (e.g. sda, nvme0n1).
func isPhysicalDisk(name string) bool {
	// Must start with one of these prefixes
	prefixOk := false
	for _, prefix := range []string{"sd", "nvme", "vd", "xvd", "mmcblk"} {
		if strings.HasPrefix(name, prefix) {
			prefixOk = true
			break
		}
	}
	if !prefixOk {
		return false
	}
	// Whole devices: last char is a letter OR the name ends with just "nX" (nvme)
	last := name[len(name)-1]
	if last >= 'a' && last <= 'z' {
		return true // sda, sdb, vda, etc.
	}
	// Handle nvme0n1 (ends with digit but is a whole device — nvme0n1, nvme1n2)
	if strings.HasPrefix(name, "nvme") {
		// nvme whole device pattern: nvme<num>n<num> (ends with digit)
		// partition would be nvme<num>n<num>p<num>
		// So if there's no 'p' before the last digit, it's a whole device
		lastP := strings.LastIndex(name, "p")
		if lastP > 0 {
			// Check if the 'p' is after "nvme" and before the end
			if lastP > len("nvme0") && lastP < len(name)-1 {
				return false // partition like nvme0n1p1
			}
		}
		return true
	}
	// mmcblk whole device: mmcblk0, mmcblk1 (partition: mmcblk0p1)
	if strings.HasPrefix(name, "mmcblk") {
		if strings.Contains(name, "p") {
			return false
		}
		return true
	}
	return false
}

// ── Temperature ─────────────────────────────────────────────────────

func getTemperature() float64 {
	pattern := procPrefix + "/sys/class/thermal/thermal_zone*/temp"
	matches, err := filepath.Glob(pattern)
	if err != nil || len(matches) == 0 {
		// Try without procPrefix for sysfs (sysfs is never under /proc)
		matches2, err2 := filepath.Glob("/sys/class/thermal/thermal_zone*/temp")
		if err2 != nil || len(matches2) == 0 {
			return 0
		}
		matches = matches2
	}
	var maxTemp float64
	for _, path := range matches {
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		v, err := strconv.ParseFloat(strings.TrimSpace(string(data)), 64)
		if err != nil {
			continue
		}
		celsius := v / 1000.0 // millicelsius → celsius
		if celsius > maxTemp {
			maxTemp = celsius
		}
	}
	return maxTemp
}

// ── PSI (Pressure Stall Information) ────────────────────────────────

func getPSI() (cpuAvg10, memAvg10, ioAvg10 float64) {
	cpuAvg10 = readPSIFile(procPrefix + "/proc/pressure/cpu")
	memAvg10 = readPSIFile(procPrefix + "/proc/pressure/memory")
	ioAvg10 = readPSIFile(procPrefix + "/proc/pressure/io")
	return
}

func readPSIFile(path string) float64 {
	data, err := os.ReadFile(path)
	if err != nil {
		return 0
	}
	// Format: "some avg10=0.00 avg60=0.00 avg300=0.00 total=0"
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "some ") {
			continue
		}
		fields := strings.Fields(line)
		for _, f := range fields {
			if strings.HasPrefix(f, "avg10=") {
				v, err := strconv.ParseFloat(f[6:], 64)
				if err != nil {
					return 0
				}
				return v
			}
		}
	}
	return 0
}

// ── File Handles / Entropy / Context Switches / CPU Throttling ──────

func getFileHandles() (used, max int64) {
	data, err := os.ReadFile(procPrefix + "/proc/sys/fs/file-nr")
	if err != nil {
		return 0, 0
	}
	fields := strings.Fields(string(data))
	if len(fields) >= 3 {
		used = parseInt64(fields[0])
		max = parseInt64(fields[2])
	}
	return
}

func getEntropy() int64 {
	data, err := os.ReadFile(procPrefix + "/proc/sys/kernel/random/entropy_avail")
	if err != nil {
		return 0
	}
	v, err := strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
	if err != nil {
		logger.Printf("stats: parse entropy: %v", err)
	}
	return v
}

func getContextSwitches() int64 {
	data, err := os.ReadFile(procPrefix + "/proc/stat")
	if err != nil {
		return 0
	}
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "ctxt ") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				return parseInt64(fields[1])
			}
		}
	}
	return 0
}

func getCPUThrottling() int64 {
	pattern := "/sys/devices/system/cpu/cpu*/thermal_throttle/core_throttle_count"
	matches, err := filepath.Glob(pattern)
	if err != nil || len(matches) == 0 {
		return 0
	}
	var total int64
	for _, path := range matches {
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		v, err := strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
		if err != nil {
			continue
		}
		total += v
	}
	return total
}

// ── Per-process CPU & Memory (Linux via /proc) ──────────────────────

func parseProcStat(data []byte) (name, state string, utime, stime, starttime uint64, rssPages int64) {
	s := string(data)
	openIdx := strings.IndexByte(s, '(')
	closeIdx := strings.LastIndexByte(s, ')')
	if openIdx == -1 || closeIdx == -1 || closeIdx <= openIdx {
		return "", "", 0, 0, 0, 0
	}
	name = s[openIdx+1 : closeIdx]
	fields := strings.Fields(s[closeIdx+2:])
	if len(fields) < 23 {
		return name, "", 0, 0, 0, 0
	}
	state = fields[0]
	var err error
	utime, err = strconv.ParseUint(fields[11], 10, 64)
	if err != nil {
		logger.Printf("stats: parse utime: %v", err)
	}
	stime, err = strconv.ParseUint(fields[12], 10, 64)
	if err != nil {
		logger.Printf("stats: parse stime: %v", err)
	}
	starttime, err = strconv.ParseUint(fields[19], 10, 64)
	if err != nil {
		logger.Printf("stats: parse starttime: %v", err)
	}
	rssPages, err = strconv.ParseInt(fields[22], 10, 64)
	if err != nil {
		logger.Printf("stats: parse rss: %v", err)
	}
	return
}

func getTopProcesses(limit int) []ProcessInfo {
	if limit <= 0 {
		limit = 10
	}
	d, err := os.Open(procPrefix + "/proc")
	if err != nil {
		return nil
	}
	defer d.Close()
	entries, err := d.Readdirnames(-1)
	if err != nil {
		return nil
	}
	hz := 100.0
	now := float64(time.Now().UnixMicro()) / 1_000_000
	uptime := getUptime()
	procs := make([]ProcessInfo, 0, len(entries))
	for _, pidStr := range entries {
		if !isNumeric(pidStr) {
			continue
		}
		data, err := os.ReadFile(procPrefix + "/proc/" + pidStr + "/stat")
		if err != nil {
			continue
		}
		pName, pState, utime, stime, starttime, rssPages := parseProcStat(data)
		if pName == "" {
			continue
		}
		pid, err := strconv.Atoi(pidStr)
		if err != nil {
			logger.Printf("stats: parse pid %q: %v", pidStr, err)
			continue
		}

		totalJiffies := utime + stime

		// Delta-based (recent-window) CPU% using the previous sample for this PID,
		// so the value reflects current usage rather than a lifetime average.
		// First sighting has no previous sample, so fall back to lifetime average.
		var cpuPct float64
		if prevSample, ok := prevProcSamples.Load(pid); ok {
			prev := prevSample.(procStatSample)
			deltaJiffies := int64(totalJiffies) - int64(prev.totalJiffies)
			deltaSec := now - prev.t0
			if deltaSec > 0 && deltaJiffies > 0 {
				cpuPct = float64(deltaJiffies) / hz / deltaSec * 100
				if cpuPct < 0 {
					cpuPct = 0
				}
				cpuPct = math.Round(cpuPct*10) / 10
			}
		} else {
			// Fallback: lifetime average since process start.
			if uptime > 0 {
				elapsedJiffies := uptime*hz - float64(starttime)
				if elapsedJiffies > 0 {
					cpuPct = math.Round(float64(totalJiffies)/elapsedJiffies*1000) / 10
				}
			}
		}

		prevProcSamples.Store(pid, procStatSample{totalJiffies: totalJiffies, t0: now})

		procs = append(procs, ProcessInfo{
			PID:        pid,
			Name:       pName,
			CPUPercent: cpuPct,
			MemRSSKB:   rssPages * 4,
			State:      pState,
		})
	}
	sort.Slice(procs, func(i, j int) bool {
		return procs[i].CPUPercent > procs[j].CPUPercent
	})
	if len(procs) > limit {
		procs = procs[:limit]
	}
	return procs
}

// ── Intent handler ───────────────────────────────────────────────────

// handleGetStats collects metrics and returns them as a STATUS_REPORT.
func handleGetStats(ctx context.Context, intent Intent) IntentResult {
	metrics := collectMetrics(ctx)
	out, err := json.Marshal(metrics)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal error: %v", err)}
	}
	return IntentResult{Success: true, Output: string(out)}
}

// buildStatusReport builds a STATUS_REPORT message from metrics.
func buildStatusReport(ctx context.Context) map[string]interface{} {
	m := collectMetrics(ctx)
	return map[string]interface{}{
		"type":                "STATUS_REPORT",
		"version":             Version,
		"cpu_percent":         m.CPUPercent,
		"cpu_load_1m":         m.CPULoad1m,
		"cpu_load_5m":         m.CPULoad5m,
		"cpu_load_15m":        m.CPULoad15m,
		"cpu_cores":           m.CPUCores,
		"mem_total_bytes":     m.MemTotalBytes,
		"mem_used_bytes":      m.MemUsedBytes,
		"mem_percent":         m.MemPercent,
		"swap_total_bytes":    m.SwapTotal,
		"swap_used_bytes":     m.SwapUsed,
		"disk_total_bytes":    m.DiskTotal,
		"disk_used_bytes":     m.DiskUsed,
		"disk_percent":        m.DiskPercent,
		"disks":               m.Disks,
		"uptime_seconds":      m.UptimeSeconds,
		"processes":           m.Processes,
		"top_processes":       m.TopProcesses,
		"net_bytes_recv":      m.NetBytesRecv,
		"net_bytes_sent":      m.NetBytesSent,
		"net_packets_recv":    m.NetPktRecv,
		"net_packets_sent":    m.NetPktSent,
		"net_errors_in":       m.NetErrIn,
		"net_errors_out":      m.NetErrOut,
		"net_drops_in":        m.NetDropIn,
		"net_drops_out":       m.NetDropOut,
		"disk_reads":          m.DiskReads,
		"disk_writes":         m.DiskWrites,
		"disk_read_bytes":     m.DiskReadBytes,
		"disk_write_bytes":    m.DiskWriteBytes,
		"temp_celsius":        m.TempCelsius,
		"psi_cpu_avg10":       m.PSICPUAvg10,
		"psi_mem_avg10":       m.PSIMemAvg10,
		"psi_io_avg10":        m.PSIOAvg10,
		"file_handles_used":   m.FileHandlesUsed,
		"file_handles_max":    m.FileHandlesMax,
		"entropy_avail":       m.EntropyAvail,
		"context_switches":    m.ContextSwitches,
		"cpu_throttled_count": m.CPUThrottledCount,
		"collected_at":        m.CollectedAt,
	}
}

// ── Darwin (macOS) Fallback Metrics Helpers ──────────────────────────

func collectDarwinMetrics(ctx context.Context, now float64) MetricsSnapshot {
	cores := runtime.NumCPU()
	diskTotal, diskUsed, diskPercent, disks := getDiskMetrics()

	cpuPercent := getDarwinCPUPercent(ctx)
	load1, load5, load15 := getDarwinLoadAvg(ctx)
	memTotal, memUsed, memPercent := getDarwinMem(ctx)
	swapTotal, swapUsed := getDarwinSwap(ctx)
	uptime := getDarwinUptime(ctx)
	procCount := getDarwinProcessCount(ctx)

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

func getDarwinCPUPercent(ctx context.Context) float64 {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	cmd := exec.CommandContext(cmdCtx, "ps", "-A", "-o", "%cpu")
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
		line = strings.ReplaceAll(line, ",", ".")
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

func getDarwinLoadAvg(ctx context.Context) (float64, float64, float64) {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	cmd := exec.CommandContext(cmdCtx, "sysctl", "-n", "vm.loadavg")
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
	l1, err := strconv.ParseFloat(fields[0], 64)
	if err != nil {
		logger.Printf("stats: parse load1: %v", err)
	}
	l5, err := strconv.ParseFloat(fields[1], 64)
	if err != nil {
		logger.Printf("stats: parse load5: %v", err)
	}
	l15, err := strconv.ParseFloat(fields[2], 64)
	if err != nil {
		logger.Printf("stats: parse load15: %v", err)
	}
	return l1, l5, l15
}

func getDarwinMem(ctx context.Context) (int64, int64, float64) {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	cmd := exec.CommandContext(cmdCtx, "sysctl", "-n", "hw.memsize")
	out, err := cmd.Output()
	if err != nil {
		return 0, 0, 0
	}
	total, err := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64)
	if err != nil {
		return 0, 0, 0
	}

	cmdStats := exec.CommandContext(cmdCtx, "vm_stat")
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
	val, err := strconv.ParseInt(valStr, 10, 64)
	if err != nil {
		logger.Printf("stats: parse vm_stat value: %v", err)
	}
	return val
}

func getDarwinSwap(ctx context.Context) (int64, int64) {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	cmd := exec.CommandContext(cmdCtx, "sysctl", "-n", "vm.swapusage")
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

func getDarwinUptime(ctx context.Context) float64 {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	cmd := exec.CommandContext(cmdCtx, "sysctl", "-n", "kern.boottime")
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

func getDarwinProcessCount(ctx context.Context) int {
	cmdCtx, cancel := context.WithTimeout(ctx, commandTimeout)
	defer cancel()
	cmd := exec.CommandContext(cmdCtx, "ps", "-A")
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
