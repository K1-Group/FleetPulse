# FleetPulse Scheduled Feed Wiring

FleetPulse is the read-only KPI surface. Zapier and Power Automate coordinate
scheduled pulls, but source authority stays with QBO, Xcelerator, SharePoint,
and the approved TenStreet Outlook/Zapier HR source.

## Azure App Settings

Run this once from an Azure-authenticated shell:

```bash
bash scripts/configure_fleetpulse_feed_appsettings.sh
```

Defaults:

```env
AZURE_RESOURCE_GROUP=k1-fleetpulse-rg
AZURE_APP_NAME=k1-fleetpulse
AZURE_KEY_VAULT_NAME=kv-k1-fleetpulse
FLEETPULSE_QBO_FINANCIAL_STATE_PATH=/home/data/fleetpulse_qbo_financial.json
FLEETPULSE_XCELERATOR_EVENT_STATE_PATH=/home/data/fleetpulse_xcelerator_events.json
HR_RECRUITING_STATE_PATH=/home/data/fleetpulse_hr_recruiting.json
HR_CALL_ANALYSIS_STATE_PATH=/home/data/fleetpulse_hr_call_analysis.json
FLEETPULSE_BILLING_EXCEPTIONS_STATE_PATH=/home/data/fleetpulse_billing_exceptions.json
FLEETPULSE_WEEKLY_CLOSE_VARIANCE_STATE_PATH=/home/data/fleetpulse_weekly_close_variance.json
FLEETPULSE_DISPATCH_TIMESTAMPS_STATE_PATH=/home/data/fleetpulse_dispatch_timestamps.json
FLEETPULSE_SHAREPOINT_SEAT_ASSIGNMENTS_STATE_PATH=/home/data/fleetpulse_sharepoint_seat_assignments.json
FLEETPULSE_SHAREPOINT_TRAINING_HISTORY_STATE_PATH=/home/data/fleetpulse_sharepoint_training_history.json
```

The script creates these Key Vault secrets if values are not supplied by env:

```env
FLEETPULSE-QBO-FINANCIAL-IMPORT-API-KEY
FLEETPULSE-XCELERATOR-EVENT-IMPORT-API-KEY
HR-RECRUITING-IMPORT-API-KEY
HR-CALL-ANALYSIS-IMPORT-API-KEY
FLEETPULSE-BILLING-EXCEPTIONS-IMPORT-API-KEY
FLEETPULSE-WEEKLY-CLOSE-VARIANCE-IMPORT-API-KEY
FLEETPULSE-DISPATCH-TIMESTAMPS-IMPORT-API-KEY
FLEETPULSE-SHAREPOINT-SEAT-ASSIGNMENTS-IMPORT-API-KEY
FLEETPULSE-SHAREPOINT-TRAINING-HISTORY-IMPORT-API-KEY
```

## Zapier Jobs

### QBO Financial Snapshot

- Trigger: Schedule by Zapier, daily at 06:00 CT.
- Action: QuickBooks Online report/export for K1 Logistics Inc AP, AR, and
  expense transactions for the last 370 days.
- Action: Webhooks by Zapier `POST`.
- URL: `https://k1-fleetpulse.azurewebsites.net/api/fuel/qbo/financial/import`
- Header: `X-FleetPulse-QBO-Key: <Key Vault secret value>`
- Body:

```json
{
  "filename": "qbo-financial-daily.json",
  "period_start": "{{start_date_370d}}",
  "period_end": "{{today}}",
  "content": "{{json_string_with_accounts_payable_accounts_receivable_expenses}}"
}
```

### Xcelerator Event Snapshot

- Trigger: Schedule by Zapier, daily at 06:05 CT.
- Action: Pull Xcelerator financial, route exception, billing exception, and
  dispatch timestamp rows from the approved Xcelerator export/API.
- Action: Webhooks by Zapier `POST`.
- URL: `https://k1-fleetpulse.azurewebsites.net/api/control-tower/xcelerator/events/import`
- Header: `X-FleetPulse-Xcelerator-Key: <Key Vault secret value>`
- Body:

```json
{
  "filename": "xcelerator-events-daily.json",
  "content": "{{json_string_with_events}}"
}
```

Minimum useful event fields:

```json
{
  "event_type": "shipment_financial_update",
  "shipment_id": "SH-1002",
  "route_id": "ROUTE-902",
  "status": "exception",
  "timestamp": "2026-05-20T11:05:00Z",
  "revenue_amount": 2500,
  "driver_pay_amount": 875,
  "gross_margin": 1625
}
```

### HR Recruiting Snapshot

- Trigger: Schedule by Zapier, daily at 06:10 CT.
- Action: Read the approved TenStreet Outlook/Zapier applicant worklist table.
- Action: Webhooks by Zapier `POST`.
- URL: `https://k1-fleetpulse.azurewebsites.net/api/hr-recruiting/import`
- Header: `X-FleetPulse-HR-Key: <Key Vault secret value>`
- Body:

```json
{
  "filename": "hr-recruiting-daily.json",
  "content": "{{json_string_with_rows}}"
}
```

Required HR row fields:

```json
{
  "source_email_id": "outlook-message-id",
  "applicant": "candidate name or source id",
  "worklist": "Recruiter Review",
  "status": "Assigned",
  "first_assigned_at": "2026-05-20T11:10:00Z",
  "current_worklist_entered_at": "2026-05-20T11:10:00Z",
  "completed_at": null
}
```

FleetPulse stores the source rows, but every HR dashboard and Power BI payload
suppresses applicant PII.

### HR Call Analysis Snapshot

- Trigger: Power Automate recurrence every 15 minutes.
- Action: Read the SharePoint folder
  `Documents/Grasshopper/Call Analysis Reports/HR`.
- Action: Webhooks by Zapier or Power Automate HTTP `POST`.
- URL: `https://k1-fleetpulse.azurewebsites.net/api/hr-call-analysis/import`
- Header: `X-FleetPulse-HR-Call-Key: <Key Vault secret value>`
- Body:

```json
{
  "filename": "grasshopper-hr-call-detail.csv",
  "content": "{{csv_or_json_string_with_call_rows}}"
}
```

Direct SharePoint sync is also available when Graph app credentials are
configured:

- URL: `https://k1-fleetpulse.azurewebsites.net/api/hr-call-analysis/sharepoint/sync`
- Header: `X-FleetPulse-HR-Call-Key: <Key Vault secret value>`
- Recommended cadence: every 15 minutes.
- GitHub Actions fallback: `.github/workflows/hr-call-analysis-sharepoint-sync.yml`
  calls this endpoint every 15 minutes using the
  `HR_CALL_ANALYSIS_IMPORT_API_KEY` repository secret. Logs only print sync
  counts, not call content or transcript text.

Minimum useful call row fields:

```json
{
  "call_started_at": "2026-05-08T21:16:31Z",
  "extension_id": "702",
  "employee_name": "David Attar",
  "direction": "Out",
  "call_type": "Mobile Outbound Connected",
  "duration_seconds": 306,
  "external_party_hash": "sha256-phone-key"
}
```

FleetPulse stores normalized call rows and SharePoint analysis metadata only.
Raw phone numbers are hashed and raw recordings/transcripts remain in
Grasshopper/SharePoint.

### Seat KPI Source Feeds

Use these for the remaining fixed-seat KPI blockers shown in Tower > Financial.
Each feed is read-only evidence and is idempotently stored by FleetPulse.

Common route shape:

- Status: `GET https://k1-fleetpulse.azurewebsites.net/api/control-tower/seat-kpis/feeds/{feed_key}/status`
- Import: `POST https://k1-fleetpulse.azurewebsites.net/api/control-tower/seat-kpis/feeds/{feed_key}/import`
- Header: `X-FleetPulse-Seat-KPI-Key: <matching Key Vault secret value>`
- Full contract manifest: `GET https://k1-fleetpulse.azurewebsites.net/api/control-tower/scheduled-feeds/contracts`

The contract manifest is safe to share with Power Automate/Zapier builders. It
contains route paths, auth header names, accepted JSON containers, and minimum
field groups, but never returns secret values.

Feed keys and minimum useful fields:

| Feed key | Source authority | Minimum fields |
| --- | --- | --- |
| `billing_exceptions` | Xcelerator + SharePoint billing packets | `exception_id` or `order_id`, `status`, `created_at` |
| `weekly_close_variance` | QBO + SharePoint weekly close ledger | `week_start`, `variance_amount`, `status` |
| `dispatch_timestamps` | Xcelerator dispatch lifecycle | `load_id` or `order_id`, one of `ready_at`, `assigned_at`, `accepted_at`, `dispatched_at` |
| `sharepoint_seat_assignments` | SharePoint `Seat_Assignments` | `seat_id`, `employee_id` or `user_principal_name`, `status` |
| `sharepoint_training_history` | SharePoint `Training_History` | `employee_id` or `user_principal_name`, `training_id` or `course`, `status` or `completed_at` |

Example body:

```json
{
  "filename": "billing-exceptions-daily.json",
  "content": "{\"rows\":[{\"exception_id\":\"BE-100\",\"order_id\":\"ORD-100\",\"status\":\"Open\",\"created_at\":\"2026-05-20T11:15:00Z\",\"blocker\":\"Missing POD\"}]}"
}
```

## Power Automate Equivalent

For each feed, create a scheduled cloud flow:

1. Recurrence trigger at the listed CT time.
2. Source connector action that retrieves the governed source rows.
3. Compose action that converts rows to a JSON string.
4. HTTP action `POST` to the matching FleetPulse endpoint with the import key
   header.
5. Teams action on failure only, posting the endpoint name, HTTP status, and
   run URL.

## Smoke Tests

After deploy and the first successful POST:

```bash
curl -sS https://k1-fleetpulse.azurewebsites.net/api/fuel/qbo/financial/status
curl -sS https://k1-fleetpulse.azurewebsites.net/api/control-tower/xcelerator/events/status
curl -sS https://k1-fleetpulse.azurewebsites.net/api/hr-recruiting/status
curl -sS https://k1-fleetpulse.azurewebsites.net/api/control-tower/seat-kpis/feeds/status
```

Expected result: each response is read-only, exposes readiness metadata, and
does not expose import keys or applicant PII.
