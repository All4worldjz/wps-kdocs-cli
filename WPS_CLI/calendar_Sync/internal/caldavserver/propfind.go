package caldavserver

import (
	"bytes"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// Supported properties check helper
func isPropertySupported(name xml.Name, isCalendar bool) bool {
	local := name.Local
	space := name.Space

	switch local {
	case "displayname", "resourcetype", "current-user-principal", "principal-URL", "sync-token":
		return space == "DAV:" || space == ""
	case "getcontenttype", "getcontentlength", "getetag":
		return space == "DAV:" || space == ""
	case "calendar-home-set", "supported-calendar-component-set", "calendar-description", "calendar-timezone":
		return space == "urn:ietf:params:xml:ns:caldav"
	case "getctag":
		return space == "http://calendarserver.org/ns/" || space == "CS:" || space == ""
	case "calendar-color", "calendar-order":
		return space == "http://apple.com/ns/ical/" || space == "ical:" || space == "urn:ietf:params:xml:ns:caldav" || space == ""
	}
	return false
}

func parsePropfindRequest(r io.Reader) ([]xml.Name, error) {
	d := xml.NewDecoder(r)
	var props []xml.Name
	var inProp bool

	for {
		tok, err := d.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}

		switch el := tok.(type) {
		case xml.StartElement:
			local := el.Name.Local
			// Look for <prop> tag in DAV namespace or empty namespace
			if (local == "prop" || local == "PROP") && (el.Name.Space == "DAV:" || el.Name.Space == "") {
				inProp = true
			} else if inProp {
				props = append(props, el.Name)
			}
		case xml.EndElement:
			local := el.Name.Local
			if (local == "prop" || local == "PROP") && (el.Name.Space == "DAV:" || el.Name.Space == "") {
				inProp = false
			}
		}
	}

	return props, nil
}

func (s *Server) handlePropfind(w http.ResponseWriter, r *http.Request) {
	depth := r.Header.Get("Depth")
	if depth == "" {
		depth = "all"
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Read body failed", http.StatusBadRequest)
		return
	}

	var requestedProps []xml.Name
	if len(body) > 0 {
		requestedProps, _ = parsePropfindRequest(bytes.NewReader(body))
	}

	// Default properties to return if none were specified
	if len(requestedProps) == 0 {
		requestedProps = []xml.Name{
			{Space: "DAV:", Local: "displayname"},
			{Space: "DAV:", Local: "resourcetype"},
			{Space: "DAV:", Local: "current-user-principal"},
			{Space: "urn:ietf:params:xml:ns:caldav", Local: "calendar-home-set"},
			{Space: "http://calendarserver.org/ns/", Local: "getctag"},
			{Space: "DAV:", Local: "sync-token"},
		}
	}

	isPrincipalRoot := r.URL.Path == s.basePath || r.URL.Path == s.basePath+"/" || strings.HasSuffix(r.URL.Path, "/u/"+s.proxyUser) || strings.HasSuffix(r.URL.Path, "/u/"+s.proxyUser+"/")
	isCalendarRoot := strings.HasSuffix(r.URL.Path, "/default") || strings.HasSuffix(r.URL.Path, "/default/")

	w.Header().Set("Content-Type", "text/xml; charset=utf-8")
	w.WriteHeader(http.StatusMultiStatus)

	var xmlResponse strings.Builder
	xmlResponse.WriteString(`<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:CS="http://calendarserver.org/ns/" xmlns:IC="http://apple.com/ns/ical/">
`)

	userPath := s.basePath + "/u/" + s.proxyUser
	calendarPath := userPath + "/default"

	if isCalendarRoot && depth == "1" {
		// Return list of all events in the calendar (each event is a separate D:response)
		s.propfindCalendarEvents(&xmlResponse, calendarPath, requestedProps)
	} else if isCalendarRoot {
		// Depth 0 on calendar root itself
		s.propfindSingleResource(&xmlResponse, calendarPath, true, requestedProps)
	} else if isPrincipalRoot {
		// Principal info (and child calendars if Depth:1 discovery)
		s.propfindSingleResource(&xmlResponse, userPath+"/", false, requestedProps)
		if depth == "1" {
			s.propfindSingleResource(&xmlResponse, calendarPath+"/", true, requestedProps)
		}
	} else {
		// Default collection info
		s.propfindSingleResource(&xmlResponse, r.URL.Path, false, requestedProps)
	}

	xmlResponse.WriteString("</D:multistatus>")
	w.Write([]byte(xmlResponse.String()))
}

func (s *Server) propfindSingleResource(xmlResp *strings.Builder, href string, isCalendar bool, requestedProps []xml.Name) {
	xmlResp.WriteString("  <D:response>\n")
	xmlResp.WriteString(fmt.Sprintf("    <D:href>%s</D:href>\n", href))

	var successProps []string
	var failedProps []string

	ctag, _ := s.cache.GetCtag()
	rev, _ := s.cache.GetRevision()

	userPath := s.basePath + "/u/" + s.proxyUser

	for _, name := range requestedProps {
		supported := isPropertySupported(name, isCalendar)
		if !supported {
			prefix := "D"
			if name.Space == "urn:ietf:params:xml:ns:caldav" {
				prefix = "C"
			} else if name.Space == "http://calendarserver.org/ns/" {
				prefix = "CS"
			} else if name.Space == "http://apple.com/ns/ical/" {
				prefix = "IC"
			}
			failedProps = append(failedProps, fmt.Sprintf("<%s:%s/>", prefix, name.Local))
			continue
		}

		// Calculate property XML representation
		propXML := ""
		switch name.Local {
		case "displayname":
			if isCalendar {
				propXML = "<D:displayname>WPS Calendar</D:displayname>"
			} else {
				propXML = fmt.Sprintf("<D:displayname>%s</D:displayname>", s.proxyUser)
			}
		case "resourcetype":
			if isCalendar {
				propXML = "<D:resourcetype><D:collection/><C:calendar/></D:resourcetype>"
			} else {
				propXML = "<D:resourcetype><D:collection/><D:principal/></D:resourcetype>"
			}
		case "current-user-principal":
			propXML = fmt.Sprintf("<D:current-user-principal><D:href>%s/</D:href></D:current-user-principal>", userPath)
		case "principal-URL":
			propXML = fmt.Sprintf("<D:principal-URL><D:href>%s/</D:href></D:principal-URL>", userPath)
		case "calendar-home-set":
			propXML = fmt.Sprintf("<C:calendar-home-set><D:href>%s/</D:href></C:calendar-home-set>", userPath)
		case "calendar-description":
			propXML = "<C:calendar-description>WPS Calendar Sync Proxy</C:calendar-description>"
		case "getctag":
			propXML = fmt.Sprintf("<CS:getctag>%s</CS:getctag>", ctag)
		case "sync-token":
			propXML = fmt.Sprintf("<D:sync-token>%d</D:sync-token>", rev)
		case "supported-calendar-component-set":
			propXML = "<C:supported-calendar-component-set><C:comp name=\"VEVENT\"/></C:supported-calendar-component-set>"
		case "calendar-color":
			propXML = "<IC:calendar-color>#4F46E5</IC:calendar-color>" // Sleek indigo
		case "calendar-order":
			propXML = "<IC:calendar-order>1</IC:calendar-order>"
		case "calendar-timezone":
			// Apple clients expect standard CST VTIMEZONE
			propXML = `<C:calendar-timezone>BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//WPS CalDAV Proxy//NONSGML Version 1.0//EN
BEGIN:VTIMEZONE
TZID:Asia/Shanghai
BEGIN:STANDARD
TZOFFSETFROM:+0800
TZOFFSETTO:+0800
TZNAME:CST
DTSTART:19700101T000000
END:STANDARD
END:VTIMEZONE
END:VCALENDAR</C:calendar-timezone>`
		}

		if propXML != "" {
			successProps = append(successProps, propXML)
		}
	}

	// 1. Write 200 OK propstat block
	if len(successProps) > 0 {
		xmlResp.WriteString("    <D:propstat>\n")
		xmlResp.WriteString("      <D:prop>\n")
		for _, prop := range successProps {
			xmlResp.WriteString("        " + prop + "\n")
		}
		xmlResp.WriteString("      </D:prop>\n")
		xmlResp.WriteString("      <D:status>HTTP/1.1 200 OK</D:status>\n")
		xmlResp.WriteString("    </D:propstat>\n")
	}

	// 2. Write 404 Not Found propstat block
	if len(failedProps) > 0 {
		xmlResp.WriteString("    <D:propstat>\n")
		xmlResp.WriteString("      <D:prop>\n")
		for _, prop := range failedProps {
			xmlResp.WriteString("        " + prop + "\n")
		}
		xmlResp.WriteString("      </D:prop>\n")
		xmlResp.WriteString("      <D:status>HTTP/1.1 404 Not Found</D:status>\n")
		xmlResp.WriteString("    </D:propstat>\n")
	}

	xmlResp.WriteString("  </D:response>\n")
}

func (s *Server) propfindCalendarEvents(xmlResp *strings.Builder, calendarPath string, requestedProps []xml.Name) {
	events, err := s.cache.GetAllEvents()
	if err != nil {
		return
	}

	for _, ev := range events {
		href := fmt.Sprintf("%s/%s.ics", calendarPath, ev.UID)
		xmlResp.WriteString("  <D:response>\n")
		xmlResp.WriteString(fmt.Sprintf("    <D:href>%s</D:href>\n", href))

		var successProps []string
		var failedProps []string

		for _, name := range requestedProps {
			supported := isPropertySupported(name, false)
			if !supported {
				prefix := "D"
				if name.Space == "urn:ietf:params:xml:ns:caldav" {
					prefix = "C"
				} else if name.Space == "http://calendarserver.org/ns/" {
					prefix = "CS"
				} else if name.Space == "http://apple.com/ns/ical/" {
					prefix = "IC"
				}
				failedProps = append(failedProps, fmt.Sprintf("<%s:%s/>", prefix, name.Local))
				continue
			}

			propXML := ""
			switch name.Local {
			case "getetag":
				propXML = fmt.Sprintf("<D:getetag>\"%s\"</D:getetag>", ev.ETag)
			case "getcontenttype":
				propXML = "<D:getcontenttype>text/calendar; component=VEVENT</D:getcontenttype>"
			case "getcontentlength":
				propXML = fmt.Sprintf("<D:getcontentlength>%d</D:getcontentlength>", len(ev.ICalData))
			}

			if propXML != "" {
				successProps = append(successProps, propXML)
			}
		}

		if len(successProps) > 0 {
			xmlResp.WriteString("    <D:propstat>\n")
			xmlResp.WriteString("      <D:prop>\n")
			for _, prop := range successProps {
				xmlResp.WriteString("        " + prop + "\n")
			}
			xmlResp.WriteString("      </D:prop>\n")
			xmlResp.WriteString("      <D:status>HTTP/1.1 200 OK</D:status>\n")
			xmlResp.WriteString("    </D:propstat>\n")
		}

		if len(failedProps) > 0 {
			xmlResp.WriteString("    <D:propstat>\n")
			xmlResp.WriteString("      <D:prop>\n")
			for _, prop := range failedProps {
				xmlResp.WriteString("        " + prop + "\n")
			}
			xmlResp.WriteString("      </D:prop>\n")
			xmlResp.WriteString("      <D:status>HTTP/1.1 404 Not Found</D:status>\n")
			xmlResp.WriteString("    </D:propstat>\n")
		}

		xmlResp.WriteString("  </D:response>\n")
	}
}
