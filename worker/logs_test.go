package main

import (
	"os"
	"testing"
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
