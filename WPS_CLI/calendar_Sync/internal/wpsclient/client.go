package wpsclient

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

type Client struct {
	httpClient *http.Client
	serverURL  string
	username   string
	password   string
	principal  string
	calHome    string
	calendar   string
}

type EventInfo struct {
	UID       string
	Href      string
	ETag      string
	ICalData  string
	StartTime int64
	EndTime   int64
	IsAllDay  bool
}

func New(serverURL, username, password string) *Client {
	transport := NewDigestTransport(username, password)
	return &Client{
		httpClient: &http.Client{
			Timeout:   30 * time.Second,
			Transport: transport,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
		serverURL: strings.TrimRight(serverURL, "/"),
		username:  username,
		password:  password,
	}
}

func (c *Client) doRequest(method, path string, body []byte, contentType string) (int, []byte, error) {
	fullURL := c.serverURL + path

	var reqBody io.Reader
	if body != nil {
		reqBody = bytes.NewReader(body)
	}

	req, err := http.NewRequest(method, fullURL, reqBody)
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("User-Agent", "WPS-Caldav-Proxy/1.0")
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()

	// Handle 301/302/307 Redirects manually due to WPS trailing slash redirects
	if resp.StatusCode == http.StatusMovedPermanently || resp.StatusCode == http.StatusFound || resp.StatusCode == http.StatusTemporaryRedirect {
		newURL := resp.Header.Get("Location")
		if newURL == "" {
			return resp.StatusCode, nil, fmt.Errorf("redirect with no Location")
		}
		u, err := url.Parse(newURL)
		if err != nil {
			return resp.StatusCode, nil, fmt.Errorf("invalid redirect URL %q: %w", newURL, err)
		}

		redirectPath := u.Path
		if u.RawQuery != "" {
			redirectPath += "?" + u.RawQuery
		}
		return c.doRequest(method, redirectPath, body, contentType)
	}

	respBody, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, respBody, nil
}

func (c *Client) Discover() error {
	xmlBody := `<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:current-user-principal/><C:calendar-home-set/></D:prop>
</D:propfind>`

	status, body, err := c.doRequest("PROPFIND", "/", []byte(xmlBody), "text/xml; charset=utf-8")
	if err != nil {
		return fmt.Errorf("propfind root: %w", err)
	}
	if status != 207 {
		return fmt.Errorf("propfind root returned HTTP %d: %s", status, trunc(string(body), 200))
	}

	principal := xmlFindHref(body, "current-user-principal")
	calHome := xmlFindHref(body, "calendar-home-set")
	if principal == "" {
		return fmt.Errorf("no principal URL in response: %s", trunc(string(body), 200))
	}
	if calHome == "" {
		calHome = principal
	}
	c.principal = principal
	c.calHome = calHome

	// Find calendar with Depth:1
	calBody := `<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:displayname/><C:calendar-description/></D:prop>
</D:propfind>`

	status, body, err = c.doRequest("PROPFIND", calHome, []byte(calBody), "text/xml; charset=utf-8")
	if err != nil {
		return fmt.Errorf("propfind cal home: %w", err)
	}
	if status != 207 {
		return fmt.Errorf("propfind cal home returned HTTP %d: %s", status, trunc(string(body), 200))
	}

	calendar := xmlFindCalendarHref(body)
	if calendar == "" {
		return fmt.Errorf("no calendar found in response: %s", trunc(string(body), 200))
	}

	c.calendar = calendar
	return nil
}

func (c *Client) CalendarURL() string {
	return c.calendar
}

func (c *Client) FetchEvents() ([]EventInfo, error) {
	if c.calendar == "" {
		if err := c.Discover(); err != nil {
			return nil, err
		}
	}

	xmlBody := `<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/><C:calendar-data/></D:prop>
  <C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT"/></C:comp-filter></C:filter>
</C:calendar-query>`

	status, body, err := c.doRequest("REPORT", c.calendar, []byte(xmlBody), "text/xml; charset=utf-8")
	if err != nil {
		return nil, err
	}
	if status != 207 {
		return nil, fmt.Errorf("calendar-query returned HTTP %d: %s", status, trunc(string(body), 200))
	}

	return parseEventsXML(string(body)), nil
}

// ====== XML helpers (case-insensitive, namespace-prefix-aware) ======

func xmlFindHref(xmlData []byte, tagName string) string {
	s := string(xmlData)
	pat := fmt.Sprintf(`(?is)<(?:[^>:]*:)?%s[^>]*>.*?<(?:[^>:]*:)?href[^>]*>([^<]*)</(?:[^>:]*:)?href>.*?</(?:[^>:]*:)?%s>`, tagName, tagName)
	re := regexp.MustCompile(pat)
	m := re.FindStringSubmatch(s)
	if len(m) > 1 {
		return strings.TrimSpace(m[1])
	}
	// Fallback: first href in body
	re2 := regexp.MustCompile(`(?is)<(?:[^>:]*:)?href[^>]*>([^<]*)</(?:[^>:]*:)?href>`)
	m2 := re2.FindStringSubmatch(s)
	if len(m2) > 1 {
		return strings.TrimSpace(m2[1])
	}
	return ""
}

func xmlFindCalendarHref(xmlData []byte) string {
	s := string(xmlData)
	re := regexp.MustCompile(`(?is)<(?:[^>:]*:)?response>(.*?)</(?:[^>:]*:)?response>`)
	matches := re.FindAllStringSubmatch(s, -1)
	uuidRe := regexp.MustCompile(`[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`)

	for _, m := range matches {
		block := m[1]
		if !strings.Contains(strings.ToLower(block), "calendar-description") && !uuidRe.MatchString(block) {
			continue
		}
		hrefRe := regexp.MustCompile(`(?is)<(?:[^>:]*:)?href[^>]*>([^<]*)</(?:[^>:]*:)?href>`)
		hm := hrefRe.FindStringSubmatch(block)
		if len(hm) > 1 && !strings.HasSuffix(hm[1], "/principal/") && !strings.HasSuffix(hm[1], "/principals/") {
			return strings.TrimSpace(hm[1])
		}
	}
	return ""
}

func parseEventsXML(xmlData string) []EventInfo {
	var events []EventInfo
	re := regexp.MustCompile(`(?is)<(?:[^>:]*:)?response>(.*?)</(?:[^>:]*:)?response>`)
	matches := re.FindAllStringSubmatch(xmlData, -1)

	for _, m := range matches {
		block := m[1]

		href := xmlTagCI(block, "href")
		etag := xmlTagCI(block, "getetag")
		etag = strings.ReplaceAll(etag, "&quot;", "\"")
		etag = strings.ReplaceAll(etag, "&amp;", "&")
		icalData := xmlTagCI(block, "calendar-data")

		if icalData == "" {
			continue
		}
		uid := extractICalUID(icalData)
		if uid == "" {
			continue
		}

		start, end, allDay := parseICalTimes(icalData)

		events = append(events, EventInfo{
			UID:       uid,
			Href:      strings.TrimSpace(href),
			ETag:      strings.Trim(etag, "\"\t "),
			ICalData:  icalData,
			StartTime: start,
			EndTime:   end,
			IsAllDay:  allDay,
		})
	}
	return events
}

func xmlTagCI(xml, tag string) string {
	re := regexp.MustCompile(fmt.Sprintf(`(?is)<(?:[^>:]*:)?%s[^>]*>([\s\S]*?)</(?:[^>:]*:)?%s>`, tag, tag))
	m := re.FindStringSubmatch(xml)
	if len(m) > 1 {
		return m[1]
	}
	return ""
}

func extractICalUID(icalData string) string {
	re := regexp.MustCompile(`(?i)UID:([^\r\n]+)`)
	m := re.FindStringSubmatch(icalData)
	if len(m) > 1 {
		return strings.TrimSpace(m[1])
	}
	return ""
}

func parseICalTimes(ical string) (start int64, end int64, allDay bool) {
	cst, _ := time.LoadLocation("Asia/Shanghai")
	if cst == nil {
		cst = time.FixedZone("CST", 8*3600)
	}

	dtstartRaw := extractICalLine(ical, "DTSTART")
	dtendRaw := extractICalLine(ical, "DTEND")

	parseTime := func(raw string) (time.Time, bool) {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			return time.Time{}, false
		}

		// Split prefix and value
		val := raw
		if strings.Contains(raw, ":") {
			val = strings.SplitN(raw, ":", 2)[1]
		}
		val = strings.TrimSpace(val)

		// Check if it's date-only
		// e.g. DTSTART;VALUE=DATE:20260525 or length of val is 8 (YYYYMMDD)
		if strings.Contains(raw, "VALUE=DATE") || len(val) == 8 {
			t, err := time.ParseInLocation("20060102", val, cst)
			if err == nil {
				return t, true
			}
		}

		// 1) UTC Date-time
		if strings.HasSuffix(val, "Z") {
			t, err := time.Parse("20060102T150405Z", val)
			if err == nil {
				return t, false
			}
		}

		// 2) With TZID
		if strings.Contains(raw, "TZID=") {
			t, err := time.ParseInLocation("20060102T150405", val, cst)
			if err == nil {
				return t, false
			}
		}

		// 3) Local time fallback
		t, err := time.ParseInLocation("20060102T150405", val, cst)
		if err == nil {
			return t, false
		}

		return time.Time{}, false
	}

	startTime, startAllDay := parseTime(dtstartRaw)
	endTime, _ := parseTime(dtendRaw)

	if startTime.IsZero() {
		startTime = time.Now()
	}

	if endTime.IsZero() {
		if startAllDay {
			endTime = startTime.AddDate(0, 0, 1)
		} else {
			endTime = startTime.Add(1 * time.Hour)
		}
	}

	return startTime.Unix(), endTime.Unix(), startAllDay
}

func extractICalLine(ical, prefix string) string {
	lines := strings.Split(ical, "\n")
	inVEvent := false
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.EqualFold(line, "BEGIN:VEVENT") {
			inVEvent = true
			continue
		}
		if strings.EqualFold(line, "END:VEVENT") {
			inVEvent = false
			continue
		}
		if !inVEvent {
			continue
		}
		// Case insensitive check
		if len(line) >= len(prefix) && strings.EqualFold(line[:len(prefix)], prefix) {
			return line
		}
	}
	return ""
}

func trunc(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
