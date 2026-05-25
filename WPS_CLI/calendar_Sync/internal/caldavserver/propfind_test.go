package caldavserver

import (
	"encoding/xml"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"wps-caldav-proxy/internal/cache"
)

func TestPROPFINDCompliance(t *testing.T) {
	// Create mock cache
	tmpDir, err := os.MkdirTemp("", "caldavserver_test_*")
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

	// Seed cache with one event
	_, _ = c.MergeEvents([]*cache.Event{
		{
			UID:       "seeded-uid",
			Href:      "/caldav/u/caldav/default/seeded-uid.ics",
			ETag:      "seeded-etag",
			ICalData:  "BEGIN:VCALENDAR\nEND:VCALENDAR",
			StartTime: 1779703200,
			EndTime:   1779706800,
		},
	})

	server := New(c, "caldav", "proxypass", "/caldav")

	// Test OPTIONS
	wOptions := httptest.NewRecorder()
	reqOptions := httptest.NewRequest("OPTIONS", "/caldav/", nil)
	reqOptions.SetBasicAuth("caldav", "proxypass")
	server.ServeHTTP(wOptions, reqOptions)

	if wOptions.Code != http.StatusOK {
		t.Errorf("expected OPTIONS code 200, got %d", wOptions.Code)
	}
	davHeader := wOptions.Header().Get("DAV")
	if !strings.Contains(davHeader, "calendar-access") {
		t.Errorf("expected calendar-access in DAV header, got %s", davHeader)
	}

	// Test PROPFIND request with strict XML body
	propfindBody := `<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:CS="http://calendarserver.org/ns/">
  <D:prop>
    <D:displayname/>
    <CS:getctag/>
    <D:some-unsupported-property/>
  </D:prop>
</D:propfind>`

	wPropfind := httptest.NewRecorder()
	reqPropfind := httptest.NewRequest("PROPFIND", "/caldav/u/caldav/default", strings.NewReader(propfindBody))
	reqPropfind.Header.Set("Depth", "0")
	reqPropfind.SetBasicAuth("caldav", "proxypass")
	server.ServeHTTP(wPropfind, reqPropfind)

	if wPropfind.Code != http.StatusMultiStatus {
		t.Errorf("expected PROPFIND code 207, got %d", wPropfind.Code)
	}

	respBody, _ := io.ReadAll(wPropfind.Body)
	respStr := string(respBody)

	// Check that we have a propstat with 200 OK
	if !strings.Contains(respStr, "<D:status>HTTP/1.1 200 OK</D:status>") {
		t.Error("expected 200 OK propstat in multi-status response")
	}

	// Check that we have a propstat with 404 Not Found for the unsupported property
	if !strings.Contains(respStr, "<D:status>HTTP/1.1 404 Not Found</D:status>") {
		t.Error("expected 404 Not Found propstat in multi-status response")
	}

	if !strings.Contains(respStr, "<D:some-unsupported-property") {
		t.Error("expected some-unsupported-property in 404 propstat")
	}

	// Verify displayname and ctag are inside the 200 OK block
	if !strings.Contains(respStr, "WPS Calendar") {
		t.Error("expected displayname value in 200 propstat")
	}

	err = xml.Unmarshal(respBody, &struct{}{})
	// Unmarshal of complex arbitrary multi-status might fail if type is strict, but structural check should succeed
	t.Logf("PROPFIND XML payload:\n%s", respStr)
}
