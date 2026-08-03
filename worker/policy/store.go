package policy

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/flavio-cbz/Vigile/worker/sys"
)

const (
	DefaultPolicyFilePath = "/etc/vigile/policy.json"
)

// Store manages thread-safe policy state and atomic persistence.
type Store struct {
	mu           sync.RWMutex
	filePath     string
	masterPub    ed25519.PublicKey
	nodeID       string
	activeState  *ActivePolicyState
}

// NewStore initializes a policy store targeting specified filePath.
func NewStore(filePath string, masterPub ed25519.PublicKey, nodeID string) *Store {
	if filePath == "" {
		filePath = DefaultPolicyFilePath
	}
	return &Store{
		filePath:  filePath,
		masterPub: masterPub,
		nodeID:    nodeID,
	}
}

// LoadFromDisk reads and verifies local persisted policy bundle on startup.
func (s *Store) LoadFromDisk() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	data, err := os.ReadFile(s.filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // No initial policy file exists yet
		}
		return fmt.Errorf("read policy file failed: %w", err)
	}

	var bundle PolicyBundle
	if err := json.Unmarshal(data, &bundle); err != nil {
		return fmt.Errorf("unmarshal stored policy failed: %w", err)
	}

	if s.masterPub != nil {
		if err := VerifyPolicyBundle(&bundle, nil, s.masterPub, s.nodeID); err != nil {
			return fmt.Errorf("stored policy failed verification: %w", err)
		}
	}

	hashBytes := sha256.Sum256(data)
	s.activeState = &ActivePolicyState{
		Bundle:     &bundle,
		BundleHash: hex.EncodeToString(hashBytes[:]),
		AppliedAt:  float64(time.Now().Unix()),
		MasterPub:  s.masterPub,
	}

	return nil
}

// UpdatePolicy verifies, persists, and activates a new policy bundle.
func (s *Store) UpdatePolicy(bundle *PolicyBundle) (*ActivePolicyState, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	var currentBundle *PolicyBundle
	if s.activeState != nil {
		currentBundle = s.activeState.Bundle
	}

	if err := VerifyPolicyBundle(bundle, currentBundle, s.masterPub, s.nodeID); err != nil {
		return nil, err
	}

	data, err := json.Marshal(bundle)
	if err != nil {
		return nil, fmt.Errorf("marshal policy bundle failed: %w", err)
	}

	if err := sys.WriteFileAtomic(s.filePath, data, 0600); err != nil {
		return nil, fmt.Errorf("persist policy failed: %w", err)
	}

	hashBytes := sha256.Sum256(data)
	s.activeState = &ActivePolicyState{
		Bundle:     bundle,
		BundleHash: hex.EncodeToString(hashBytes[:]),
		AppliedAt:  float64(time.Now().Unix()),
		MasterPub:  s.masterPub,
	}

	return s.activeState, nil
}

// GetActivePolicy returns a thread-safe copy of the active policy bundle state.
func (s *Store) GetActivePolicy() *ActivePolicyState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.activeState
}
