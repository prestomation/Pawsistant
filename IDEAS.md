# IDEAS.md — Pawsistant (ha-doglog)

## Future Features

- **Update event service** — `doglog.update_event` to edit notes/values on existing events without delete+recreate
- **Event history panel** — custom Lovelace card showing a scrollable timeline of recent events
- **Prediction engine** — based on historical patterns, predict when the dog will need to go out next (like the community potty training blueprint but data-driven)
- **Multi-dog dashboard generator** — auto-generate dashboard cards for all dogs in a pack
- **Export service** — `doglog.export_events` to dump events as CSV/JSON for external analysis
- **Statistics integration** — feed weight/medicine data into HA's long-term statistics for native history graphs
- **Photo attachments** — attach a photo to an event (stored in /config/www/doglog/)
- **Vet visit event type** — dedicated type with fields for vet name, diagnosis, cost
- **Recurring medicine reminders** — per-medicine schedules (e.g., Simparica Trio every 30 days) instead of one global threshold
