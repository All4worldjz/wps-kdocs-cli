package wpsclient

import (
	"testing"
)

func TestParseICalTimes(t *testing.T) {
	tests := []struct {
		name       string
		ical       string
		wantStart  int64
		wantEnd    int64
		wantAllDay bool
	}{
		{
			name: "UTC Time",
			ical: `BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid1
DTSTART:20260525T100000Z
DTEND:20260525T110000Z
END:VEVENT
END:VCALENDAR`,
			wantStart:  1779703200, // 2026-05-25 10:00:00 UTC
			wantEnd:    1779706800, // 2026-05-25 11:00:00 UTC
			wantAllDay: false,
		},
		{
			name: "Local Time (CST Fallback)",
			ical: `BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid2
DTSTART:20260525T180000
DTEND:20260525T190000
END:VEVENT
END:VCALENDAR`,
			wantStart:  1779703200, // 2026-05-25 18:00:00 CST = 10:00:00 UTC
			wantEnd:    1779706800, // 2026-05-25 19:00:00 CST = 11:00:00 UTC
			wantAllDay: false,
		},
		{
			name: "All-Day Date",
			ical: `BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid3
DTSTART;VALUE=DATE:20260525
DTEND;VALUE=DATE:20260526
END:VEVENT
END:VCALENDAR`,
			wantStart:  1779638400, // 2026-05-25 00:00:00 CST = 2026-05-24 16:00:00 UTC
			wantEnd:    1779724800, // 2026-05-26 00:00:00 CST = 2026-05-25 16:00:00 UTC
			wantAllDay: true,
		},
		{
			name: "Timezone Block Shadowing",
			ical: `BEGIN:VCALENDAR
BEGIN:VTIMEZONE
TZID:Asia/Shanghai
BEGIN:STANDARD
DTSTART:19890917T020000
TZNAME:GMT+8
TZOFFSETFROM:+0900
TZOFFSETTO:+0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:uid4
DTSTART;TZID=Asia/Shanghai:20260525T180000
DTEND;TZID=Asia/Shanghai:20260525T190000
END:VEVENT
END:VCALENDAR`,
			wantStart:  1779703200, // 2026-05-25 18:00:00 CST = 10:00:00 UTC
			wantEnd:    1779706800, // 2026-05-25 19:00:00 CST = 11:00:00 UTC
			wantAllDay: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			start, end, allDay := parseICalTimes(tt.ical)
			if start != tt.wantStart {
				t.Errorf("start time mismatch: got %d, want %d", start, tt.wantStart)
			}
			if end != tt.wantEnd {
				t.Errorf("end time mismatch: got %d, want %d", end, tt.wantEnd)
			}
			if allDay != tt.wantAllDay {
				t.Errorf("all-day flag mismatch: got %t, want %t", allDay, tt.wantAllDay)
			}
		})
	}
}

func TestXMLHelpers(t *testing.T) {
	xmlData := []byte(`<?xml version="1.0" encoding="utf-8"?>
<multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <response>
    <href>/caldav/u/123/default/</href>
    <propstat>
      <prop>
        <current-user-principal>
          <href>/caldav/u/123/</href>
        </current-user-principal>
        <C:calendar-home-set>
          <href>/caldav/u/123/home/</href>
        </C:calendar-home-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
  </response>
</multistatus>`)

	principal := xmlFindHref(xmlData, "current-user-principal")
	if principal != "/caldav/u/123/" {
		t.Errorf("expected /caldav/u/123/, got %s", principal)
	}

	calHome := xmlFindHref(xmlData, "calendar-home-set")
	if calHome != "/caldav/u/123/home/" {
		t.Errorf("expected /caldav/u/123/home/, got %s", calHome)
	}
}
