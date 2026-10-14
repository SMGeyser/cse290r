# CAL-1 — Canvas Coursework to Google Calendar Sync

> Implementation plan. Source: user-requested feature; structure based on [`_TEMPLATE.md`](_TEMPLATE.md).

## Metadata

| Field | Value |
|---|---|
| **Feature ID** | CAL-1 |
| **Section** | Student Productivity & Integrations |
| **Severity** | MAJOR |
| **Markets** | K12 / HE / HS |
| **Status (today)** | MISSING |
| **Estimated effort** | L (1–2 months) for a production service; M (2–4 weeks) for a single-user prototype |
| **Owner (proposed)** | Integrations team, with Identity and Privacy review |
| **Depends on** | OAuth callback support, encrypted secret storage, durable job queue, and persistent sync-state storage; feature IDs TBD |
| **Unblocks** | A common calendar-provider framework and future Outlook support; feature IDs TBD |

---

## 1. Problem Statement

Students often plan their time in Google Calendar, while their authoritative coursework and due dates live in Canvas. Copying assignments by hand is slow and becomes inaccurate when an instructor renames an assignment, changes its due date, applies a student-specific override, or removes it. Canvas offers an iCal feed today, but a first-class opt-in integration can add guided setup, course selection, faster deterministic reconciliation, visible sync health, and safe cleanup of only the events it owns.

## 2. Goals

- Let an eligible student explicitly connect a Google account and enable a one-way coursework sync.
- Represent every selected, visible Canvas assignment with an effective due date as one Google Calendar event at the correct due date and time.
- Include the course and assignment name plus a working link back to the Canvas coursework.
- Keep managed events accurate when Canvas assignments are added, renamed, rescheduled, unpublished, deleted, or no longer visible to the student.
- Give students clear course controls, sync status, recovery actions, and disconnect/cleanup choices.
- Meet production expectations for security, privacy, accessibility, reliability, and rate-limit handling.

## 3. Non-Goals

- Bidirectional editing; changes made in Google Calendar will not modify Canvas.
- Assignment submission, grading, grade display, or submission-status synchronization.
- Copying full assignment descriptions, attachments, rubrics, student work, or instructor feedback into Google.
- Syncing undated assignments, announcements, course meetings, appointments, or non-assignment Canvas calendar events in the MVP.
- Syncing to Outlook, Apple Calendar, a parent/observer calendar, or a shared instructor calendar in the MVP.
- Creating study blocks, estimating work duration, or using AI to schedule coursework.
- Replacing the existing Canvas iCal feed for users who prefer a read-only subscription.

## 4. Personas & User Stories

The feature should be delivered as the following sequenced stories rather than as one large release item.

| Story | Persona | User story | Outcome |
|---|---|---|---|
| **CAL-1A — Connect Google Calendar** | Student | As a student, I want to securely connect or disconnect my Google account so that Canvas can manage coursework events only with my consent. | OAuth connection, dedicated calendar, encrypted credentials, and revocation flow. |
| **CAL-1B — Choose coursework to sync** | Student | As a student, I want to choose which active courses are synced so that only relevant coursework appears in Google Calendar. | Course-selection UI, timezone handling, and saved preferences. |
| **CAL-1C — Run the initial sync** | Student | As a student, I want my dated assignments and Canvas links added without duplicates so that my calendar becomes useful immediately. | Normalization, event creation, pagination, and stable mappings. |
| **CAL-1D — Keep events current** | Student | As a student, I want Canvas changes reflected automatically so that I do not act on stale deadlines. | Scheduled reconciliation, patch/delete behavior, idempotency, and retry handling. |
| **CAL-1E — Understand and recover sync** | Student | As a student, I want to see sync status and actionable errors so that I can reconnect or retry without losing unrelated calendar data. | Status UI, manual sync, partial-failure reporting, and lifecycle controls. |
| **CAL-1F — Govern availability** | Institution admin | As an administrator, I want to enable or disable the integration for my institution so that local privacy and Google Workspace policies are respected. | Tenant policy control and aggregate operational status without exposing student coursework. |

Parent/observer and instructor-owned calendar flows are not included in the MVP. Homeschool students use the same student-owned flow; an adult-managed or observer flow requires a separate privacy and authorization design.

## 5. Functional Requirements

- **FR-1.** The system MUST expose the integration only when both the global feature flag and the institution-level policy allow it.
- **FR-2.** The system MUST require an explicit student action before beginning Google OAuth and MUST NOT create or modify an event before consent succeeds.
- **FR-3.** The OAuth flow MUST use the authorization-code flow with `state`, PKCE where supported, offline access, and the narrowest viable Google scope. The recommended MVP scope is `https://www.googleapis.com/auth/calendar.app.created` with a dedicated secondary calendar named **Canvas Coursework**.
- **FR-4.** The system MUST encrypt Google refresh tokens at rest, MUST NOT expose them to the browser after the callback, MUST redact them from logs, and MUST revoke or delete stored credentials when the connection is removed.
- **FR-5.** The system MUST let the student enable or disable each active Canvas course. Newly enrolled courses SHOULD remain off until the student confirms them, unless the student has explicitly enabled an “automatically include new courses” preference.
- **FR-6.** The source reader MUST retrieve all pages of visible, published assignments for each selected course and MUST use the due date effective for the current student, including section, group, or individual overrides.
- **FR-7.** An assignment without an effective `due_at` MUST NOT create an event and MUST be counted as “skipped: no due date” in the sync summary.
- **FR-8.** A managed Google event MUST contain only the minimum useful coursework data:
  - Summary: `[{course code or short name}] {assignment name}`.
  - Start: the exact effective Canvas due instant. For a Canvas all-day assignment, use the Canvas all-day date.
  - End: 15 minutes after a timed due instant; for an all-day event, the exclusive end date is the following day.
  - Description/source: a short localized label and the Canvas `html_url` deep link.
  - Visibility: Google account default; no attendees.
  - Transparency: `transparent`, so a deadline does not mark the student as busy.
- **FR-9.** The system MUST NOT copy grades, submission content, instructor comments, or the full HTML assignment description into Google Calendar.
- **FR-10.** Exactly one Google event MUST exist for a given connection, Canvas tenant, Canvas user, course, and assignment. The identity MUST be stored both in the local mapping and in Google private extended properties. The writer SHOULD also derive a Google-compatible deterministic event ID from that stable identity so an ambiguous create retry can recover with get/update rather than duplicate the event.
- **FR-11.** The initial sync MUST run asynchronously after setup and MUST be safe to retry after interruption.
- **FR-12.** The system MUST support a user-triggered **Sync now** action and SHOULD run scheduled synchronization at least every 15 minutes while the connection is healthy.
- **FR-13.** When a synced assignment’s name, effective due date, course label, all-day status, or Canvas link changes, the next successful run MUST update the existing Google event rather than create a replacement. Writes SHOULD use ETag preconditions or an equivalent conflict check so concurrent changes are detected rather than silently lost.
- **FR-14.** When a synced assignment is deleted, unpublished, loses its due date, is no longer visible/assigned to the student, or its course is deselected, the next complete successful reconciliation MUST delete only its managed Google event. A partial or failed Canvas scan MUST NOT trigger deletions.
- **FR-15.** Submitting or completing an assignment MUST NOT remove its event in the MVP; the deadline remains useful calendar history.
- **FR-16.** Canvas MUST remain the source of truth for managed fields. While sync is enabled, edits to those fields in Google MAY be overwritten and a manually deleted managed event MAY be recreated on the next run. The setup UI MUST disclose this behavior.
- **FR-17.** Every sync operation MUST be idempotent. Transient Canvas or Google `429` and `5xx` responses MUST use bounded exponential backoff with jitter and MUST honor `Retry-After` when present. Canvas request-cost/remaining-limit headers and Google per-project/per-user quota signals SHOULD shape concurrency proactively.
- **FR-18.** The integration page MUST display connection state, selected courses, last attempt, last successful sync, next scheduled run, counts for created/updated/deleted/skipped items, and an actionable error when attention is required.
- **FR-19.** If Google access is revoked or blocked by a Workspace administrator, the system MUST pause future syncs, preserve existing events, and prompt the student to reconnect. It MUST NOT repeatedly retry an authorization failure.
- **FR-20.** Disconnect MUST stop scheduled jobs immediately and offer two explicit choices: keep the existing Canvas Coursework calendar as a static snapshot, or remove the integration-created calendar and its managed events. Unrelated calendars and events MUST never be deleted.
- **FR-21.** Event writes MUST use `sendUpdates=none` and MUST NOT add guests or generate invitation emails.
- **FR-22.** Institution administrators MUST be able to disable new connections and pause existing connections. The admin view MUST expose aggregate health only, not assignment titles or due dates.
- **FR-23.** Setup MUST explain that enabling this integration while an existing Canvas iCal subscription is active can show duplicate coursework and MUST link to instructions for removing the older subscription.

## 6. Non-Functional Requirements

- **Performance** — Settings reads and writes SHOULD complete at p95 under 300 ms, excluding third-party redirects. A manual sync request SHOULD acknowledge within 2 seconds and continue in the background. An initial sync of 500 assignments SHOULD complete within 2 minutes under normal API conditions.
- **Security** — Use OAuth 2.0 authorization code, `state`, PKCE where supported, HTTPS-only callbacks, encrypted refresh tokens, key rotation, CSRF protection, strict redirect URI allowlists, and least-privilege scopes. Never accept Google tokens through query parameters or logs.
- **Privacy & Compliance** — Treat assignment names, courses, links, and due dates as education records. Complete FERPA, COPPA/age-appropriate consent, GDPR deletion/export, institutional Google Workspace, and vendor-risk review before GA. Retain only data needed for synchronization.
- **Accessibility** — All integration UI MUST conform to WCAG 2.2 AA, including keyboard-only operation, visible focus, programmatic status announcements, non-color error indicators, and accessible OAuth return states.
- **Scalability** — Partition work by connection/user, bound concurrency per Canvas tenant and Google project, batch selected Canvas course contexts when required, and apply queue backpressure rather than dropping runs.
- **Reliability** — Target 99.9% monthly availability for settings and job submission. At least 95% of source changes SHOULD appear in Google within 20 minutes and 99% within 60 minutes, excluding provider outages or revoked access.
- **Observability** — Record correlation ID, connection ID, tenant ID, provider response class, run phase, attempt number, duration, and item counts. Never log tokens, assignment names, links, or student-identifying calendar content. Alert on freshness, auth-failure, quota, and deletion-spike thresholds.
- **Maintainability** — Isolate Canvas normalization from Google event projection, use a provider interface for future calendar integrations, and document ownership of the worker, OAuth client, migrations, and runbook.
- **Internationalization** — Externalize all copy, preserve RFC 3339 instants and IANA time zones, handle daylight-saving transitions, and use the student’s locale only for display—not for persisted timestamps.
- **Backward compatibility** — The feature is opt-in and MUST NOT change Canvas assignments, the native Canvas calendar, existing iCal feeds, or users without a connection. Schema changes MUST be additive for the initial release.

## 7. Acceptance Criteria

- **AC-1.** *Given* an eligible student with no connection, *when* they choose **Connect Google Calendar**, *then* OAuth consent starts and no Google calendar or event is written until the callback succeeds.
- **AC-2.** *Given* successful consent, *when* setup completes, *then* one dedicated **Canvas Coursework** calendar is created and the connection is stored without exposing the refresh token to the client.
- **AC-3.** *Given* a selected course with one published, visible assignment that has a due date, *when* the initial sync completes, *then* exactly one transparent event is created at the same instant with the course, assignment name, and a working HTTPS Canvas link.
- **AC-4.** *Given* a Canvas assignment marked all-day, *when* it is synced, *then* Google displays an all-day event on the same Canvas calendar date with the correct exclusive end date.
- **AC-5.** *Given* a student-specific due-date override or a due date across a daylight-saving transition, *when* the assignment is synced, *then* Google represents the same effective instant/date that Canvas shows that student.
- **AC-6.** *Given* unchanged source data, *when* synchronization runs repeatedly, *then* the same Google event ID remains, no duplicate appears, and subsequent runs report zero writes.
- **AC-7.** *Given* Canvas changes a synced assignment’s title, due date, or link, *when* the next sync succeeds, *then* the existing Google event is patched within the freshness target.
- **AC-8.** *Given* an assignment is unpublished, deleted, no longer visible, loses its due date, or belongs to a newly deselected course, *when* a complete source scan succeeds, *then* only the corresponding managed event is removed.
- **AC-9.** *Given* a Canvas scan fails or ends before all pages are read, *when* reconciliation stops, *then* no absence-based event deletions occur and the run is marked partial/failed.
- **AC-10.** *Given* an assignment has no due date, *when* sync completes, *then* no event is created and the summary increments the no-due-date skipped count.
- **AC-11.** *Given* a student submits an assignment, *when* the next sync runs, *then* its existing deadline event remains.
- **AC-12.** *Given* more assignments than fit on one Canvas response page, *when* sync runs, *then* every page is followed and every eligible assignment is represented once.
- **AC-13.** *Given* Google returns a transient quota or server error after some writes, *when* the job retries, *then* it resumes idempotently without duplicate events.
- **AC-14.** *Given* a revoked token or a Workspace policy block, *when* sync runs, *then* it pauses, keeps existing events, redacts credentials, and shows one actionable reconnect message.
- **AC-15.** *Given* a student disconnects and selects **Remove synced calendar**, *when* cleanup succeeds, *then* only the integration-created calendar/events and stored credentials are removed. Selecting **Keep calendar** leaves a static snapshot.
- **AC-16.** *Given* an institution administrator disables the feature, *when* a student opens settings, *then* no new connection can be created and the UI explains that the institution controls availability.
- **AC-17.** *Given* a keyboard or screen-reader user, *when* they connect, choose courses, run a sync, encounter an error, or disconnect, *then* every action and state change is operable and announced without relying on color.
- **AC-18.** *Given* the setup screen, *when* the student reviews prerequisites, *then* it warns about duplicate events from an existing Canvas iCal subscription and links to removal guidance.

## 8. Data Model

Names are proposed because this repository does not contain the production application or its migration conventions.

### `calendar_connections`

| Column | Notes |
|---|---|
| `id` | UUID primary key. |
| `user_id` | Canvas user foreign key; unique with `provider` for MVP. |
| `provider` | Enum; initially `google`. |
| `provider_subject_id` | Stable Google account subject, encrypted or access-controlled. |
| `encrypted_refresh_token` | Envelope-encrypted secret; never returned through the API. |
| `granted_scopes` | Normalized scope set for permission checks. |
| `status` | `pending`, `active`, `paused`, `reauth_required`, `disconnecting`, `disconnected`. |
| `external_calendar_id` | Dedicated Google calendar ID. |
| `last_attempt_at`, `last_success_at`, `last_error_code` | Health state without coursework content. |
| `created_at`, `updated_at`, `disconnected_at` | Audit timestamps. |

### `calendar_sync_preferences`

| Column | Notes |
|---|---|
| `connection_id` | Primary/foreign key to `calendar_connections`. |
| `enabled` | Master sync toggle. |
| `timezone` | IANA zone used for display and all-day interpretation. |
| `auto_include_new_courses` | Defaults to `false`. |
| `disconnect_cleanup_default` | Optional remembered preference; UI still confirms destructive cleanup. |

### `calendar_sync_courses`

| Column | Notes |
|---|---|
| `connection_id`, `canvas_course_id` | Composite primary key. |
| `enabled` | Course-level selection. |
| `course_label_snapshot` | Minimal cached label used to detect event-title changes. |

### `calendar_event_mappings`

| Column | Notes |
|---|---|
| `connection_id`, `canvas_tenant_id`, `canvas_course_id`, `canvas_assignment_id` | Composite unique source identity. |
| `google_event_id` | Unique within the connection/calendar. |
| `source_updated_at` | Last Canvas version observed. |
| `source_fingerprint` | Hash of managed fields for no-op detection. |
| `last_seen_run_id`, `last_synced_at` | Safe absence reconciliation and audit. |
| `state` | `active`, `delete_pending`, `deleted`, `error`. |

### `calendar_sync_runs`

Store run ID, connection ID, trigger, start/end timestamps, status, page/item counts, write counts, retry count, and non-sensitive error code. Apply a short operational retention period (for example 30–90 days) and aggregate older metrics.

Required constraints include one active Google connection per Canvas user for MVP, one source assignment mapping per connection, and one mapped Google event per connection. Add indexes for runnable connections, stale `last_success_at`, and mapping lookup. Migration filenames MUST follow the implementation repository’s established convention; no convention exists in this planning repository. No backfill is required because the feature is opt-in.

## 9. API Surface

The following routes are proposed and MUST be aligned with the production application’s established routing/versioning conventions.

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /api/v1/integrations/google-calendar` | Current Canvas user | Return eligibility, connection/status, preferences, selected courses, and last run summary. |
| `POST /api/v1/integrations/google-calendar/oauth/start` | Current Canvas user + CSRF | Create a short-lived OAuth transaction and return/redirect to the Google authorization URL. |
| `GET /oauth/google-calendar/callback` | Valid OAuth `state` + PKCE verifier | Exchange the authorization code, create/reuse the dedicated calendar, and redirect to settings. |
| `PATCH /api/v1/integrations/google-calendar/preferences` | Connection owner | Change enabled courses, timezone, and automatic-course preference. |
| `POST /api/v1/integrations/google-calendar/sync` | Connection owner; rate-limited | Enqueue a manual sync and return `202 Accepted` with a run ID. |
| `GET /api/v1/integrations/google-calendar/runs/:run_id` | Connection owner | Return non-sensitive run state and item counts. |
| `DELETE /api/v1/integrations/google-calendar` | Connection owner + recent-auth/CSRF | Disconnect, with `cleanup=keep` or `cleanup=remove_managed`. |
| `PATCH /api/v1/admin/integrations/google-calendar` | Institution admin | Enable, pause, or disable the tenant policy. |

Example preferences request:

```json
{
  "enabled": true,
  "courseIds": [123, 456],
  "autoIncludeNewCourses": false,
  "timezone": "America/Denver"
}
```

Example status response:

```json
{
  "eligible": true,
  "connectionState": "active",
  "calendarName": "Canvas Coursework",
  "selectedCourseIds": [123, 456],
  "lastAttemptAt": "2026-09-22T16:30:00Z",
  "lastSuccessAt": "2026-09-22T16:30:07Z",
  "nextScheduledAt": "2026-09-22T16:45:00Z",
  "lastRun": {
    "status": "succeeded",
    "created": 2,
    "updated": 1,
    "deleted": 0,
    "skippedNoDueDate": 3
  },
  "actionRequired": null
}
```

Manual sync SHOULD be limited to one queued/running job per connection and one new request per minute. All routes and schemas require OpenAPI documentation. No public WebSocket contract is required for MVP; the UI may poll a run endpoint, while an internal `calendar_sync.status_changed` event can update notifications/metrics.

## 10. UI / UX

### Pages and components

- Add **Settings → Integrations → Google Calendar** for students.
- Add a connection card with availability, connected Google account, dedicated calendar name, and privacy summary.
- Add a searchable active-course checklist, **Automatically include new courses**, **Sync now**, **Pause**, and **Disconnect** controls.
- Add a compact status panel showing last success, next run, result counts, and one primary recovery action.
- Add an institution policy control to the existing admin feature settings area.

### Key flows

1. Student opens the integration page and reviews what data is copied, how Canvas remains authoritative, and the warning about an existing iCal subscription.
2. Student selects **Connect Google Calendar**, completes Google consent, and returns to Canvas.
3. Student reviews eligible active courses, selects courses, and saves.
4. Canvas creates the dedicated calendar, enqueues initial sync, and shows progress without blocking the page.
5. Student can open the Google calendar, follow a coursework link, sync now, change course selection, pause, reconnect, or disconnect.

### Required states

- **Empty** — explanation, privacy summary, iCal alternative, and connect action.
- **OAuth pending/cancelled** — safe retry with no connection shown as active prematurely.
- **Initial sync** — progress/status without an indefinite spinner.
- **Healthy** — last/next timestamps and concise result counts.
- **Partial/provider delayed** — non-destructive retry state and plain-language explanation.
- **Action required** — reconnect or contact-institution action.
- **Paused/admin-disabled** — existing event behavior and resume eligibility explained.
- **Disconnecting/cleanup failed** — retry cleanup without restoring scheduled sync.
- **Offline** — show cached status, disable mutating actions, and preserve entered course choices locally until reconnection where safe.

The layout MUST work at 320 CSS pixels, preserve logical focus order, return focus after dialogs, announce async completion through an ARIA live region, and avoid exposing provider error payloads. Proposed i18n keys include `integrations.googleCalendar.connect`, `.courseSelection`, `.syncNow`, `.lastSuccess`, `.reauthRequired`, `.icalDuplicateWarning`, and `.disconnectCleanupChoice`.

## 11. AI / ML Considerations

Not applicable. Assignment selection, event projection, and reconciliation are deterministic and MUST NOT call an AI model.

## 12. Integration Points

### External services

- **Google OAuth 2.0** — authorization-code flow with offline access and narrow scopes.
- **Google Calendar API v3** — create the dedicated calendar and insert, patch, get, and delete managed events. Use private extended properties for source identity and `sendUpdates=none` for writes.
- **Canvas assignment data** — a native Canvas implementation should use its authorization-aware assignment service. An external implementation can use `GET /api/v1/users/self/courses`, `GET /api/v1/courses/:course_id/assignments`, and/or `GET /api/v1/calendar_events?type=assignment`, following opaque `Link` pagination and preserving `due_at`, `all_day`, `all_day_date`, `html_url`, `updated_at`, visibility, and student-specific overrides. Calendar-event requests MUST batch selected `context_codes[]` in groups of at most 10. Periodic complete reconciliation remains required even if Canvas Live Events are later used to trigger faster runs.

### Internal modules

- Identity/session and tenant-policy service.
- OAuth transaction/callback service and encrypted secret store.
- Canvas coursework normalization layer.
- Calendar provider adapter and reconciliation engine.
- Durable scheduler/job queue and retry/dead-letter handling.
- Settings UI, admin feature-policy UI, audit/metrics pipeline, and support runbook.

The current planning repository has no production server, database, UI, or job queue. Its existing `study-agent/scripts/pull_canvas_workload.py` is a useful read-only reference for Canvas pagination and date handling, but it is not sufficient production infrastructure and MUST NOT become a token store or multi-user worker without a separate design review.

## 13. Dependencies & Sequencing

| Order | Story | Scope | Exit criteria | Depends on |
|---|---|---|---|---|
| 1 | **CAL-1A** | OAuth, secret storage, tenant gate, dedicated calendar, disconnect skeleton | A student can connect/revoke safely in a non-production Google project. | Identity, OAuth callback, KMS/secret store |
| 2 | **CAL-1B** | Active-course discovery, selection, timezone, preferences | Preferences persist and enforce ownership/admin policy. | CAL-1A |
| 3 | **CAL-1C** | Assignment normalization, event projection, mapping, initial sync | Representative assignments create one correct linked event each. | CAL-1A, CAL-1B, database, worker queue |
| 4 | **CAL-1D** | Scheduled reconciliation, updates, safe deletion, retry/backoff | Mutation, pagination, partial-scan, and idempotency tests pass. | CAL-1C, scheduler |
| 5 | **CAL-1E** | Status, manual sync, recovery, pause, cleanup, support tooling | End-to-end lifecycle and accessibility tests pass. | CAL-1D |
| 6 | **CAL-1F** | Institution policy, rollout cohorts, aggregate health | Admin policy is enforced at UI, API, and worker layers. | CAL-1A–CAL-1E |

OAuth app registration/verification, privacy/legal approval, encrypted storage, and a durable queue are release prerequisites. If this is implemented only as a local single-user `study-agent` prototype, production administration and multi-user infrastructure may be deferred, but the token-handling, idempotency, timezone, and cleanup rules still apply.

## 14. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Existing Canvas iCal subscriptions cause duplicate assignments. | M | M | Warn during setup, document the difference, and provide removal guidance before initial sync. |
| Google OAuth verification or a Workspace admin blocks the requested scope. | M | H | Use `calendar.app.created`, begin verification early, support admin allowlisting docs, and show a clear blocked state. |
| Refresh tokens or education-record metadata are exposed. | L | H | Envelope encryption, strict access boundaries, redacted structured logs, short retention, rotation, and security review. |
| Student-specific overrides or DST conversion produce the wrong deadline. | M | H | Use the requesting student’s effective Canvas date, preserve offsets/instants, use IANA zones, and test override/DST boundaries. |
| Retries or concurrent runs create duplicates. | M | H | Unique mapping constraints, per-connection job lock, source fingerprints, Google private properties, and idempotent upsert logic. |
| A partial Canvas response is mistaken for deletion. | M | H | Reconcile absence only after every page/course succeeds; record a run-level completeness marker. |
| Cleanup deletes unrelated Google content. | L | H | Default to an app-created calendar, require source tags/mappings, scope all deletion queries to the owned calendar, and confirm cleanup. |
| Large enrollments exceed Canvas or Google quotas. | M | M | Pagination, bounded concurrency, change fingerprints, backoff/jitter, `Retry-After`, queue shaping, and quota dashboards. |
| Users edit or delete managed Google events and are surprised by reconciliation. | M | M | Disclose one-way ownership, use a dedicated calendar, and offer pause/disconnect before customization. |
| Canvas and Google provider outages create stale deadlines. | M | H | Show last-success freshness, retain existing events on failure, retry safely, alert on backlog, and provide the Canvas link as source of truth. |
| Product value is too close to the existing iCal feed. | M | M | Validate demand for course selection, actionable health, reliable cleanup, and faster reconciliation before full rollout. |

## 15. Rollout Plan

- **Feature flag** — `google_calendar_coursework_sync`, default `false` globally and per institution.
- **Migration sequence** — additive schema and encryption keys → OAuth configuration → read-only shadow normalization → internal event writes → UI cohort → tenant opt-in → broader rollout.
- **Dogfood** — staff/test accounts with synthetic courses, then a small consenting student pilot across at least one K12 and one higher-education tenant where policy permits.
- **Guardrails** — cap users and writes per cohort, monitor duplicate rate, wrong-time reports, auth failures, queue age, deletion spikes, and support volume.
- **GA criteria** — zero confirmed cross-user data exposure or unrelated-event deletion; ≥99.9% duplicate-free mappings in reconciliation audits; freshness targets met for four consecutive weeks; accessibility/security/privacy reviews complete; documented support ownership.
- **Communication** — setup guide, privacy disclosure, iCal comparison, Workspace admin allowlisting guide, release notes, and in-product opt-in notice.
- **Rollback** — disable new connections and scheduled jobs with the flag, preserve credentials/mappings temporarily for recovery, stop all deletion work, and let users keep or explicitly clean up the dedicated calendar. Schema removal is a later, separately reviewed change.

## 16. Test Plan

- **Unit** — Canvas assignment normalization; effective override selection; all-day/timed projection; URL allowlisting; source fingerprints; extended-property identity; course filtering; retry classification; disconnect choices; locale/timezone/DST cases.
- **Integration** — mocked and sandbox Canvas/Google APIs covering OAuth callback, token refresh, calendar creation, event insert/patch/delete, opaque Canvas pagination, Google pagination, `429`/`5xx`, `Retry-After`, revoked tokens, Workspace policy errors, partial scans, concurrent/manual jobs, and cleanup scope.
- **End-to-end** — connect/cancel consent, select courses, initial sync, open Canvas link, rename/reschedule/unpublish/delete assignment, no-due skip, submitted assignment retained, sync now, pause/resume, reconnect, keep-on-disconnect, remove-on-disconnect, and admin disable.
- **Security** — user/tenant authorization matrix, OAuth state and PKCE validation, callback replay, CSRF, redirect manipulation, IDOR, token/log redaction, KMS access, SSRF/open-redirect checks on Canvas URLs, HTML injection in assignment/course names, and deletion-boundary tests.
- **Accessibility** — automated axe checks plus keyboard-only and screen-reader scripts for setup, course selection, async status, errors, confirmation dialogs, and OAuth return focus.
- **Performance/load** — 500 assignments per user, 100 concurrent syncs per worker pool, large paginated tenants, provider latency, retry storms, and queue backpressure. Pass when freshness and initial-sync targets hold without exceeding configured provider quotas.
- **Manual exploratory** — multiple Google accounts, multiple Canvas institutions, courses with identical names, emoji/non-Latin titles, very long titles, midnight and all-day deadlines, DST boundaries, mobile widths, offline/reconnect, existing iCal subscription, and user edits/deletes in Google.

## 17. Documentation & Training

- Publish a student help article covering connect, course selection, event format, one-way ownership, manual sync, status, disconnect, privacy, and troubleshooting.
- Add a comparison explaining when to use the new integration versus Canvas’s existing iCal subscription, including how to avoid duplicate events.
- Publish an institution/Google Workspace admin guide for feature policy, OAuth app approval/allowlisting, underage-account considerations, and aggregate health.
- Document all new routes and schemas in the API reference, without exposing token-management internals.
- Create an internal runbook for revoked access, quota exhaustion, provider outages, stuck jobs, deletion spikes, key rotation, cleanup failure, and OAuth client-secret rotation.
- Train support teams to request correlation/run IDs rather than screenshots containing coursework or access tokens.

## 18. Open Questions

1. Is the intended target a native Canvas product feature, an external multi-user service, or a local extension of this repository’s `study-agent`? The authentication, storage, and UI architecture changes materially by target.
2. Is the recommended dedicated **Canvas Coursework** calendar acceptable for MVP, or must students select an existing writable calendar at the cost of broader Google permissions and higher cleanup risk?
3. What initial date range should be populated: current active term, a rolling window, or all future dated assignments? Recommendation: recent 30 days through the selected courses’ end dates, capped at one year when a course end is unavailable.
4. Should disconnect default to keeping a static calendar or removing it? Both choices are planned, but product/privacy owners should select the default.
5. Is a 15-minute schedule and 20-minute p95 freshness target sufficient, or should Canvas Live Events/webhooks be evaluated after MVP?
6. Should observer/parent accounts, adult-managed homeschool accounts, or instructor calendars become a separate follow-up feature?
7. How will institution policy and consent work for minors and school-managed Google Workspace accounts in each launch market?
8. What measured user problem is not met by the existing Canvas iCal feed, and which differentiation metric—setup completion, freshness, course selection, recovery, or cleanup—will determine whether the pilot expands?

## 19. References

- Planning template: [`_TEMPLATE.md`](_TEMPLATE.md)
- Existing local Canvas client: [`study-agent/scripts/pull_canvas_workload.py`](study-agent/scripts/pull_canvas_workload.py)
- Existing local Canvas API notes: [`study-agent/references/canvas-api-operations.md`](study-agent/references/canvas-api-operations.md)
- [Canvas Assignments API](https://developerdocs.instructure.com/services/canvas/resources/assignments)
- [Canvas Calendar Events API](https://developerdocs.instructure.com/services/canvas/resources/calendar_events)
- [Canvas Courses API](https://developerdocs.instructure.com/services/canvas/resources/courses)
- [Canvas OAuth2](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth)
- [Canvas pagination](https://developerdocs.instructure.com/services/canvas/basics/file.pagination)
- [Canvas throttling](https://developerdocs.instructure.com/services/canvas/basics/file.throttling)
- [Canvas assignment Live Events](https://developerdocs.instructure.com/services/canvas/data-services/live-events/event-format/canvas/file.data_service_canvas_assignment)
- [Canvas Basics Guide](https://community.canvaslms.com/html/assets/Canvas_Basics_Guide.pdf) — includes the current Google Calendar/iCal subscription flow.
- [Google Calendar API overview](https://developers.google.com/workspace/calendar/api/guides/overview)
- [Google Calendar OAuth scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Google OAuth 2.0 for web server applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google secondary calendar creation](https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert)
- [Google Calendar event creation](https://developers.google.com/workspace/calendar/api/guides/create-events)
- [Google Calendar event insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), [patch](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch), and [delete](https://developers.google.com/workspace/calendar/api/v3/reference/events/delete)
- [Google Calendar private extended properties](https://developers.google.com/workspace/calendar/api/guides/extended-properties)
- [Google Calendar quota guidance](https://developers.google.com/workspace/calendar/api/guides/quota)
