package capabilities

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestValidateAndSanitizePath(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "vigile-disk-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	subDir := filepath.Join(tmpDir, "logs")
	if err := os.MkdirAll(subDir, 0755); err != nil {
		t.Fatalf("failed to create sub dir: %v", err)
	}

	secretDir := filepath.Join(tmpDir, "secret")
	if err := os.MkdirAll(secretDir, 0700); err != nil {
		t.Fatalf("failed to create secret dir: %v", err)
	}

	// Create symlink inside logs pointing to secret
	symlinkPath := filepath.Join(subDir, "link_to_secret")
	if err := os.Symlink(secretDir, symlinkPath); err != nil {
		t.Fatalf("failed to create symlink: %v", err)
	}

	t.Run("Valid path under allowed root", func(t *testing.T) {
		expected, _ := filepath.EvalSymlinks(subDir)
		expected = filepath.Clean(expected)
		got, err := ValidateAndSanitizePath(subDir, subDir)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != expected {
			t.Errorf("got %q, want %q", got, expected)
		}
	})

	t.Run("Symlink escape attempt rejected", func(t *testing.T) {
		_, err := ValidateAndSanitizePath(symlinkPath, subDir)
		if err == nil {
			t.Fatalf("expected error for symlink escape attempt, got nil")
		}
		if !strings.Contains(err.Error(), "traverses outside allowed root") {
			t.Errorf("unexpected error message: %v", err)
		}
	})

	t.Run("Forbidden pseudo-filesystem rejected", func(t *testing.T) {
		_, err := ValidateAndSanitizePath("/proc/sys", "/")
		if err == nil {
			t.Fatalf("expected error for /proc, got nil")
		}
	})
}
