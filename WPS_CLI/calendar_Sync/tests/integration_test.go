package tests

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"testing"

	"wps-caldav-proxy/internal/cache"
	"wps-caldav-proxy/internal/caldavserver"
	"wps-caldav-proxy/internal/poller"
	"wps-caldav-proxy/internal/wpsclient"
)

// Dynamic Mock WPS CalDAV Server State
type mockWpsServer struct {
	mu     sync.Mutex
	events map[string]wpsclient.EventInfo
}

func (m *mockWpsServer) setEvent(ev wpsclient.EventInfo) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events[ev.UID] = ev
}

func (m *mockWpsServer) deleteEvent(uid string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.events, uid)
}

func TestE2EClientSimulationAndRealtimeSync(t *testing.T) {
	// Initialize dynamic Mock WPS Server state
	mockWps := &mockWpsServer{
		events: make(map[string]wpsclient.EventInfo),
	}

	// Seed event-1 in Mock WPS
	mockWps.setEvent(wpsclient.EventInfo{
		UID:      "event-1",
		Href:     "/u/u123/default/event-1.ics",
		ETag:     "etag-v1",
		ICalData: "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:event-1\nSUMMARY:Initial Sync Event\nDTSTART:20260525T100000Z\nDTEND:20260525T110000Z\nEND:VEVENT\nEND:VCALENDAR",
	})

	// Let's write the Mock WPS Http Server properly
	wpsServerHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case "PROPFIND":
			if r.URL.Path == "/" || r.URL.Path == "/caldav" {
				w.Header().Set("Content-Type", "text/xml; charset=utf-8")
				w.WriteHeader(http.StatusMultiStatus)
				w.Write([]byte(`<?xml version="1.0" encoding="utf-8"?>
<multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <response>
    <href>/</href>
    <propstat>
      <prop>
        <current-user-principal><href>/u/u123/</href></current-user-principal>
        <C:calendar-home-set><href>/u/u123/</href></C:calendar-home-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
  </response>
</multistatus>`))
				return
			}
			if r.URL.Path == "/u/u123/" || r.URL.Path == "/u/u123" {
				w.Header().Set("Content-Type", "text/xml; charset=utf-8")
				w.WriteHeader(http.StatusMultiStatus)
				w.Write([]byte(`<?xml version="1.0" encoding="utf-8"?>
<multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <response>
    <href>/u/u123/</href>
    <propstat>
      <prop>
        <resourcetype><collection/></resourcetype>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
  </response>
  <response>
    <href>/u/u123/default/</href>
    <propstat>
      <prop>
        <displayname>WPS Calendar</displayname>
        <C:calendar-description>My WPS Sync Calendar</C:calendar-description>
        <resourcetype><collection/><C:calendar/></resourcetype>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
  </response>
</multistatus>`))
				return
			}
		case "REPORT":
			if strings.Contains(r.URL.Path, "/u/u123/default") {
				w.Header().Set("Content-Type", "text/xml; charset=utf-8")
				w.WriteHeader(http.StatusMultiStatus)

				mockWps.mu.Lock()
				var xmlOutput strings.Builder
				xmlOutput.WriteString(`<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
`)
				for _, ev := range mockWps.events {
					xmlOutput.WriteString(fmt.Sprintf(`  <D:response>
    <D:href>%s</D:href>
    <D:propstat>
      <D:prop>
        <D:getetag>"%s"</D:getetag>
        <C:calendar-data>%s</C:calendar-data>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
`, ev.Href, ev.ETag, ev.ICalData))
				}
				xmlOutput.WriteString("</D:multistatus>")
				mockWps.mu.Unlock()

				w.Write([]byte(xmlOutput.String()))
				return
			}
		}
		w.WriteHeader(http.StatusNotFound)
	})

	mockWpsHttpServer := httptest.NewServer(wpsServerHandler)
	defer mockWpsHttpServer.Close()

	// 1. Setup local cache on temp DB file
	tmpDir, err := os.MkdirTemp("", "integration_test_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "cache.db")
	c, err := cache.New(dbPath)
	if err != nil {
		t.Fatalf("failed to open cache db: %v", err)
	}
	defer c.Close()

	// 2. Setup WPS client pointing to Mock WPS HTTP server
	wpsClient := wpsclient.New(mockWpsHttpServer.URL, "wpsuser", "wpspass")

	// Verify discovery
	if err := wpsClient.Discover(); err != nil {
		t.Fatalf("WPS discovery failed: %v", err)
	}
	if wpsClient.CalendarURL() != "/u/u123/default/" {
		t.Errorf("expected calendar URL /u/u123/default/, got %s", wpsClient.CalendarURL())
	}

	// 3. Setup Poller and warm cache (SyncOnce)
	p := poller.New(wpsClient, c, 60)
	if err := p.SyncOnce(); err != nil {
		t.Fatalf("poller first sync failed: %v", err)
	}

	// Assert cache was successfully seeded with event-1
	events, err := c.GetAllEvents()
	if err != nil || len(events) != 1 {
		t.Fatalf("expected 1 event in local cache, got %d, err: %v", len(events), err)
	}
	if events[0].UID != "event-1" {
		t.Errorf("expected seeded event-1, got %s", events[0].UID)
	}

	// 4. Setup Proxy server (speaks Basic Auth, standard WebDAV compliance)
	proxyServer := caldavserver.New(c, "caldav", "proxypass", "/caldav")
	proxyHttpServer := httptest.NewServer(proxyServer)
	defer proxyHttpServer.Close()

	client := &http.Client{}

	// Helper to send HTTP requests to Proxy
	sendRequest := func(method, path, body string, headers map[string]string) (int, string) {
		var reqBody io.Reader
		if body != "" {
			reqBody = strings.NewReader(body)
		}
		req, _ := http.NewRequest(method, proxyHttpServer.URL+path, reqBody)
		req.SetBasicAuth("caldav", "proxypass")
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		resp, err := client.Do(req)
		if err != nil {
			t.Fatalf("request to proxy %s %s failed: %v", method, path, err)
		}
		defer resp.Body.Close()
		respBody, _ := io.ReadAll(resp.Body)
		return resp.StatusCode, string(respBody)
	}

	// -------------------------------------------------------------
	// SIMULATE macOS CLIENT FLOW
	// -------------------------------------------------------------
	t.Run("macOS Client Simulation Flow", func(t *testing.T) {
		// Step A: Handshake OPTIONS
		status, _ := sendRequest("OPTIONS", "/caldav/", "", nil)
		if status != http.StatusOK {
			t.Errorf("OPTIONS failed with %d", status)
		}

		// Step B: Principal Discovery (PROPFIND /caldav) Depth:0
		propfindPrincipal := `<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:current-user-principal/>
    <C:calendar-home-set/>
  </D:prop>
</D:propfind>`
		status, resp := sendRequest("PROPFIND", "/caldav", propfindPrincipal, map[string]string{"Depth": "0"})
		if status != http.StatusMultiStatus {
			t.Errorf("Principal discovery returned HTTP %d, expected 207", status)
		}
		if !strings.Contains(resp, "<D:current-user-principal><D:href>/caldav/u/caldav/</D:href>") {
			t.Errorf("expected principal URL in response, got XML:\n%s", resp)
		}
		if !strings.Contains(resp, "<C:calendar-home-set><D:href>/caldav/u/caldav/</D:href>") {
			t.Errorf("expected calendar-home-set URL in response, got XML:\n%s", resp)
		}

		// Step C: Calendar Discovery (PROPFIND /caldav/u/caldav) Depth:1
		propfindHome := `<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:displayname/>
    <D:resourcetype/>
  </D:prop>
</D:propfind>`
		status, resp = sendRequest("PROPFIND", "/caldav/u/caldav", propfindHome, map[string]string{"Depth": "1"})
		if status != http.StatusMultiStatus {
			t.Errorf("Calendar discovery returned HTTP %d, expected 207", status)
		}
		if !strings.Contains(resp, "<D:href>/caldav/u/caldav/default/</D:href>") {
			t.Errorf("expected calendar href, got XML:\n%s", resp)
		}

		// Step D: Calendar Properties (PROPFIND /caldav/u/caldav/default) Depth:0
		propfindCalendarProps := `<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:CS="http://calendarserver.org/ns/">
  <D:prop>
    <D:displayname/>
    <CS:getctag/>
    <D:sync-token/>
    <C:calendar-color/>
  </D:prop>
</D:propfind>`
		status, resp = sendRequest("PROPFIND", "/caldav/u/caldav/default", propfindCalendarProps, map[string]string{"Depth": "0"})
		if status != http.StatusMultiStatus {
			t.Errorf("Calendar props returned HTTP %d, expected 207", status)
		}
		if !strings.Contains(resp, "<D:sync-token>1</D:sync-token>") {
			t.Errorf("expected sync-token 1 initially, got XML:\n%s", resp)
		}
		if !strings.Contains(resp, "<IC:calendar-color>#4F46E5</IC:calendar-color>") {
			t.Errorf("expected calendar-color, got XML:\n%s", resp)
		}

		// Step E: Initial Event Query (calendar-query)
		calendarQuery := `<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT"/></C:comp-filter>
  </C:filter>
</C:calendar-query>`
		status, resp = sendRequest("REPORT", "/caldav/u/caldav/default", calendarQuery, nil)
		if status != http.StatusMultiStatus {
			t.Errorf("Initial event query returned HTTP %d, expected 207", status)
		}
		if !strings.Contains(resp, "event-1.ics") || !strings.Contains(resp, "Initial Sync Event") {
			t.Errorf("expected initial event-1 content, got XML:\n%s", resp)
		}
	})

	// -------------------------------------------------------------
	// DYNAMIC REAL-TIME SYNC LOOP VERIFICATION
	// -------------------------------------------------------------
	t.Run("Dynamic Real-time Sync and Client Incremental Updates", func(t *testing.T) {
		// Modify dynamic Mock WPS Server state:
		// 1. Delete event-1
		// 2. Add event-new
		mockWps.deleteEvent("event-1")
		mockWps.setEvent(wpsclient.EventInfo{
			UID:      "event-new",
			Href:     "/u/u123/default/event-new.ics",
			ETag:     "etag-new-v1",
			ICalData: "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:event-new\nSUMMARY:Real-time Added Event\nDTSTART:20260525T120000Z\nDTEND:20260525T130000Z\nEND:VEVENT\nEND:VCALENDAR",
		})

		// Trigger Poller background synchronization once programmatically
		if err := p.SyncOnce(); err != nil {
			t.Fatalf("poller incremental sync failed: %v", err)
		}

		// Verify local SQLite cache got updated
		events, err := c.GetAllEvents()
		if err != nil || len(events) != 1 {
			t.Fatalf("expected exactly 1 event in local cache after sync, got %d, err: %v", len(events), err)
		}
		if events[0].UID != "event-new" {
			t.Errorf("expected event-new in cache, got %s", events[0].UID)
		}

		// Simulated Client performs incremental sync using sync-token 1
		syncCollection := `<?xml version="1.0" encoding="utf-8" ?>
<D:sync-collection xmlns:D="DAV:">
  <D:sync-token>1</D:sync-token>
  <D:prop>
    <D:getetag/>
  </D:prop>
</D:sync-collection>`
		status, resp := sendRequest("REPORT", "/caldav/u/caldav/default", syncCollection, nil)
		if status != http.StatusMultiStatus {
			t.Errorf("sync-collection returned HTTP %d, expected 207", status)
		}

		// ---------------------------------------------------------
		// CRITICAL PROTOCOL VERIFICATIONS
		// ---------------------------------------------------------
		// A. Check that it returns sync-token = 2 representing the new state
		if !strings.Contains(resp, "<D:sync-token>2</D:sync-token>") {
			t.Errorf("expected sync-token 2 in response, got XML:\n%s", resp)
		}

		// B. Check that event-new is returned as an ADDED event with status 200 OK
		reEventNew := regexp.MustCompile(`(?is)<D:href>[^<]*event-new.ics</D:href>\s*<D:propstat>\s*<D:prop>\s*<D:getetag>"etag-new-v1"</D:getetag>\s*<C:calendar-data>.*?</D:prop>\s*<D:status>HTTP/1.1 200 OK</D:status>`)
		if !reEventNew.MatchString(resp) {
			t.Errorf("expected event-new.ics added with 200 OK and ETag, got XML:\n%s", resp)
		}

		// C. Check that event-1 is returned as a DELETED event with status 404 Not Found (RFC 6578 standard)
		reEvent1Del := regexp.MustCompile(`(?is)<D:href>[^<]*event-1.ics</D:href>\s*<D:status>HTTP/1.1 404 Not Found</D:status>`)
		if !reEvent1Del.MatchString(resp) {
			t.Errorf("expected event-1.ics deletion notification with 404 Not Found, got XML:\n%s", resp)
		}

		t.Log("SUCCESS: E2E client handshake and real-time incremental synchronization verified successfully!")
	})

	// -------------------------------------------------------------
	// COMPATIBILITY VERIFICATIONS (multiget & MKCALENDAR)
	// -------------------------------------------------------------
	t.Run("macOS Client calendar-multiget & MKCALENDAR Compatibility", func(t *testing.T) {
		// A. Test calendar-multiget requesting both existing event-new and non-existing event-1
		multigetXML := `<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-multiget xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <D:href>/caldav/u/caldav/default/event-new.ics</D:href>
  <D:href>/caldav/u/caldav/default/event-1.ics</D:href>
</C:calendar-multiget>`
		status, resp := sendRequest("REPORT", "/caldav/u/caldav/default", multigetXML, nil)
		if status != http.StatusMultiStatus {
			t.Errorf("calendar-multiget returned HTTP %d, expected 207", status)
		}
		if !strings.Contains(resp, "event-new.ics") || !strings.Contains(resp, "HTTP/1.1 200 OK") {
			t.Errorf("expected event-new.ics to be found with 200 OK, got XML:\n%s", resp)
		}
		if !strings.Contains(resp, "Real-time Added Event") {
			t.Errorf("expected event-new.ics data in response, got XML:\n%s", resp)
		}
		if !strings.Contains(resp, "event-1.ics") || !strings.Contains(resp, "HTTP/1.1 404 Not Found") {
			t.Errorf("expected event-1.ics to return 404 Not Found, got XML:\n%s", resp)
		}

		// B. Test MKCALENDAR method to verify that it is handled elegantly (returns 403 Forbidden)
		status, resp = sendRequest("MKCALENDAR", "/caldav/u/caldav/new-calendar-uid/", "", nil)
		if status != http.StatusForbidden {
			t.Errorf("MKCALENDAR returned HTTP %d, expected 403", status)
		}
		if !strings.Contains(resp, "<C:initialize-calendar-collection-allowed/>") {
			t.Errorf("expected standard WebDAV error in MKCALENDAR response, got:\n%s", resp)
		}

		// C. Test OPTIONS response contains MKCALENDAR in Allow header
		status, _ = sendRequest("OPTIONS", "/caldav/", "", nil)
		req, _ := http.NewRequest("OPTIONS", proxyHttpServer.URL+"/caldav/", nil)
		req.SetBasicAuth("caldav", "proxypass")
		respOpt, err := client.Do(req)
		if err != nil {
			t.Fatalf("OPTIONS direct request failed: %v", err)
		}
		defer respOpt.Body.Close()
		allowHeader := respOpt.Header.Get("Allow")
		if !strings.Contains(allowHeader, "MKCALENDAR") {
			t.Errorf("expected OPTIONS Allow header to contain MKCALENDAR, got: %s", allowHeader)
		}
	})
}

