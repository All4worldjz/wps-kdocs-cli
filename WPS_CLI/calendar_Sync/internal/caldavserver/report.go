package caldavserver

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"wps-caldav-proxy/internal/cache"
)

func (s *Server) handleReport(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Read body failed", http.StatusBadRequest)
		return
	}
	bodyStr := string(body)

	if strings.Contains(bodyStr, "sync-collection") {
		s.handleSyncCollection(w, bodyStr)
	} else if strings.Contains(bodyStr, "calendar-query") {
		s.handleCalendarQuery(w, bodyStr)
	} else if strings.Contains(bodyStr, "calendar-multiget") {
		s.handleCalendarMultiget(w, bodyStr)
	} else {
		http.Error(w, "Unsupported REPORT query", http.StatusBadRequest)
	}
}

func (s *Server) handleSyncCollection(w http.ResponseWriter, body string) {
	calendarPath := s.basePath + "/u/" + s.proxyUser + "/default"

	var clientRev int64
	// Match both prefixed and non-prefixed sync-token elements
	reToken := regexp.MustCompile(`(?i)<(?:[^>:]*:)?sync-token>(.*?)</(?:[^>:]*:)?sync-token>`)
	m := reToken.FindStringSubmatch(body)
	if len(m) > 1 {
		val := strings.TrimSpace(m[1])
		// Extract last number from URI or use raw integer
		if idx := strings.LastIndex(val, "/"); idx != -1 {
			val = val[idx+1:]
		}
		if revInt, err := strconv.ParseInt(val, 10, 64); err == nil {
			clientRev = revInt
		}
	}

	currentRev, _ := s.cache.GetRevision()

	w.Header().Set("Content-Type", "text/xml; charset=utf-8")
	w.WriteHeader(http.StatusMultiStatus)

	var xmlResp strings.Builder
	xmlResp.WriteString(`<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
`)
	xmlResp.WriteString(fmt.Sprintf("  <D:sync-token>%d</D:sync-token>\n", currentRev))

	// If client token is up to date or ahead, return no changes
	if clientRev >= currentRev {
		xmlResp.WriteString("</D:multistatus>")
		w.Write([]byte(xmlResp.String()))
		return
	}

	// Fetch changes since client revision
	changes, err := s.cache.GetChangesSince(clientRev)
	if err != nil {
		http.Error(w, "Internal cache error", http.StatusInternalServerError)
		return
	}

	// Group changes by UID to keep only the latest state for each UID in this sync window
	latestChanges := make(map[string]*cache.ChangeLogEntry)
	var orderedUIDs []string

	for _, ch := range changes {
		if _, exists := latestChanges[ch.UID]; !exists {
			orderedUIDs = append(orderedUIDs, ch.UID)
		}
		latestChanges[ch.UID] = ch
	}

	for _, uid := range orderedUIDs {
		ch := latestChanges[uid]
		href := fmt.Sprintf("%s/%s.ics", calendarPath, ch.UID)

		if ch.Action == "delete" {
			// standard RFC 6578 deletion notification
			xmlResp.WriteString("  <D:response>\n")
			xmlResp.WriteString(fmt.Sprintf("    <D:href>%s</D:href>\n", href))
			xmlResp.WriteString("    <D:status>HTTP/1.1 404 Not Found</D:status>\n")
			xmlResp.WriteString("  </D:response>\n")
		} else {
			// set/updated action
			ev, err := s.cache.GetEvent(ch.UID)
			if err != nil || ev == nil {
				continue // Deleted in subsequent action or missing
			}

			xmlResp.WriteString("  <D:response>\n")
			xmlResp.WriteString(fmt.Sprintf("    <D:href>%s</D:href>\n", href))
			xmlResp.WriteString("    <D:propstat>\n")
			xmlResp.WriteString("      <D:prop>\n")
			xmlResp.WriteString(fmt.Sprintf("        <D:getetag>\"%s\"</D:getetag>\n", ev.ETag))
			xmlResp.WriteString(fmt.Sprintf("        <C:calendar-data>%s</C:calendar-data>\n", xmlEscape(ev.ICalData)))
			xmlResp.WriteString("      </D:prop>\n")
			xmlResp.WriteString("      <D:status>HTTP/1.1 200 OK</D:status>\n")
			xmlResp.WriteString("    </D:propstat>\n")
			xmlResp.WriteString("  </D:response>\n")
		}
	}

	xmlResp.WriteString("</D:multistatus>")
	w.Write([]byte(xmlResp.String()))
}

func (s *Server) handleCalendarQuery(w http.ResponseWriter, body string) {
	calendarPath := s.basePath + "/u/" + s.proxyUser + "/default"

	wantCalendarData := strings.Contains(body, "calendar-data")
	wantETag := strings.Contains(body, "getetag")

	// Parse standard CalDAV time-range filter
	// e.g., <C:time-range start="20260525T100000Z" end="20260525T110000Z"/>
	var startEpoch int64 = 0
	var endEpoch int64 = 253402300799 // Year 9999 standard CST midnight

	reTimeRange := regexp.MustCompile(`(?i)time-range\s+[^>]*\bstart="([^"]+)"`)
	mStart := reTimeRange.FindStringSubmatch(body)
	if len(mStart) > 1 {
		if t, err := time.Parse("20060102T150405Z", mStart[1]); err == nil {
			startEpoch = t.Unix()
		}
	}

	reTimeRangeEnd := regexp.MustCompile(`(?i)time-range\s+[^>]*\bend="([^"]+)"`)
	mEnd := reTimeRangeEnd.FindStringSubmatch(body)
	if len(mEnd) > 1 {
		if t, err := time.Parse("20060102T150405Z", mEnd[1]); err == nil {
			endEpoch = t.Unix()
		}
	}

	// Fetch index-backed query from local SQLite cache! Extremely fast!
	events, err := s.cache.GetEventsInTimeRange(startEpoch, endEpoch)
	if err != nil {
		http.Error(w, "Internal cache query error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/xml; charset=utf-8")
	w.WriteHeader(http.StatusMultiStatus)

	var xmlResp strings.Builder
	xmlResp.WriteString(`<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
`)

	for _, ev := range events {
		href := fmt.Sprintf("%s/%s.ics", calendarPath, ev.UID)
		xmlResp.WriteString("  <D:response>\n")
		xmlResp.WriteString(fmt.Sprintf("    <D:href>%s</D:href>\n", href))
		xmlResp.WriteString("    <D:propstat>\n")
		xmlResp.WriteString("      <D:prop>\n")

		if wantETag {
			xmlResp.WriteString(fmt.Sprintf("        <D:getetag>\"%s\"</D:getetag>\n", ev.ETag))
		}
		if wantCalendarData {
			xmlResp.WriteString(fmt.Sprintf("        <C:calendar-data>%s</C:calendar-data>\n", xmlEscape(ev.ICalData)))
		}

		xmlResp.WriteString("      </D:prop>\n")
		xmlResp.WriteString("      <D:status>HTTP/1.1 200 OK</D:status>\n")
		xmlResp.WriteString("    </D:propstat>\n")
		xmlResp.WriteString("  </D:response>\n")
	}

	xmlResp.WriteString("</D:multistatus>")
	w.Write([]byte(xmlResp.String()))
}

func xmlEscape(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	s = strings.ReplaceAll(s, "\"", "&quot;")
	return s
}

func (s *Server) handleCalendarMultiget(w http.ResponseWriter, body string) {
	wantCalendarData := strings.Contains(body, "calendar-data")
	wantETag := strings.Contains(body, "getetag")

	// Find all `<D:href>` or `<href>` tags
	reHref := regexp.MustCompile(`(?i)<(?:[^>:]*:)?href>([^<]+)</(?:[^>:]*:)?href>`)
	matches := reHref.FindAllStringSubmatch(body, -1)

	w.Header().Set("Content-Type", "text/xml; charset=utf-8")
	w.WriteHeader(http.StatusMultiStatus)

	var xmlResp strings.Builder
	xmlResp.WriteString(`<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
`)

	for _, m := range matches {
		href := strings.TrimSpace(m[1])
		if href == "" {
			continue
		}

		// Skip paths that are collections themselves (just to be safe)
		if strings.HasSuffix(href, "/") || !strings.HasSuffix(href, ".ics") {
			continue
		}

		// Extract UID from href path (e.g. /caldav/u/caldav/default/xxx.ics)
		parts := strings.Split(strings.TrimSuffix(href, ".ics"), "/")
		uid := parts[len(parts)-1]

		ev, err := s.cache.GetEvent(uid)
		if err != nil {
			log.Printf("[CalDAV] Error reading event %s: %v", uid, err)
			ev = nil
		}

		if ev != nil {
			xmlResp.WriteString("  <D:response>\n")
			xmlResp.WriteString(fmt.Sprintf("    <D:href>%s</D:href>\n", href))
			xmlResp.WriteString("    <D:propstat>\n")
			xmlResp.WriteString("      <D:prop>\n")

			if wantETag {
				xmlResp.WriteString(fmt.Sprintf("        <D:getetag>\"%s\"</D:getetag>\n", ev.ETag))
			}
			if wantCalendarData {
				xmlResp.WriteString(fmt.Sprintf("        <C:calendar-data>%s</C:calendar-data>\n", xmlEscape(ev.ICalData)))
			}

			xmlResp.WriteString("      </D:prop>\n")
			xmlResp.WriteString("      <D:status>HTTP/1.1 200 OK</D:status>\n")
			xmlResp.WriteString("    </D:propstat>\n")
			xmlResp.WriteString("  </D:response>\n")
		} else {
			xmlResp.WriteString("  <D:response>\n")
			xmlResp.WriteString(fmt.Sprintf("    <D:href>%s</D:href>\n", href))
			xmlResp.WriteString("    <D:status>HTTP/1.1 404 Not Found</D:status>\n")
			xmlResp.WriteString("  </D:response>\n")
		}
	}

	xmlResp.WriteString("</D:multistatus>")
	w.Write([]byte(xmlResp.String()))
}
