package caldavserver

import (
	"encoding/base64"
	"fmt"
	"log"
	"net/http"
	"strings"

	"wps-caldav-proxy/internal/cache"
)

type Server struct {
	cache     *cache.Cache
	proxyUser string
	proxyPass string
	basePath  string
}

func New(c *cache.Cache, proxyUser, proxyPass, basePath string) *Server {
	return &Server{
		cache:     c,
		proxyUser: proxyUser,
		proxyPass: proxyPass,
		basePath:  strings.TrimRight(basePath, "/"),
	}
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// 1. Enforce Basic Authentication
	if !s.checkAuth(r) {
		w.Header().Set("WWW-Authenticate", `Basic realm="WPS CalDAV Proxy"`)
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	log.Printf("[CalDAV] %s %s", r.Method, r.URL.Path)

	// Clean up paths by resolving any trailing slash redirections internally
	path := strings.TrimRight(r.URL.Path, "/")
	if path == "" {
		path = "/"
	}

	switch r.Method {
	case "OPTIONS":
		s.handleOptions(w)
	case "PROPFIND":
		s.handlePropfind(w, r)
	case "REPORT":
		s.handleReport(w, r)
	case "GET":
		s.handleGet(w, r)
	case "MKCALENDAR":
		w.Header().Set("Content-Type", "text/xml; charset=utf-8")
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`<?xml version="1.0" encoding="utf-8" ?>
<D:error xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <C:initialize-calendar-collection-allowed/>
</D:error>`))
	default:
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
	}
}

func (s *Server) checkAuth(r *http.Request) bool {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Basic ") {
		return false
	}
	payload, err := base64.StdEncoding.DecodeString(auth[6:])
	if err != nil {
		return false
	}
	parts := strings.SplitN(string(payload), ":", 2)
	if len(parts) != 2 {
		return false
	}
	return parts[0] == s.proxyUser && parts[1] == s.proxyPass
}

func (s *Server) handleOptions(w http.ResponseWriter) {
	w.Header().Set("DAV", "1, 2, 3, calendar-access, calendar-proxy")
	w.Header().Set("Allow", "OPTIONS, PROPFIND, REPORT, GET, MKCALENDAR")
	w.WriteHeader(http.StatusOK)
}

func (s *Server) handleGet(w http.ResponseWriter, r *http.Request) {
	// GET expects /u/caldav/default/xxx.ics
	// Extract the event UID
	path := r.URL.Path
	if !strings.HasSuffix(path, ".ics") {
		http.Error(w, "Not Found", http.StatusNotFound)
		return
	}

	parts := strings.Split(strings.TrimSuffix(path, ".ics"), "/")
	if len(parts) < 2 {
		http.Error(w, "Not Found", http.StatusNotFound)
		return
	}
	uid := parts[len(parts)-1]

	ev, err := s.cache.GetEvent(uid)
	if err != nil {
		http.Error(w, "Internal DB error", http.StatusInternalServerError)
		return
	}
	if ev == nil {
		http.Error(w, "Event not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "text/calendar; component=VEVENT; charset=utf-8")
	w.Header().Set("ETag", fmt.Sprintf(`"%s"`, ev.ETag))
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(ev.ICalData))
}

func (s *Server) ListenAndServe(addr string) error {
	log.Printf("[Server] Starting CalDAV Proxy Gateway on %s", addr)
	log.Printf("[Server] Authorized User: %s, BasePath: %s", s.proxyUser, s.basePath)
	return http.ListenAndServe(addr, s)
}
