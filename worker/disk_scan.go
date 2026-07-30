package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
)

const (
	scanTimeout        = 45 * time.Second
	maxScanResultBytes = 2 * 1024 * 1024  // 2 MB output cap
	maxChildrenPerNode = 50               // cap children per directory
	defaultMinSize     = 1 * 1024 * 1024  // 1 MB default min file size
)

// DiskNode matches master/schemas/disk_scan.py DiskNode schema exactly.
type DiskNode struct {
	Name     string     `json:"name"`
	Path     string     `json:"path"`
	Size     int64      `json:"size"`
	IsDir    bool       `json:"is_dir"`
	Children []DiskNode `json:"children,omitempty"`
}

// DiskScanResult matches master/schemas/disk_scan.py DiskScanResult schema exactly.
type DiskScanResult struct {
	Root        DiskNode `json:"root"`
	Truncated   bool     `json:"truncated"`
	ScannedAt   int64    `json:"scanned_at"`
	WalkedCount int      `json:"walked_count"`
	SkippedPerm int      `json:"skipped_perm"`
}

// walkStats tracks counters across the recursive walk.
type walkStats struct {
	walkedCount int
	skippedPerm int
}

// isAllowedScanPath validates the scan path against the dynamic mounts whitelist.
// Fail-closed: empty mounts → always false.
func isAllowedScanPath(path string, mounts []string) bool {
	if len(mounts) == 0 {
		return false
	}

	absPath, err := canonicalScanPath(path)
	if err != nil {
		return false
	}

	for _, mount := range mounts {
		absMount, err := canonicalScanPath(mount)
		if err != nil {
			continue
		}

		if absMount == string(filepath.Separator) {
			return true
		}

		if strings.HasPrefix(absPath, absMount) {
			if len(absPath) == len(absMount) || absPath[len(absMount)] == filepath.Separator {
				return true
			}
		}
	}
	return false
}

func canonicalScanPath(path string) (string, error) {
	cleanPath := filepath.Clean(path)
	absPath, err := filepath.Abs(cleanPath)
	if err != nil {
		return "", err
	}
	if realPath, err := filepath.EvalSymlinks(absPath); err == nil {
		absPath = realPath
	}
	return absPath, nil
}

// getParamBool extracts a bool from the params map.
func getParamBool(params map[string]interface{}, key string, defaultVal bool) bool {
	if params == nil {
		return defaultVal
	}
	if v, ok := params[key]; ok {
		if b, ok := v.(bool); ok {
			return b
		}
	}
	return defaultVal
}

// getParamStringSlice extracts a []string from a JSON array in params.
func getParamStringSlice(params map[string]interface{}, key string) []string {
	if params == nil {
		return nil
	}
	v, ok := params[key]
	if !ok {
		return nil
	}
	arr, ok := v.([]interface{})
	if !ok {
		return nil
	}
	result := make([]string, 0, len(arr))
	for _, item := range arr {
		if s, ok := item.(string); ok {
			result = append(result, s)
		}
	}
	return result
}

// handleDiskScan handles the DISK_SCAN intent.
func handleDiskScan(ctx context.Context, intent Intent) IntentResult {
	path := getParamString(intent.Params, "path", "/")
	maxDepth := getParamInt(intent.Params, "max_depth", 4)
	minSizeBytes := getParamInt(intent.Params, "min_size_bytes", defaultMinSize)
	maxChildren := getParamInt(intent.Params, "max_children_per_node", maxChildrenPerNode)
	includeHidden := getParamBool(intent.Params, "include_hidden", false)
	mounts := getParamStringSlice(intent.Params, "mounts")

	// Fail-closed: no mounts provided
	if len(mounts) == 0 {
		return IntentResult{Success: false, Error: "path not allowed: no mounts provided"}
	}

	// Fail-closed: path not in allowed mounts
	if !isAllowedScanPath(path, mounts) {
		return IntentResult{Success: false, Error: "path not allowed"}
	}

	scanCtx, cancel := context.WithTimeout(ctx, scanTimeout)
	defer cancel()

	stats := &walkStats{}
	root := walkDir(scanCtx, path, 0, maxDepth, minSizeBytes, maxChildren, includeHidden, stats)

	if scanCtx.Err() == context.DeadlineExceeded {
		return IntentResult{Success: false, Error: "disk scan timed out"}
	}

	result := DiskScanResult{
		Root:        root,
		Truncated:   false,
		ScannedAt:   time.Now().Unix(),
		WalkedCount: stats.walkedCount,
		SkippedPerm: stats.skippedPerm,
	}

	data, err := json.Marshal(result)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("marshal failed: %v", err)}
	}

	if len(data) > maxScanResultBytes {
		result.Truncated = true
		result.Root.Children = nil
		data, err = json.Marshal(result)
		if err != nil {
			return IntentResult{Success: false, Error: fmt.Sprintf("marshal failed: %v", err)}
		}
	}

	return IntentResult{Success: true, Output: string(data)}
}

// walkDir recursively scans a directory tree with depth control.
// Symlinks are never followed. Hidden files are skipped unless includeHidden is true.
func walkDir(ctx context.Context, path string, depth, maxDepth, minSizeBytes, maxChildren int, includeHidden bool, stats *walkStats) DiskNode {
	stats.walkedCount++

	info, err := os.Lstat(path)
	if err != nil {
		if os.IsPermission(err) {
			stats.skippedPerm++
		}
		return DiskNode{Name: filepath.Base(path), Path: path}
	}

	size := allocatedSize(info)
	node := DiskNode{
		Name:  filepath.Base(path),
		Path:  path,
		Size:  size,
		IsDir: info.IsDir(),
	}

	if !info.IsDir() || ctx.Err() != nil || depth >= maxDepth {
		return node
	}

	entries, err := os.ReadDir(path)
	if err != nil {
		if os.IsPermission(err) {
			stats.skippedPerm++
		}
		return node
	}

	var children []DiskNode
	for _, entry := range entries {
		if ctx.Err() != nil {
			break
		}

		if !includeHidden && strings.HasPrefix(entry.Name(), ".") {
			continue
		}

		childPath := filepath.Join(path, entry.Name())
		childInfo, err := os.Lstat(childPath)
		if err != nil {
			if os.IsPermission(err) {
				stats.skippedPerm++
			}
			continue
		}

		// Skip symlinks entirely — never follow.
		if childInfo.Mode()&os.ModeSymlink != 0 {
			continue
		}

		if childInfo.IsDir() && depth < maxDepth {
			child := walkDir(ctx, childPath, depth+1, maxDepth, minSizeBytes, maxChildren, includeHidden, stats)
			children = append(children, child)
		} else {
			stats.walkedCount++
			childSize := allocatedSize(childInfo)
			children = append(children, DiskNode{
				Name:  entry.Name(),
				Path:  childPath,
				Size:  childSize,
				IsDir: childInfo.IsDir(),
			})
		}
	}

	var dirSize int64
	for _, child := range children {
		dirSize += child.Size
	}
	if dirSize > 0 {
		node.Size = dirSize
	}

	node.Children = aggregateChildren(children, minSizeBytes, maxChildren, path)
	return node
}

// aggregateChildren sorts children by size descending, caps at maxChildren,
// and replaces small/extra entries with ghost summary nodes.
func aggregateChildren(children []DiskNode, minSizeBytes, maxChildren int, parentPath string) []DiskNode {
	if len(children) == 0 {
		return nil
	}

	sort.Slice(children, func(i, j int) bool {
		return children[i].Size > children[j].Size
	})

	var kept []DiskNode
	var smallSum int64
	var smallCount int
	var extraSum int64
	var extraCount int

	for _, child := range children {
		if child.Size < int64(minSizeBytes) {
			smallSum += child.Size
			smallCount++
			continue
		}
		if len(kept) < maxChildren {
			kept = append(kept, child)
		} else {
			extraSum += child.Size
			extraCount++
		}
	}

	result := kept
	if smallCount > 0 {
		result = append(result, DiskNode{
			Name:  "* (small)",
			Path:  parentPath,
			Size:  smallSum,
			IsDir: false,
		})
	}
	if extraCount > 0 {
		result = append(result, DiskNode{
			Name:  "* (others)",
			Path:  parentPath,
			Size:  extraSum,
			IsDir: false,
		})
	}
	return result
}

// allocatedSize returns the allocated size on disk using stat.Blocks * 512 (POSIX 512-byte blocks).
// Falls back to info.Size() if syscall.Stat_t is unavailable.
func allocatedSize(info os.FileInfo) int64 {
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return info.Size()
	}
	return stat.Blocks * 512
}
