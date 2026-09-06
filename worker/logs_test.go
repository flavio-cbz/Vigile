package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestIsAllowedLogPathRejectsTraversal(t *testing.T) {
	if isAllowedLogPath("/var/log/../../etc/passwd") {
		t.Fatal("expected traversal outside /var/log to be rejected")
	}
}

func TestIsAllowedLogPathAllowsVarLogChild(t *testing.T) {
	if !isAllowedLogPath("/var/log/syslog") {
		t.Fatal("expected /var/log child file to be allowed")
	}
}

func TestIsAllowedLogPathDockerContainerLogs(t *testing.T) {
	if !isAllowedLogPath("/var/lib/docker/containers/abc123/abc123-json.log") {
		t.Fatal("expected docker container json log to be allowed")
	}
	if isAllowedLogPath("/var/lib/docker/containers_evil/x") {
		t.Fatal("expected docker prefix boundary violation to be rejected")
	}
}

func TestIsAllowedLogPathRejectsSymlink(t *testing.T) {
	tmpDir := t.TempDir()
	symlink := tmpDir + "/evil_link"
	if err := os.Symlink("/etc/passwd", symlink); err != nil {
		t.Skip("cannot create symlink:", err)
	}
	if isAllowedLogPath(symlink) {
		t.Fatal("expected symlink to /etc/passwd to be rejected")
	}
}

func TestTailFileReturnsLastLinesInOrder(t *testing.T) {
	path := filepath.Join(t.TempDir(), "big.log")
	var sb strings.Builder
	const total = 5000
	for i := 0; i < total; i++ {
		fmt.Fprintf(&sb, "line-%04d\n", i)
	}
	if err := os.WriteFile(path, []byte(sb.String()), 0o644); err != nil {
		t.Fatal(err)
	}

	out, err := tailFile(path, 50, maxTailWindow)
	if err != nil {
		t.Fatalf("tailFile failed: %v", err)
	}
	wantLines := make([]string, 0, 50)
	for i := total - 50; i < total; i++ {
		wantLines = append(wantLines, fmt.Sprintf("line-%04d", i))
	}
	want := strings.Join(wantLines, "\n")
	if out != want {
		t.Fatalf("unexpected tail output:\n got: %q\nwant: %q", out, want)
	}
}

// TestTailFileLargeFileOver10MB is the regression test for the user bug: a
// 16511652-byte file was rejected by the old whole-file read + 10 MB cap even
// though only 50 lines were requested.
func TestTailFileLargeFileOver10MB(t *testing.T) {
	path := filepath.Join(t.TempDir(), "huge.log")
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	const total = 150000
	for i := 0; i < total; i++ {
		if _, err := fmt.Fprintf(f, "line-%06d-%s\n", i, strings.Repeat("x", 64)); err != nil {
			t.Fatal(err)
		}
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Size() <= 10*1024*1024 {
		t.Fatalf("test file too small: %d bytes", info.Size())
	}

	out, err := tailFile(path, 50, maxTailWindow)
	if err != nil {
		t.Fatalf("tailFile failed on %d-byte file: %v", info.Size(), err)
	}
	if strings.Contains(out, tailTruncatedMarker) {
		t.Fatalf("unexpected truncation marker for 50 lines of a %d-byte file", info.Size())
	}
	wantLines := make([]string, 0, 50)
	for i := total - 50; i < total; i++ {
		wantLines = append(wantLines, fmt.Sprintf("line-%06d-%s", i, strings.Repeat("x", 64)))
	}
	want := strings.Join(wantLines, "\n")
	if out != want {
		t.Fatalf("unexpected tail output:\n got: %q\nwant: %q", out, want)
	}
}

func TestTailFileEdgeCases(t *testing.T) {
	dir := t.TempDir()

	// File without trailing newline.
	noNL := filepath.Join(dir, "nonl.log")
	if err := os.WriteFile(noNL, []byte("one\ntwo\nthree"), 0o644); err != nil {
		t.Fatal(err)
	}
	out, err := tailFile(noNL, 2, maxTailWindow)
	if err != nil {
		t.Fatal(err)
	}
	if out != "two\nthree" {
		t.Fatalf("no-trailing-newline: got %q", out)
	}

	// \r\n line endings.
	crlf := filepath.Join(dir, "crlf.log")
	if err := os.WriteFile(crlf, []byte("one\r\ntwo\r\nthree\r\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	out, err = tailFile(crlf, 2, maxTailWindow)
	if err != nil {
		t.Fatal(err)
	}
	if out != "two\nthree" {
		t.Fatalf("crlf endings: got %q", out)
	}

	// Empty file.
	empty := filepath.Join(dir, "empty.log")
	if err := os.WriteFile(empty, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	out, err = tailFile(empty, 50, maxTailWindow)
	if err != nil {
		t.Fatal(err)
	}
	if out != "" {
		t.Fatalf("empty file: got %q", out)
	}
}

func TestTailFileMoreLinesThanFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "small.log")
	if err := os.WriteFile(path, []byte("a\nb\nc\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	out, err := tailFile(path, 100, maxTailWindow)
	if err != nil {
		t.Fatal(err)
	}
	if out != "a\nb\nc" {
		t.Fatalf("got %q", out)
	}
}

func TestTailFileWindowCapMarker(t *testing.T) {
	path := filepath.Join(t.TempDir(), "huge-line.log")
	// One giant line (5 MB) followed by a short final line.
	data := append([]byte(strings.Repeat("x", 5*1024*1024)), []byte("\nlast\n")...)
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
	out, err := tailFile(path, 10, 1024*1024)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(out, tailTruncatedMarker) {
		t.Fatalf("expected truncation marker, got %q", out)
	}
	if !strings.HasSuffix(out, "last") {
		t.Fatalf("expected final line, got %q", out)
	}
}

func TestReadLogFileMissingFile(t *testing.T) {
	res := readLogFile(filepath.Join(t.TempDir(), "nope.log"), 50)
	if res.Success {
		t.Fatal("expected failure")
	}
	if !strings.Contains(res.Error, "stat failed") {
		t.Fatalf("expected 'stat failed' error, got %q", res.Error)
	}
}

func TestListLogFilesDepthSymlinkJournalAndSort(t *testing.T) {
	root := t.TempDir()
	mkfile := func(rel string, mtime time.Time) {
		p := filepath.Join(root, rel)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte("data"), 0o644); err != nil {
			t.Fatal(err)
		}
		if err := os.Chtimes(p, mtime, mtime); err != nil {
			t.Fatal(err)
		}
	}

	now := time.Now()
	mkfile("a.log", now.Add(-3*time.Hour))                // depth 0
	mkfile("d1/b.log", now.Add(-2*time.Hour))             // depth 1
	mkfile("d1/d2/c.log", now.Add(-1*time.Hour))          // depth 2
	mkfile("d1/d2/d3/d.log", now)                         // depth 3 → included
	mkfile("d1/d2/d3/d4/e.log", now.Add(-30*time.Minute)) // depth 4 → excluded
	mkfile("d1/x.journal", now.Add(-4*time.Hour))         // journal → excluded
	if err := os.Symlink(filepath.Join(root, "a.log"), filepath.Join(root, "link.log")); err != nil {
		t.Skip("cannot create symlink:", err)
	}

	entries, truncated, err := listLogFiles(root, 3, 500)
	if err != nil {
		t.Fatal(err)
	}
	if truncated {
		t.Fatal("expected truncated=false")
	}
	if len(entries) != 4 {
		t.Fatalf("expected 4 entries, got %d: %+v", len(entries), entries)
	}
	// Sorted by mtime descending: d.log (now), c.log, b.log, a.log.
	wantOrder := []string{"d.log", "c.log", "b.log", "a.log"}
	for i, want := range wantOrder {
		if filepath.Base(entries[i].Path) != want {
			t.Fatalf("entry %d: got %s, want %s (order %+v)", i, filepath.Base(entries[i].Path), want, entries)
		}
	}
	for _, e := range entries {
		if strings.HasSuffix(e.Path, ".journal") {
			t.Fatalf("journal file included: %s", e.Path)
		}
		if strings.HasSuffix(e.Path, "link.log") {
			t.Fatalf("symlink included: %s", e.Path)
		}
	}
}

func TestListLogFilesFromRootsSkipsMissingAndMerges(t *testing.T) {
	realRoot := t.TempDir()
	for i := 0; i < 3; i++ {
		p := filepath.Join(realRoot, fmt.Sprintf("f%d.log", i))
		if err := os.WriteFile(p, []byte("data"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	missingRoot := filepath.Join(t.TempDir(), "does-not-exist")

	entries, truncated, err := listLogFilesFromRoots(
		context.Background(), []string{realRoot, missingRoot}, 3, 500,
	)
	if err != nil {
		t.Fatal(err)
	}
	if truncated {
		t.Fatal("expected truncated=false")
	}
	if len(entries) != 3 {
		t.Fatalf("expected 3 entries from real root, got %d: %+v", len(entries), entries)
	}
}

func TestListLogFilesTruncated(t *testing.T) {
	root := t.TempDir()
	for i := 0; i < 5; i++ {
		p := filepath.Join(root, fmt.Sprintf("f%d.log", i))
		if err := os.WriteFile(p, []byte("data"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	entries, truncated, err := listLogFiles(root, 3, 3)
	if err != nil {
		t.Fatal(err)
	}
	if !truncated {
		t.Fatal("expected truncated=true")
	}
	if len(entries) != 3 {
		t.Fatalf("expected 3 entries, got %d", len(entries))
	}
}

// TestHandleListLogFilesJSONContract verifies the fixed output contract the
// Master side parses: a JSON object with "files" and "truncated" keys.
func TestHandleListLogFilesJSONContract(t *testing.T) {
	res := handleListLogFiles(context.Background(), Intent{})
	if !res.Success {
		t.Fatalf("expected success, got error: %s", res.Error)
	}
	var payload struct {
		Files     []LogFileEntry `json:"files"`
		Truncated bool           `json:"truncated"`
	}
	if err := json.Unmarshal([]byte(res.Output), &payload); err != nil {
		t.Fatalf("output is not valid JSON: %v\noutput: %s", err, res.Output)
	}
	if payload.Files == nil {
		t.Fatal("expected non-nil files array")
	}
	for _, e := range payload.Files {
		if e.Path == "" {
			t.Fatal("entry with empty path")
		}
	}
}
