package cache

import (
	"crypto/sha256"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

type Event struct {
	UID       string    `json:"uid"`
	Href      string    `json:"href"`
	ETag      string    `json:"etag"`
	ICalData  string    `json:"ical_data"`
	StartTime int64     `json:"start_time"` // Unix epoch timestamp
	EndTime   int64     `json:"end_time"`   // Unix epoch timestamp
	IsAllDay  bool      `json:"is_allday"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type ChangeLogEntry struct {
	ID        int64     `json:"id"`
	Revision  int64     `json:"revision"`
	Action    string    `json:"action"` // "set" (created/updated) or "delete"
	Href      string    `json:"href"`
	UID       string    `json:"uid"`
	Timestamp time.Time `json:"timestamp"`
}

type MergeStats struct {
	Created int
	Updated int
	Deleted int
}

type Cache struct {
	db   *sql.DB
	mu   sync.RWMutex
	ctag string
	rev  int64
}

func New(dbPath string) (*Cache, error) {
	// Create directory if not exists
	dir := filepath.Dir(dbPath)
	if dir != "." && dir != "" {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return nil, fmt.Errorf("create db directory: %w", err)
		}
	}

	// Open modernc sqlite using pure Go driver "sqlite"
	// Enable WAL and a decent busy timeout
	db, err := sql.Open("sqlite", dbPath+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open sqlite db: %w", err)
	}

	// SQLite WAL mode performs best with single writer / limited pool
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)

	c := &Cache{db: db}

	if err := c.migrate(); err != nil {
		db.Close()
		return nil, fmt.Errorf("db migration failed: %w", err)
	}

	if err := c.loadMeta(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to load meta keys: %w", err)
	}

	return c, nil
}

func (c *Cache) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.db.Close()
}

func (c *Cache) migrate() error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS events (
			uid TEXT PRIMARY KEY,
			href TEXT NOT NULL,
			etag TEXT NOT NULL,
			ical_data TEXT NOT NULL,
			start_time INTEGER,
			end_time INTEGER,
			is_allday INTEGER DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE INDEX IF NOT EXISTS idx_events_time ON events(start_time, end_time)`,
		`CREATE INDEX IF NOT EXISTS idx_events_href ON events(href)`,
		
		`CREATE TABLE IF NOT EXISTS meta (
			key TEXT PRIMARY KEY,
			value TEXT NOT NULL
		)`,
		`INSERT OR IGNORE INTO meta (key, value) VALUES ('ctag', '')`,
		`INSERT OR IGNORE INTO meta (key, value) VALUES ('revision', '0')`,

		`CREATE TABLE IF NOT EXISTS change_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			revision INTEGER NOT NULL,
			action TEXT NOT NULL,
			href TEXT NOT NULL,
			uid TEXT NOT NULL,
			timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE INDEX IF NOT EXISTS idx_changelog_revision ON change_log(revision)`,
	}

	for _, stmt := range stmts {
		if _, err := c.db.Exec(stmt); err != nil {
			return fmt.Errorf("execute stmt %q: %w", stmt, err)
		}
	}
	return nil
}

func (c *Cache) loadMeta() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	var ctag string
	err := c.db.QueryRow(`SELECT value FROM meta WHERE key = 'ctag'`).Scan(&ctag)
	if err != nil && err != sql.ErrNoRows {
		return err
	}
	c.ctag = ctag

	var revStr string
	err = c.db.QueryRow(`SELECT value FROM meta WHERE key = 'revision'`).Scan(&revStr)
	if err != nil && err != sql.ErrNoRows {
		return err
	}
	if revStr != "" {
		fmt.Sscanf(revStr, "%d", &c.rev)
	}

	return nil
}

func (c *Cache) GetCtag() (string, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.ctag, nil
}

func (c *Cache) GetRevision() (int64, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.rev, nil
}

func (c *Cache) GetAllEvents() ([]*Event, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	rows, err := c.db.Query(`SELECT uid, href, etag, ical_data, start_time, end_time, is_allday, created_at, updated_at FROM events ORDER BY uid`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []*Event
	for rows.Next() {
		var ev Event
		var isAllDayInt int
		err := rows.Scan(&ev.UID, &ev.Href, &ev.ETag, &ev.ICalData, &ev.StartTime, &ev.EndTime, &isAllDayInt, &ev.CreatedAt, &ev.UpdatedAt)
		if err != nil {
			return nil, err
		}
		ev.IsAllDay = (isAllDayInt != 0)
		events = append(events, &ev)
	}
	return events, nil
}

func (c *Cache) GetEvent(uid string) (*Event, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var ev Event
	var isAllDayInt int
	err := c.db.QueryRow(`SELECT uid, href, etag, ical_data, start_time, end_time, is_allday, created_at, updated_at FROM events WHERE uid = ?`, uid).
		Scan(&ev.UID, &ev.Href, &ev.ETag, &ev.ICalData, &ev.StartTime, &ev.EndTime, &isAllDayInt, &ev.CreatedAt, &ev.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	ev.IsAllDay = (isAllDayInt != 0)
	return &ev, nil
}

func (c *Cache) GetEventByHref(href string) (*Event, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var ev Event
	var isAllDayInt int
	err := c.db.QueryRow(`SELECT uid, href, etag, ical_data, start_time, end_time, is_allday, created_at, updated_at FROM events WHERE href = ?`, href).
		Scan(&ev.UID, &ev.Href, &ev.ETag, &ev.ICalData, &ev.StartTime, &ev.EndTime, &isAllDayInt, &ev.CreatedAt, &ev.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	ev.IsAllDay = (isAllDayInt != 0)
	return &ev, nil
}

func (c *Cache) GetEventsInTimeRange(start, end int64) ([]*Event, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	// An event overlaps if: event.start_time <= range.end AND event.end_time >= range.start
	rows, err := c.db.Query(`
		SELECT uid, href, etag, ical_data, start_time, end_time, is_allday, created_at, updated_at 
		FROM events 
		WHERE start_time <= ? AND end_time >= ? 
		ORDER BY uid`, end, start)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []*Event
	for rows.Next() {
		var ev Event
		var isAllDayInt int
		err := rows.Scan(&ev.UID, &ev.Href, &ev.ETag, &ev.ICalData, &ev.StartTime, &ev.EndTime, &isAllDayInt, &ev.CreatedAt, &ev.UpdatedAt)
		if err != nil {
			return nil, err
		}
		ev.IsAllDay = (isAllDayInt != 0)
		events = append(events, &ev)
	}
	return events, nil
}

func (c *Cache) GetChangesSince(revision int64) ([]*ChangeLogEntry, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	rows, err := c.db.Query(`
		SELECT id, revision, action, href, uid, timestamp 
		FROM change_log 
		WHERE revision > ? 
		ORDER BY id`, revision)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var logs []*ChangeLogEntry
	for rows.Next() {
		var entry ChangeLogEntry
		err := rows.Scan(&entry.ID, &entry.Revision, &entry.Action, &entry.Href, &entry.UID, &entry.Timestamp)
		if err != nil {
			return nil, err
		}
		logs = append(logs, &entry)
	}
	return logs, nil
}

func (c *Cache) MergeEvents(remoteEvents []*Event) (*MergeStats, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	tx, err := c.db.Begin()
	if err != nil {
		return nil, fmt.Errorf("begin transaction: %w", err)
	}
	defer tx.Rollback()

	// 1. Load existing event hashes to do change detection
	rows, err := tx.Query(`SELECT uid, href, etag FROM events`)
	if err != nil {
		return nil, fmt.Errorf("query existing events: %w", err)
	}
	existing := make(map[string]*Event) // key: uid
	for rows.Next() {
		var ev Event
		if err := rows.Scan(&ev.UID, &ev.Href, &ev.ETag); err != nil {
			rows.Close()
			return nil, fmt.Errorf("scan existing: %w", err)
		}
		existing[ev.UID] = &ev
	}
	rows.Close()

	// 2. Identify created, updated, and deleted
	var created []*Event
	var updated []*Event
	var deleted []string

	incomingUIDs := make(map[string]bool)

	// Single writer prepared statements
	upsertStmt, err := tx.Prepare(`
		INSERT OR REPLACE INTO events(uid, href, etag, ical_data, start_time, end_time, is_allday, updated_at) 
		VALUES(?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`)
	if err != nil {
		return nil, fmt.Errorf("prepare upsert: %w", err)
	}
	defer upsertStmt.Close()

	for _, rem := range remoteEvents {
		incomingUIDs[rem.UID] = true
		isAllDayVal := 0
		if rem.IsAllDay {
			isAllDayVal = 1
		}

		local, exists := existing[rem.UID]
		if !exists {
			created = append(created, rem)
		} else if local.ETag != rem.ETag || local.Href != rem.Href {
			updated = append(updated, rem)
		}

		_, err := upsertStmt.Exec(rem.UID, rem.Href, rem.ETag, rem.ICalData, rem.StartTime, rem.EndTime, isAllDayVal)
		if err != nil {
			return nil, fmt.Errorf("upsert event %s: %w", rem.UID, err)
		}
	}

	for uid, local := range existing {
		if !incomingUIDs[uid] {
			deleted = append(deleted, uid)
			if _, err := tx.Exec(`DELETE FROM events WHERE uid = ?`, uid); err != nil {
				return nil, fmt.Errorf("delete event %s: %w", uid, err)
			}
			// Record deletion in change log
			if err := c.writeChangeLog(tx, c.rev+1, "delete", local.Href, local.UID); err != nil {
				return nil, fmt.Errorf("write delete log: %w", err)
			}
		}
	}

	changed := len(created) > 0 || len(updated) > 0 || len(deleted) > 0

	if changed {
		nextRev := c.rev + 1

		// Record created events in change log
		for _, ev := range created {
			if err := c.writeChangeLog(tx, nextRev, "set", ev.Href, ev.UID); err != nil {
				return nil, fmt.Errorf("write create log: %w", err)
			}
		}
		// Record updated events in change log
		for _, ev := range updated {
			if err := c.writeChangeLog(tx, nextRev, "set", ev.Href, ev.UID); err != nil {
				return nil, fmt.Errorf("write update log: %w", err)
			}
		}

		// Recompute stable ctag
		newCtag, err := c.recalcCtag(tx)
		if err != nil {
			return nil, fmt.Errorf("recalc ctag: %w", err)
		}

		// Update revision metadata
		if _, err := tx.Exec(`UPDATE meta SET value = ? WHERE key = 'revision'`, fmt.Sprintf("%d", nextRev)); err != nil {
			return nil, fmt.Errorf("update revision: %w", err)
		}

		c.ctag = newCtag
		c.rev = nextRev
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit merge transaction: %w", err)
	}

	return &MergeStats{
		Created: len(created),
		Updated: len(updated),
		Deleted: len(deleted),
	}, nil
}

func (c *Cache) writeChangeLog(tx *sql.Tx, rev int64, action, href, uid string) error {
	_, err := tx.Exec(`
		INSERT INTO change_log(revision, action, href, uid) 
		VALUES(?, ?, ?, ?)`, rev, action, href, uid)
	return err
}

func (c *Cache) recalcCtag(tx *sql.Tx) (string, error) {
	rows, err := tx.Query(`SELECT etag FROM events ORDER BY etag`)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	var etags []string
	for rows.Next() {
		var etag string
		if err := rows.Scan(&etag); err != nil {
			return "", err
		}
		etags = append(etags, etag)
	}

	sort.Strings(etags)
	hash := sha256.Sum256([]byte(strings.Join(etags, "\n")))
	ctag := fmt.Sprintf("%x", hash)

	_, err = tx.Exec(`UPDATE meta SET value = ? WHERE key = 'ctag'`, ctag)
	if err != nil {
		return "", err
	}

	return ctag, nil
}
