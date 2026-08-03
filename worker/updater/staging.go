package updater

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
)

const (
	DefaultStagingDir = "/var/lib/vigile/staging"
	FallbackStagingDir = "/tmp/vigile-staging"
)

// StagingResult describes a successfully staged worker binary.
type StagingResult struct {
	StagedPath string
	SHA256     string
	SizeBytes  int64
}

// StageRelease Binary downloads the binary from manifest.URL, checks SHA256 and SizeBytes, and writes to staging path.
func StageRelease(ctx context.Context, client *http.Client, baseURL string, manifest *ReleaseManifest) (*StagingResult, error) {
	if manifest == nil {
		return nil, fmt.Errorf("manifest is nil")
	}

	stagingDir := DefaultStagingDir
	if err := os.MkdirAll(stagingDir, 0755); err != nil {
		stagingDir = FallbackStagingDir
		if err := os.MkdirAll(stagingDir, 0755); err != nil {
			return nil, fmt.Errorf("failed to create staging directory: %w", err)
		}
	}

	stagedPath := filepath.Join(stagingDir, fmt.Sprintf("worker-%s.tmp", manifest.WorkerVersion))
	defer func() {
		// Clean up temporary file on failure
	}()

	downloadURL := manifest.URL
	if !filepath.IsAbs(downloadURL) && !hasScheme(downloadURL) {
		downloadURL = baseURL + "/" + manifest.URL
	}

	req, err := http.NewRequestWithContext(ctx, "GET", downloadURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create download request: %w", err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to download release binary: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("download returned status %d", resp.StatusCode)
	}

	tmpFile, err := os.OpenFile(stagedPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0755)
	if err != nil {
		return nil, fmt.Errorf("failed to open staging file: %w", err)
	}

	hasher := sha256.New()
	writer := io.MultiWriter(tmpFile, hasher)

	written, err := io.Copy(writer, resp.Body)
	_ = tmpFile.Close()

	if err != nil {
		_ = os.Remove(stagedPath)
		return nil, fmt.Errorf("failed during binary download copy: %w", err)
	}

	if manifest.SizeBytes > 0 && written != manifest.SizeBytes {
		_ = os.Remove(stagedPath)
		return nil, fmt.Errorf("size mismatch: expected %d bytes, got %d", manifest.SizeBytes, written)
	}

	actualHash := hex.EncodeToString(hasher.Sum(nil))
	if manifest.SHA256 != "" && actualHash != manifest.SHA256 {
		_ = os.Remove(stagedPath)
		return nil, fmt.Errorf("SHA256 checksum mismatch: expected %s, got %s", manifest.SHA256, actualHash)
	}

	return &StagingResult{
		StagedPath: stagedPath,
		SHA256:     actualHash,
		SizeBytes:  written,
	}, nil
}

func hasScheme(url string) bool {
	return len(url) > 7 && (url[:7] == "http://" || url[:8] == "https://")
}
