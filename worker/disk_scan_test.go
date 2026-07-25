package main

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func TestDiskScan_IsAllowedPath(t *testing.T) {
	tmpDir := t.TempDir()
	mounts := []string{tmpDir}

	if !isAllowedScanPath(tmpDir, mounts) {
		t.Fatal("expected temp dir to be allowed when in mounts")
	}

	child := filepath.Join(tmpDir, "subdir")
	if err := os.Mkdir(child, 0755); err != nil {
		t.Fatal(err)
	}
	if !isAllowedScanPath(child, mounts) {
		t.Fatal("expected child path to be allowed")
	}
}

func TestDiskScan_RejectsSlash(t *testing.T) {
	if isAllowedScanPath("/", []string{"/data"}) {
		t.Fatal("expected / to be rejected when not in mounts")
	}
}

func TestDiskScan_RejectsEmptyMounts(t *testing.T) {
	if isAllowedScanPath("/any/path", nil) {
		t.Fatal("expected rejection with nil mounts")
	}
	if isAllowedScanPath("/any/path", []string{}) {
		t.Fatal("expected rejection with empty mounts")
	}

	// Also verify handleDiskScan returns the right error
	result := handleDiskScan(context.Background(), Intent{
		Params: map[string]interface{}{
			"mounts": []interface{}{},
		},
	})
	if result.Success {
		t.Fatal("expected failure with empty mounts")
	}
	if result.Error != "path not allowed: no mounts provided" {
		t.Fatalf("unexpected error: %q", result.Error)
	}
}

func TestDiskScan_RejectsSymlinkTraversal(t *testing.T) {
	mounts := []string{"/allowed"}
	symlink := "/tmp/test_symlink_traversal"

	// Clean up if it exists
	defer os.Remove(symlink)

	if err := os.Symlink("/etc/passwd", symlink); err != nil {
		t.Skip("cannot create symlink:", err)
	}
	defer os.Remove(symlink)

	if isAllowedScanPath(symlink, mounts) {
		t.Fatal("expected symlink outside mounts to be rejected")
	}
}

func TestDiskScan_HandlesPermissionDenied(t *testing.T) {
	tmpDir := t.TempDir()

	// Create a readable subdir and an unreadable one
	goodDir := filepath.Join(tmpDir, "accessible")
	badDir := filepath.Join(tmpDir, "forbidden")
	if err := os.Mkdir(goodDir, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(badDir, 0000); err != nil {
		t.Fatal(err)
	}
	defer os.Chmod(badDir, 0755) // cleanup

	// Create a file in the good dir so the scan has something to report
	if err := os.WriteFile(filepath.Join(goodDir, "file.txt"), []byte("hello"), 0644); err != nil {
		t.Fatal(err)
	}

	result := handleDiskScan(context.Background(), Intent{
		Params: map[string]interface{}{
			"path":      tmpDir,
			"mounts":    []interface{}{tmpDir},
			"max_depth": 3,
		},
	})

	if !result.Success {
		t.Fatalf("expected success, got error: %q", result.Error)
	}

	var scan DiskScanResult
	if err := json.Unmarshal([]byte(result.Output), &scan); err != nil {
		t.Fatalf("failed to parse result JSON: %v", err)
	}

	if scan.SkippedPerm == 0 {
		t.Fatal("expected at least one permission-denied skip")
	}
}

func TestDiskScan_AggregationDefault(t *testing.T) {
	tmpDir := t.TempDir()

	// Create 60 tiny files (below default min_size) + 3 large files
	for i := 0; i < 60; i++ {
		name := filepath.Join(tmpDir, "small_"+string(rune('a'+i%26))+".dat")
		if err := os.WriteFile(name, []byte("x"), 0644); err != nil {
			t.Fatal(err)
		}
	}

	// Create 3 large files (above default 10 MB min)
	largeData := bytes.Repeat([]byte("L"), 11*1024*1024) // 11 MB each
	for i := 0; i < 3; i++ {
		name := filepath.Join(tmpDir, "large_"+string(rune('A'+i))+".dat")
		if err := os.WriteFile(name, largeData, 0644); err != nil {
			t.Fatal(err)
		}
	}

	result := handleDiskScan(context.Background(), Intent{
		Params: map[string]interface{}{
			"path":      tmpDir,
			"mounts":    []interface{}{tmpDir},
			"max_depth": 1,
		},
	})

	if !result.Success {
		t.Fatalf("expected success, got error: %q", result.Error)
	}

	var scan DiskScanResult
	if err := json.Unmarshal([]byte(result.Output), &scan); err != nil {
		t.Fatalf("failed to parse result JSON: %v", err)
	}

	// Find the ghost nodes
	var hasSmall, hasOthers bool
	var totalChildren int
	for _, child := range scan.Root.Children {
		if child.Name == "* (small)" {
			hasSmall = true
		}
		if child.Name == "* (others)" {
			hasOthers = true
		}
		totalChildren++
	}

	if !hasSmall {
		t.Fatal("expected '* (small)' ghost node for files below min_size")
	}
	if totalChildren > maxChildrenPerNode+2 { // +2 for ghost nodes
		t.Fatalf("expected at most %d children (including ghosts), got %d", maxChildrenPerNode+2, totalChildren)
	}
	// 3 large files are above min, so 3 real + 1 small ghost = 4 total
	// No "* (others)" ghost since 3 < maxChildrenPerNode
	if hasOthers {
		t.Fatal("did not expect '* (others)' ghost since we have fewer than 50 large files")
	}
}

func TestDiskScan_RespectsTimeout(t *testing.T) {
	tmpDir := t.TempDir()

	// Create a deep tree: 20 levels, 5 dirs per level
	dir := tmpDir
	for i := 0; i < 20; i++ {
		dir = filepath.Join(dir, "level")
		if err := os.Mkdir(dir, 0755); err != nil {
			t.Fatal(err)
		}
	}

	// Use a very short deadline context
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Nanosecond)
	defer cancel()

	// Give it time to expire
	time.Sleep(1 * time.Millisecond)

	result := handleDiskScan(ctx, Intent{
		Params: map[string]interface{}{
			"path":      tmpDir,
			"mounts":    []interface{}{tmpDir},
			"max_depth": 50,
		},
	})

	if result.Success {
		t.Fatal("expected timeout to cause failure")
	}
	if result.Error != "disk scan timed out" {
		t.Fatalf("expected timeout error, got: %q", result.Error)
	}
}

func TestDiskScan_AllocatedSize(t *testing.T) {
	tmpDir := t.TempDir()

	// Create a file with known content
	data := bytes.Repeat([]byte("x"), 8192)
	path := filepath.Join(tmpDir, "sized_file")
	if err := os.WriteFile(path, data, 0644); err != nil {
		t.Fatal(err)
	}

	// Compute expected size: stat.Blocks * stat.Blksize
	info, err := os.Lstat(path)
	if err != nil {
		t.Fatal(err)
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		t.Skip("syscall.Stat_t not available on this platform")
	}
	expectedSize := stat.Blocks * int64(stat.Blksize)

	result := handleDiskScan(context.Background(), Intent{
		Params: map[string]interface{}{
			"path":           tmpDir,
			"mounts":         []interface{}{tmpDir},
			"max_depth":      1,
			"min_size_bytes": 0,
		},
	})

	if !result.Success {
		t.Fatalf("expected success, got error: %q", result.Error)
	}

	var scan DiskScanResult
	if err := json.Unmarshal([]byte(result.Output), &scan); err != nil {
		t.Fatalf("failed to parse result JSON: %v", err)
	}

	// Find the sized_file in root children
	found := false
	for _, child := range scan.Root.Children {
		if child.Name == "sized_file" {
			found = true
			if child.Size != expectedSize {
				t.Fatalf("expected size %d (Blocks=%d * Blksize=%d), got %d",
					expectedSize, stat.Blocks, stat.Blksize, child.Size)
			}
			break
		}
	}
	if !found {
		t.Fatal("sized_file not found in root children")
	}
}

func TestDiskScan_MaxDepthLeaf(t *testing.T) {
	tmpDir := t.TempDir()

	// Create: tmpDir/a/ (depth 1), tmpDir/a/b/ (depth 2)
	inner := filepath.Join(tmpDir, "a", "b")
	if err := os.MkdirAll(inner, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(inner, "deep.txt"), []byte("deep"), 0644); err != nil {
		t.Fatal(err)
	}

	result := handleDiskScan(context.Background(), Intent{
		Params: map[string]interface{}{
			"path":           tmpDir,
			"mounts":         []interface{}{tmpDir},
			"max_depth":      1,
			"min_size_bytes": 0,
		},
	})

	if !result.Success {
		t.Fatalf("expected success, got error: %q", result.Error)
	}

	var scan DiskScanResult
	if err := json.Unmarshal([]byte(result.Output), &scan); err != nil {
		t.Fatalf("failed to parse result JSON: %v", err)
	}

	// At max_depth=1, "a" should be a leaf (IsDir=true, no children)
	if len(scan.Root.Children) == 0 {
		t.Fatal("expected at least one child")
	}
	for _, child := range scan.Root.Children {
		if child.Name == "a" {
			if !child.IsDir {
				t.Fatal("expected 'a' to be a directory")
			}
			if child.Children != nil {
				t.Fatalf("expected 'a' to have no children at max_depth, got %d", len(child.Children))
			}
			return
		}
	}
	t.Fatal("'a' not found in root children")
}

func TestDiskScan_SkipsSymlinks(t *testing.T) {
	tmpDir := t.TempDir()

	// Create a regular file
	if err := os.WriteFile(filepath.Join(tmpDir, "real.txt"), []byte("real"), 0644); err != nil {
		t.Fatal(err)
	}

	// Create a symlink to an out-of-mount target
	if err := os.Symlink("/etc/passwd", filepath.Join(tmpDir, "evil_link")); err != nil {
		t.Fatal(err)
	}

	result := handleDiskScan(context.Background(), Intent{
		Params: map[string]interface{}{
			"path":           tmpDir,
			"mounts":         []interface{}{tmpDir},
			"max_depth":      1,
			"min_size_bytes": 0,
		},
	})

	if !result.Success {
		t.Fatalf("expected success, got error: %q", result.Error)
	}

	var scan DiskScanResult
	if err := json.Unmarshal([]byte(result.Output), &scan); err != nil {
		t.Fatalf("failed to parse result JSON: %v", err)
	}

	for _, child := range scan.Root.Children {
		if child.Name == "evil_link" {
			t.Fatal("symlink should not appear in scan results")
		}
	}

	if len(scan.Root.Children) != 1 {
		t.Fatalf("expected 1 child (real file), got %d", len(scan.Root.Children))
	}
	if scan.Root.Children[0].Name != "real.txt" {
		t.Fatalf("expected child 'real.txt', got %q", scan.Root.Children[0].Name)
	}
}
