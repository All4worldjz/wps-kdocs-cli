package cache

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCacheOperations(t *testing.T) {
	// Create a temp directory for sqlite db
	tmpDir, err := os.MkdirTemp("", "cache_test_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "test.db")
	c, err := New(dbPath)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer c.Close()

	// Verify schema is initialized
	revision, err := c.GetRevision()
	if err != nil {
		t.Fatalf("failed to get initial revision: %v", err)
	}
	if revision != 0 {
		t.Errorf("expected initial revision to be 0, got %d", revision)
	}
	ctag, err := c.GetCtag()
	if err != nil {
		t.Fatalf("failed to get initial ctag: %v", err)
	}
	if ctag != "" {
		t.Errorf("expected initial ctag to be empty, got %q", ctag)
	}

	// Define test events
	event1 := &Event{
		UID:       "uid1",
		Href:      "/caldav/u/caldav/default/event1.ics",
		ETag:      `"etag1"`,
		ICalData:  "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:uid1\nSUMMARY:Meeting 1\nDTSTART:20260525T100000Z\nDTEND:20260525T110000Z\nEND:VEVENT\nEND:VCALENDAR",
		StartTime: 1779703200, // 2026-05-25 10:00:00 UTC
		EndTime:   1779706800, // 2026-05-25 11:00:00 UTC
		IsAllDay:  false,
	}

	event2 := &Event{
		UID:       "uid2",
		Href:      "/caldav/u/caldav/default/event2.ics",
		ETag:      `"etag2"`,
		ICalData:  "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:uid2\nSUMMARY:Meeting 2\nDTSTART:20260525T120000Z\nDTEND:20260525T130000Z\nEND:VEVENT\nEND:VCALENDAR",
		StartTime: 1779710400, // 2026-05-25 12:00:00 UTC
		EndTime:   1779714000, // 2026-05-25 13:00:00 UTC
		IsAllDay:  false,
	}

	// Merge events (Insert phase)
	remoteEvents := []*Event{event1, event2}
	stats, err := c.MergeEvents(remoteEvents)
	if err != nil {
		t.Fatalf("failed to merge events (insert): %v", err)
	}
	if stats.Created != 2 || stats.Updated != 0 || stats.Deleted != 0 {
		t.Errorf("expected 2 created, got %+v", stats)
	}

	// Verify revision incremented
	newRev, err := c.GetRevision()
	if err != nil {
		t.Fatalf("failed to get revision: %v", err)
	}
	if newRev != 1 {
		t.Errorf("expected revision to be 1, got %d", newRev)
	}

	// Verify ctag changed
	newCtag, err := c.GetCtag()
	if err != nil {
		t.Fatalf("failed to get ctag: %v", err)
	}
	if newCtag == ctag {
		t.Error("expected ctag to change after inserts")
	}

	// Verify we can fetch the events
	events, err := c.GetAllEvents()
	if err != nil {
		t.Fatalf("failed to get all events: %v", err)
	}
	if len(events) != 2 {
		t.Errorf("expected 2 events in db, got %d", len(events))
	}

	// Get events by time-range
	rangeEvents, err := c.GetEventsInTimeRange(1779701400, 1779708600) // matches event1 but not event2
	if err != nil {
		t.Fatalf("failed to query time-range: %v", err)
	}
	if len(rangeEvents) != 1 {
		t.Errorf("expected 1 event in time range, got %d", len(rangeEvents))
	}
	if rangeEvents[0].UID != "uid1" {
		t.Errorf("expected event1, got %s", rangeEvents[0].UID)
	}

	// Merge again with modifications and deletion (Update & Delete phase)
	event1Mod := &Event{
		UID:       "uid1",
		Href:      "/caldav/u/caldav/default/event1.ics",
		ETag:      `"etag1-updated"`,
		ICalData:  "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:uid1\nSUMMARY:Meeting 1 Updated\nDTSTART:20260525T100000Z\nDTEND:20260525T110000Z\nEND:VEVENT\nEND:VCALENDAR",
		StartTime: 1779703200,
		EndTime:   1779706800,
		IsAllDay:  false,
	}
	// We leave out event2 to simulate its deletion
	remoteEventsMod := []*Event{event1Mod}
	statsMod, err := c.MergeEvents(remoteEventsMod)
	if err != nil {
		t.Fatalf("failed to merge events (update/delete): %v", err)
	}
	if statsMod.Created != 0 || statsMod.Updated != 1 || statsMod.Deleted != 1 {
		t.Errorf("expected 1 updated and 1 deleted, got %+v", statsMod)
	}

	// Revision should be 2
	rev2, err := c.GetRevision()
	if err != nil {
		t.Fatalf("failed to get revision: %v", err)
	}
	if rev2 != 2 {
		t.Errorf("expected revision to be 2, got %d", rev2)
	}

	// Verify change log contains the records since revision 0
	changes, err := c.GetChangesSince(0)
	if err != nil {
		t.Fatalf("failed to get changes since 0: %v", err)
	}
	if len(changes) != 4 { // revision 1: 2 inserts, revision 2: 1 update, 1 delete
		t.Errorf("expected 4 changes in log since 0, got %d", len(changes))
	}

	// Check changes since revision 1 (only includes revision 2 changes)
	changesSince1, err := c.GetChangesSince(1)
	if err != nil {
		t.Fatalf("failed to get changes since 1: %v", err)
	}
	if len(changesSince1) != 2 {
		t.Errorf("expected 2 changes since revision 1, got %d", len(changesSince1))
	}
}

func TestTimeRangeParsing(t *testing.T) {
	// Tests standard VCALENDAR time range parsing helper (if any)
	t.Log("Time range parsing test placeholder")
}
