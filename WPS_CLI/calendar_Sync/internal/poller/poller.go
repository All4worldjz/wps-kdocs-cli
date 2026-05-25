package poller

import (
	"fmt"
	"log"
	"time"

	"wps-caldav-proxy/internal/cache"
	"wps-caldav-proxy/internal/wpsclient"
)

type wpsClient interface {
	FetchEvents() ([]wpsclient.EventInfo, error)
	Discover() error
}

type Poller struct {
	wpsClient wpsClient
	cache     *cache.Cache
	interval  time.Duration
	stopCh    chan struct{}
}

func New(client wpsClient, c *cache.Cache, intervalSeconds int) *Poller {
	return &Poller{
		wpsClient: client,
		cache:     c,
		interval:  time.Duration(intervalSeconds) * time.Second,
		stopCh:    make(chan struct{}),
	}
}

func (p *Poller) RunOnce() {
	log.Printf("[Poller] Performing initial synchronization...")
	if err := p.SyncOnce(); err != nil {
		log.Printf("[Poller] Initial sync failed/halted: %v", err)
	} else {
		log.Printf("[Poller] Initial synchronization successful.")
	}
}

func (p *Poller) Start() {
	log.Printf("[Poller] Starting background sync loop every %v...", p.interval)
	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if err := p.SyncOnce(); err != nil {
				log.Printf("[Poller] Background sync error: %v", err)
			}
		case <-p.stopCh:
			log.Printf("[Poller] Background sync loop stopped.")
			return
		}
	}
}

func (p *Poller) Stop() {
	close(p.stopCh)
}

func (p *Poller) SyncOnce() error {
	remoteEvents, err := p.wpsClient.FetchEvents()
	if err != nil {
		return fmt.Errorf("fetch remote wps events: %w", err)
	}

	localEvents, err := p.cache.GetAllEvents()
	if err != nil {
		return fmt.Errorf("query local cache: %w", err)
	}

	// Fail-Safe / Wiping protection:
	// If remote returns 0 events, but local cache contains events,
	// do NOT perform the merge! Wiping the cache on a transient failure or
	// API change would cause client devices to delete all their local events.
	if len(remoteEvents) == 0 && len(localEvents) > 0 {
		log.Printf("[Poller] WARNING: Remote WPS server returned 0 events, but local cache contains %d events! Keep-Stale wiping protection triggered. Sync aborted.", len(localEvents))
		return fmt.Errorf("wiping protection triggered: empty remote calendar returned")
	}

	// Convert wpsclient.EventInfo to cache.Event
	var eventsToMerge []*cache.Event
	for _, re := range remoteEvents {
		eventsToMerge = append(eventsToMerge, &cache.Event{
			UID:       re.UID,
			Href:      re.Href,
			ETag:      re.ETag,
			ICalData:  re.ICalData,
			StartTime: re.StartTime,
			EndTime:   re.EndTime,
			IsAllDay:  re.IsAllDay,
		})
	}

	stats, err := p.cache.MergeEvents(eventsToMerge)
	if err != nil {
		return fmt.Errorf("merge cache: %w", err)
	}

	if stats.Created > 0 || stats.Updated > 0 || stats.Deleted > 0 {
		log.Printf("[Poller] Merge complete: +%d created, ~%d updated, -%d deleted.", stats.Created, stats.Updated, stats.Deleted)
	}

	return nil
}
