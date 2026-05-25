package poller

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"wps-caldav-proxy/internal/cache"
	"wps-caldav-proxy/internal/wpsclient"
)

// Mock wps client that we can configure for tests
type mockWpsClient struct {
	events    []wpsclient.EventInfo
	err       error
	calledGet bool
}

func (m *mockWpsClient) FetchEvents() ([]wpsclient.EventInfo, error) {
	m.calledGet = true
	if m.err != nil {
		return nil, m.err
	}
	return m.events, nil
}

func (m *mockWpsClient) Discover() error {
	return nil
}

func TestPollerFailSafe(t *testing.T) {
	// Create mock cache
	tmpDir, err := os.MkdirTemp("", "poller_test_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "test.db")
	c, err := cache.New(dbPath)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer c.Close()

	// Seed cache with 1 existing event
	_, _ = c.MergeEvents([]*cache.Event{
		{
			UID:      "existing-event",
			Href:     "/caldav/u/caldav/default/existing-event.ics",
			ETag:     "etag1",
			ICalData: "BEGIN:VCALENDAR\nEND:VCALENDAR",
		},
	})

	// 1. Test case: WPS client returns an error (network down)
	mockClient := &mockWpsClient{
		err: errors.New("WPS server timeout"),
	}

	p := New(mockClient, c, 60)
	err = p.SyncOnce()
	if err == nil {
		t.Error("expected error during sync once when WPS is unreachable, got nil")
	}

	// Verify that the cache still contains the seeded event (keep-stale)
	events, _ := c.GetAllEvents()
	if len(events) != 1 {
		t.Errorf("expected cache to keep 1 event, got %d", len(events))
	}

	// 2. Test case: WPS client returns 0 events (accidental wipe protection)
	mockClient2 := &mockWpsClient{
		events: []wpsclient.EventInfo{}, // empty calendar!
	}

	p2 := New(mockClient2, c, 60)
	err = p2.SyncOnce()
	if err == nil {
		t.Error("expected error or warning when WPS returns empty calendar, got nil")
	}

	// Verify cache was NOT wiped!
	events, _ = c.GetAllEvents()
	if len(events) != 1 {
		t.Errorf("FAIL-SAFE VOIDED: Cache was wiped! Expected 1 event, got %d", len(events))
	} else {
		t.Log("SUCCESS: Fail-safe protection blocked empty calendar merge and preserved cache!")
	}

	// 3. Test case: Normal healthy sync
	mockClient3 := &mockWpsClient{
		events: []wpsclient.EventInfo{
			{
				UID:      "new-event-1",
				Href:     "/caldav/u/caldav/default/new-event-1.ics",
				ETag:     "etag2",
				ICalData: "BEGIN:VCALENDAR\nEND:VCALENDAR",
			},
		},
	}

	p3 := New(mockClient3, c, 60)
	err = p3.SyncOnce()
	if err != nil {
		t.Fatalf("expected successful sync, got error: %v", err)
	}

	// Verify cache was updated to the new set
	events, _ = c.GetAllEvents()
	if len(events) != 1 || events[0].UID != "new-event-1" {
		t.Errorf("expected cache to have 1 new event, got %+v", events)
	}
}
