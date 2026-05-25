package caldavserver

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"wps-caldav-proxy/internal/cache"
)

func TestReportCompliance(t *testing.T) {
	// Create mock cache
	tmpDir, err := os.MkdirTemp("", "caldavserver_report_*")
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

	// Seed cache with events to test time range
	// Event 1: DTSTART:20260525T100000Z, DTEND:20260525T110000Z
	_, _ = c.MergeEvents([]*cache.Event{
		{
			UID:       "event-1",
			Href:      "/caldav/u/caldav/default/event-1.ics",
			ETag:      "etag-1",
			ICalData:  "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:event-1\nDTSTART:20260525T100000Z\nDTEND:20260525T110000Z\nEND:VEVENT\nEND:VCALENDAR",
			StartTime: 1779703200,
			EndTime:   1779706800,
		},
		{
			UID:       "event-2",
			Href:      "/caldav/u/caldav/default/event-2.ics",
			ETag:      "etag-2",
			ICalData:  "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:event-2\nDTSTART:20260525T150000Z\nDTEND:20260525T160000Z\nEND:VEVENT\nEND:VCALENDAR",
			StartTime: 1779721200,
			EndTime:   1779724800,
		},
	})

	server := New(c, "caldav", "proxypass", "/caldav")

	// 1. Test calendar-query with time-range overlap matching ONLY event-1
	queryXML := `<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="20260525T093000Z" end="20260525T103000Z"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>`

	wQuery := httptest.NewRecorder()
	reqQuery := httptest.NewRequest("REPORT", "/caldav/u/caldav/default", strings.NewReader(queryXML))
	reqQuery.SetBasicAuth("caldav", "proxypass")
	server.ServeHTTP(wQuery, reqQuery)

	if wQuery.Code != http.StatusMultiStatus {
		t.Errorf("expected REPORT status 207, got %d", wQuery.Code)
	}

	bodyQuery, _ := io.ReadAll(wQuery.Body)
	respQueryStr := string(bodyQuery)

	if !strings.Contains(respQueryStr, "event-1.ics") {
		t.Error("expected event-1 in report query response")
	}
	if strings.Contains(respQueryStr, "event-2.ics") {
		t.Error("did NOT expect event-2 in report query response")
	}

	// 2. Test sync-collection with revision = 0 (returns all changes)
	syncXML := `<?xml version="1.0" encoding="utf-8" ?>
<D:sync-collection xmlns:D="DAV:">
  <D:sync-token>0</D:sync-token>
  <D:prop>
    <D:getetag/>
  </D:prop>
</D:sync-collection>`

	wSync := httptest.NewRecorder()
	reqSync := httptest.NewRequest("REPORT", "/caldav/u/caldav/default", strings.NewReader(syncXML))
	reqSync.SetBasicAuth("caldav", "proxypass")
	server.ServeHTTP(wSync, reqSync)

	if wSync.Code != http.StatusMultiStatus {
		t.Errorf("expected REPORT status 207, got %d", wSync.Code)
	}

	bodySync, _ := io.ReadAll(wSync.Body)
	respSyncStr := string(bodySync)

	if !strings.Contains(respSyncStr, "<D:sync-token>1</D:sync-token>") {
		t.Errorf("expected sync-token 1 in response, got XML:\n%s", respSyncStr)
	}

	if !strings.Contains(respSyncStr, "event-1.ics") || !strings.Contains(respSyncStr, "event-2.ics") {
		t.Error("expected all seeded events in sync-collection from revision 0")
	}
}

func TestCalendarMultiget(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "caldavserver_multiget_*")
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

	_, _ = c.MergeEvents([]*cache.Event{
		{
			UID:      "event-1",
			Href:     "/caldav/u/caldav/default/event-1.ics",
			ETag:     "etag-1",
			ICalData: "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:event-1\nSUMMARY:Test Multiget\nEND:VEVENT\nEND:VCALENDAR",
		},
	})

	server := New(c, "caldav", "proxypass", "/caldav")

	multigetXML := `<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-multiget xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <D:href>/caldav/u/caldav/default/event-1.ics</D:href>
  <D:href>/caldav/u/caldav/default/event-2.ics</D:href>
</C:calendar-multiget>`

	w := httptest.NewRecorder()
	req := httptest.NewRequest("REPORT", "/caldav/u/caldav/default", strings.NewReader(multigetXML))
	req.SetBasicAuth("caldav", "proxypass")
	server.ServeHTTP(w, req)

	if w.Code != http.StatusMultiStatus {
		t.Errorf("expected REPORT status 207, got %d", w.Code)
	}

	body, _ := io.ReadAll(w.Body)
	respStr := string(body)

	if !strings.Contains(respStr, "event-1.ics") || !strings.Contains(respStr, "HTTP/1.1 200 OK") {
		t.Errorf("expected event-1 to be found with 200 OK, got XML:\n%s", respStr)
	}
	if !strings.Contains(respStr, "Test Multiget") {
		t.Errorf("expected event-1's calendar data in response, got XML:\n%s", respStr)
	}

	if !strings.Contains(respStr, "event-2.ics") || !strings.Contains(respStr, "HTTP/1.1 404 Not Found") {
		t.Errorf("expected event-2 to return 404 Not Found, got XML:\n%s", respStr)
	}
}

