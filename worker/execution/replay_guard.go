package execution

import (
	"container/list"
	"sync"
	"time"
)

type cacheEntry struct {
	requestID string
	expiresAt time.Time
}

// ReplayGuard protects against replaying request_ids using a dual LRU + TTL mechanism.
type ReplayGuard struct {
	mu         sync.Mutex
	maxSize    int
	defaultTTL time.Duration
	items      map[string]*list.Element
	evictList  *list.List
}

// NewReplayGuard creates a new ReplayGuard with max capacity and TTL.
func NewReplayGuard(maxSize int, defaultTTL time.Duration) *ReplayGuard {
	if maxSize <= 0 {
		maxSize = 5000
	}
	if defaultTTL <= 0 {
		defaultTTL = 24 * time.Hour
	}
	return &ReplayGuard{
		maxSize:    maxSize,
		defaultTTL: defaultTTL,
		items:      make(map[string]*list.Element),
		evictList:  list.New(),
	}
}

// IsReplayed checks if requestID was already executed. If not, records it.
func (rg *ReplayGuard) IsReplayed(requestID string, grantExpiresAt time.Time) bool {
	rg.mu.Lock()
	defer rg.mu.Unlock()

	now := time.Now()
	rg.purgeExpired(now)

	if elem, exists := rg.items[requestID]; exists {
		// Element exists in cache
		entry := elem.Value.(*cacheEntry)
		if now.Before(entry.expiresAt) {
			return true // Replayed!
		}
		// Expired entry found, remove it
		rg.removeElement(elem)
	}

	// Calculate TTL
	ttl := rg.defaultTTL
	if !grantExpiresAt.IsZero() && grantExpiresAt.After(now) {
		grantTTL := grantExpiresAt.Sub(now)
		if grantTTL > ttl {
			ttl = grantTTL
		}
	}

	entry := &cacheEntry{
		requestID: requestID,
		expiresAt: now.Add(ttl),
	}

	// Ensure capacity
	if rg.evictList.Len() >= rg.maxSize {
		rg.removeOldest()
	}

	elem := rg.evictList.PushFront(entry)
	rg.items[requestID] = elem
	return false
}

func (rg *ReplayGuard) purgeExpired(now time.Time) {
	for elem := rg.evictList.Back(); elem != nil; {
		prev := elem.Prev()
		entry := elem.Value.(*cacheEntry)
		if now.After(entry.expiresAt) {
			rg.removeElement(elem)
		}
		elem = prev
	}
}

func (rg *ReplayGuard) removeElement(elem *list.Element) {
	rg.evictList.Remove(elem)
	entry := elem.Value.(*cacheEntry)
	delete(rg.items, entry.requestID)
}

func (rg *ReplayGuard) removeOldest() {
	elem := rg.evictList.Back()
	if elem != nil {
		rg.removeElement(elem)
	}
}
