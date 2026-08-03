package capabilities

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// FileMeta describes file metadata without content.
type FileMeta struct {
	Path     string    `json:"path"`
	SizeBytes int64     `json:"size_bytes"`
	ModTime  time.Time `json:"mod_time"`
	IsDir    bool      `json:"is_dir"`
}

// DirectoryUsageResult holds output for GET_DIRECTORY_USAGE.
type DirectoryUsageResult struct {
	RootPath     string     `json:"root_path"`
	TotalSize    int64      `json:"total_size_bytes"`
	FileCount    int64      `json:"file_count"`
	DirCount     int64      `json:"dir_count"`
	DepthReached int        `json:"depth_reached"`
	Truncated    bool       `json:"truncated"`
	LargeFiles   []FileMeta `json:"large_files,omitempty"`
}

// ForbiddenSystemPaths lists OS pseudo-filesystems that are strictly forbidden.
var ForbiddenSystemPaths = []string{
	"/proc",
	"/sys",
	"/dev",
	"/run",
}

// ValidateAndSanitizePath enforces symlink safety and path containment:
// Sequence: filepath.EvalSymlinks(path) -> filepath.Clean(resolved) -> strings.HasPrefix(resolved, allowedRoot)
func ValidateAndSanitizePath(requestedPath, allowedRoot string) (string, error) {
	if requestedPath == "" {
		return "", fmt.Errorf("path cannot be empty")
	}

	cleanReq := filepath.Clean(requestedPath)
	if !filepath.IsAbs(cleanReq) {
		return "", fmt.Errorf("path %q must be absolute", requestedPath)
	}

	for _, forbidden := range ForbiddenSystemPaths {
		if cleanReq == forbidden || strings.HasPrefix(cleanReq, forbidden+"/") {
			return "", fmt.Errorf("access to pseudo-filesystem %q is forbidden", forbidden)
		}
	}

	// Resolve symlinks
	resolved, err := filepath.EvalSymlinks(cleanReq)
	if err != nil {
		if os.IsNotExist(err) {
			resolved = cleanReq // File might not exist yet, clean is sufficient
		} else {
			return "", fmt.Errorf("eval symlinks failed: %w", err)
		}
	}
	resolved = filepath.Clean(resolved)

	cleanRoot := filepath.Clean(allowedRoot)
	resolvedRoot, err := filepath.EvalSymlinks(cleanRoot)
	if err == nil {
		cleanRoot = filepath.Clean(resolvedRoot)
	}

	if cleanRoot != "*" && cleanRoot != "/" {
		if resolved != cleanRoot && !strings.HasPrefix(resolved, cleanRoot+"/") {
			return "", fmt.Errorf("path %q traverses outside allowed root %q", resolved, cleanRoot)
		}
	}

	return resolved, nil
}

// HandleGetDirectoryUsage scans directory recursively up to budget limits.
func HandleGetDirectoryUsage(rootPath string, allowedRoot string, budget BudgetLimits) (DirectoryUsageResult, error) {
	sanitized, err := ValidateAndSanitizePath(rootPath, allowedRoot)
	if err != nil {
		return DirectoryUsageResult{}, err
	}

	res := DirectoryUsageResult{
		RootPath: sanitized,
	}

	start := time.Now()
	var totalEntries int

	err = filepath.Walk(sanitized, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Skip unreadable paths
		}

		if time.Since(start) > budget.MaxTimeout {
			res.Truncated = true
			return filepath.SkipDir
		}

		rel, err := filepath.Rel(sanitized, path)
		if err == nil {
			depth := strings.Count(rel, string(os.PathSeparator))
			if depth > budget.MaxDepth {
				if info.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}
			if depth > res.DepthReached {
				res.DepthReached = depth
			}
		}

		totalEntries++
		if budget.MaxEntries > 0 && totalEntries > budget.MaxEntries {
			res.Truncated = true
			return filepath.SkipDir
		}

		if info.IsDir() {
			res.DirCount++
		} else {
			res.FileCount++
			res.TotalSize += info.Size()
		}

		return nil
	})

	return res, err
}
