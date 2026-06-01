# FleetPulse Scheduled Feed Wiring

FleetPulse is the read-only KPI surface. Zapier and Power Automate coordinate
scheduled pulls, but source authority stays with QBO, Xcelerator, SharePoint,
and the approved HR_Lead_KPI_Recheck_By_Phone workbook-backed HR source.

## Azure App Settings

Run this once from an Azure-authenticated shell:

```bash
bash scripts/configure_fleetpulse_feed_appsettings.sh
```

The approved live deployment path runs the same script from the GitHub Actions
Azure deployment workflow after the App Service container deploy and before
smoke tests. Store only the Graph Key Vault secret names in GitHub Secrets; the
workflow writes App Service settings as Key Vault references and does not expose
or persist raw Microsoft Graph credential values.

Defaults:

```env
AZURE_RESOURCE_GROUP=k1-fleetpulse-rg
AZURE_APP_NAME=k1-fleetpulse
AZURE_KEY_VAULT_NAME=kv-k1-fleetpulse
FLEETPULSE_QBO_FINANCIAL_STATE_PATH=/home/data/fleetpulse_qbo_financial.json
FLEETPULSE_XCELERATOR_EVENT_STATE_PATH=/home/data/fleetpulse_xcelerator_events.json
HR_RECRUITING_SOURCE=hr_kpi_workbook
HR_RECRUITING_WORKBOOK_PATH=/home/data/HR_Lead_KPI_Recheck_By_Phone.xlsx
HR_RECRUITING_CONVERSION_WORKBOOK_PATH=/home/data/HR_Lead_Name_To_Xcelerator_Driver_Conversion.xlsx
HR_RECRUITING_STATE_PATH=/home/data/fleetpulse_hr_recruiting.json
HR_CALL_ANALYSIS_STATE_PATH=/home/data/fleetpulse_hr_call_analysis.json
DEPARTMENT_CALL_ANALYSIS_STATE_PATH=/home/data/fleetpulse_hr_call_analysis.json
FLEETPULSE_BILLING_EXCEPTIONS_STATE_PATH=/home/data/fleetpulse_billing_exceptions.json
FLEETPULSE_WEEKLY_CLOSE_VARIANCE_STATE_PATH=/home/data/fleetpulse_weekly_close_variance.json
FLEETPULSE_DISPATCH_TIMESTAMPS_STATE_PATH=/home/data/fleetpulse_dispatch_timestamps.json
FLEETPULSE_SHAREPOINT_SEAT_ASSIGNMENTS_STATE_PATH=/home/data/fleetpulse_sharepoint_seat_assignments.json
FLEETPULSE_SHAREPOINT_TRAINING_HISTORY_STATE_PATH=/home/data/fleetpulse_sharepoint_training_history.json
FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE=xcelerator_ceo_powerbi
FLEETPULSE_DRIVER_WORKFORCE_XCELERATOR_SOURCE=ceo_powerbi
FLEETPULSE_DRIVER_WORKFORCE_CEO_POWERBI_FALLBACK=fabric_warehouse_sql
K1L_OPERATING_COST_REVENUE_SOURCE=xcelerator_ceo_powerbi
FLEETPULSE_XCELERATOR_CEO_POWERBI_WORKSPACE_ID=b801f80d-5303-4121-abd1-1163639ef58b
FLEETPULSE_XCELERATOR_CEO_POWERBI_REPORT_ID=c6624826-3a00-4f94-b1f3-24baaf99dd24
FLEETPULSE_XCELERATOR_CEO_POWERBI_SEMANTIC_MODEL_ID=478b78eb-663d-42ff-b92d-bc8f699e05ac
FLEETPULSE_EMPLOYEE_WORKFORCE_SOURCE=time_doctor
FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH=/home/data/fleetpulse_time_doctor_activity.json
FLEETPULSE_EMPLOYEE_SESSION_STATE_PATH=/home/data/fleetpulse_employee_sessions.json
FLEETPULSE_EMPLOYEE_EXCLUSIONS_PATH=/home/data/fleetpulse_employee_exclusions.json
FLEETPULSE_DRIVER_COMPLIANCE_SOURCE=driver_qualification_register
FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH=/home/data/fleetpulse_driver_compliance_register.json
FLEETPULSE_DRIVER_COMPLIANCE_WARNING_DAYS=45
HR_CALL_ANALYSIS_SHAREPOINT_ENABLED=true
HR_CALL_ANALYSIS_SHAREPOINT_SITE_URL=https://netorgft3187866.sharepoint.com/sites/K1SOPsandProcedures
HR_CALL_ANALYSIS_SHAREPOINT_FOLDER_PATH=Grasshopper/Call Analysis Reports/HR
HR_CALL_ANALYSIS_SHAREPOINT_FILE_EXTENSIONS=.txt,.csv
HR_CALL_ANALYSIS_ACTIVE_EXTENSIONS=702,722,725,728,700
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

The script never creates or guesses Xcelerator CEO Dashboard BI credentials.
When those secrets already exist in Key Vault, set any of these secret-name
environment variables before running the script and the App Service setting will
be written as a Key Vault reference:

```env
FLEETPULSE_XCELERATOR_CEO_POWERBI_ACCESS_TOKEN_SECRET_NAME=
FLEETPULSE_XCELERATOR_CEO_POWERBI_TENANT_ID_SECRET_NAME=
FLEETPULSE_XCELERATOR_CEO_POWERBI_CLIENT_ID_SECRET_NAME=
FLEETPULSE_XCELERATOR_CEO_POWERBI_CLIENT_SECRET_SECRET_NAME=
```

Live SharePoint folder sync uses the shared Microsoft Graph app credentials.
When those secrets already exist in Key Vault, set these secret-name variables
before running the script so the App Service receives Key Vault references:

```env
FLEETPULSE_GRAPH_TENANT_ID_SECRET_NAME=
FLEETPULSE_GRAPH_CLIENT_ID_SECRET_NAME=
FLEETPULSE_GRAPH_CLIENT_SECRET_SECRET_NAME=
```

The Graph app must be read-only for the configured SharePoint site/folder. It
must not grant FleetPulse write authority to HR, Tenstreet, Grasshopper,
SharePoint, or Xcelerator data.

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

The stored snapshot must include enough metadata for finance guardrails:

- `coverage_start` and `coverage_end` must match the QBO report/export window.
- `last_imported_at` is written by FleetPulse on successful import and is used
  for source freshness checks.
- `accounts_payable`, `accounts_receivable`, and `expenses` should be
  account-level rows. QuickBooks Profit & Loss summary rows in `rows`,
  `profit_and_loss`, `profit_and_loss_rows`, `pnl`, or `pl_summary` containers
  are accepted as evidence but flagged as `qbo_financial_statement_rows`;
  FleetPulse will not publish them as the K1 Logistics Inc operating-cost stack.
- Configure `FLEETPULSE_QBO_FINANCIAL_MAX_STALENESS_HOURS` for the maximum
  acceptable snapshot age before margin publishing is marked review-required.
- Configure `FLEETPULSE_QBO_FINANCIAL_ACCOUNT_SPIKE_MIN_AMOUNT` to set the
  account-level P&L/expense spike threshold; the default is `100000`.

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

### Xcelerator CEO Power BI Route Tickets and Finance

- Source: K1 Group LLC Xcelerator CEO Dashboard semantic model.
- FleetPulse mode: read-only DAX query or Fabric Warehouse SQL fallback.
- Driver Workforce route windows use
  `FLEETPULSE_DRIVER_WORKFORCE_XCELERATOR_SOURCE=ceo_powerbi`.
- K1L revenue-per-mile/profit uses
  `K1L_OPERATING_COST_REVENUE_SOURCE=xcelerator_ceo_powerbi`.
- Keep `FLEETPULSE_DRIVER_WORKFORCE_CEO_POWERBI_FALLBACK=fabric_warehouse_sql`
  for controlled read-only warehouse fallback when the semantic model auth path
  is unavailable.

No Power BI credential values are stored in this repo. Use the Key Vault
secret-name environment variables above when existing approved secrets are
available.

### Time Doctor Activity Feed

- Trigger: after the approved Time Doctor activity export refreshes.
- Action: publish JSON or CSV to `FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH`, or
  expose an approved read-only URL through `FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_URL`.
- Status URL: `https://k1-fleetpulse.azurewebsites.net/api/employee-workforce`
- Contract manifest key: `time_doctor_activity`

Minimum useful row fields:

```json
{
  "employee_id": "E-100",
  "employee_name": "Dispatch User",
  "email": "dispatch@example.com",
  "department": "Dispatch",
  "date": "2026-05-30",
  "worked_minutes": 480,
  "productive_minutes": 420,
  "idle_minutes": 30
}
```

FleetPulse uses this as activity evidence only. It does not write payroll, and
hourly coverage remains manager-review-required.

Optional inactive/separated employee suppression can be supplied through
`FLEETPULSE_EMPLOYEE_EXCLUSIONS_PATH`, `FLEETPULSE_EMPLOYEE_EXCLUSIONS_JSON`,
`FLEETPULSE_INACTIVE_EMPLOYEE_EMAILS`, `FLEETPULSE_SEPARATED_EMPLOYEE_EMAILS`,
`FLEETPULSE_INACTIVE_EMPLOYEE_IDS`, or `FLEETPULSE_SEPARATED_EMPLOYEE_IDS`.
Those references only remove matching rows from FleetPulse projection counts;
HR, Entra, Time Doctor, and SharePoint remain authoritative.

### Driver Compliance Document Register

- Trigger: after the approved driver qualification register refreshes.
- Action: publish JSON or CSV to `FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH`, or
  expose an approved read-only URL through `FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_URL`.
- Status URL: `https://k1-fleetpulse.azurewebsites.net/api/driver-compliance`
- Contract manifest key: `driver_compliance_documents`

Minimum useful row fields:

```json
{
  "driver_id": "D-100",
  "driver_name": "Driver One",
  "medical_card_expires": "2026-08-01",
  "drug_test_expires": "2026-07-30",
  "mvr_expires": "2026-09-01"
}
```

FleetPulse only calculates expiration risk and dashboard coverage. It does not
write back to any driver qualification or compliance system.

### HR Recruiting KPI Workbook Projection

- Trigger: after the upstream HR KPI workbook refresh completes.
- Action: publish the approved `HR_Lead_KPI_Recheck_By_Phone.xlsx` workbook to
  the persistent App Service path in `HR_RECRUITING_WORKBOOK_PATH`.
- Source: workbook evidence from Grasshopper/SharePoint/Tenstreet; FleetPulse
  only reads aggregate KPI evidence and suppresses applicant contact data.
- Status URL: `https://k1-fleetpulse.azurewebsites.net/api/hr-recruiting/status`
- Worklist URL: `https://k1-fleetpulse.azurewebsites.net/api/hr-recruiting/worklist`
- Date-scoped worklist URL:
  `https://k1-fleetpulse.azurewebsites.net/api/hr-recruiting/worklist?start_date=2026-05-01&end_date=2026-05-31`

```env
HR_RECRUITING_SOURCE=hr_kpi_workbook
HR_RECRUITING_WORKBOOK_PATH=/home/data/HR_Lead_KPI_Recheck_By_Phone.xlsx
HR_RECRUITING_CONVERSION_WORKBOOK_PATH=/home/data/HR_Lead_Name_To_Xcelerator_Driver_Conversion.xlsx
HR_RECRUITING_TEAM_MEMBERS=Jordan
HR_CALL_ANALYSIS_STATE_PATH=/home/data/fleetpulse_hr_call_analysis.json
DEPARTMENT_CALL_ANALYSIS_STATE_PATH=/home/data/fleetpulse_hr_call_analysis.json
HR_CALL_ANALYSIS_ACTIVE_EXTENSIONS=702,722,725,728,700
```

`HR_RECRUITING_TEAM_MEMBERS` is the configured HR roster displayed on the HR
page. FleetPulse merges that roster with workbook member KPI rows when the
source workbook includes them; it does not fabricate activity for roster-only
members.
`HR_RECRUITING_CONVERSION_WORKBOOK_PATH` adds the optional
`HR_Lead_Name_To_Xcelerator_Driver_Conversion.xlsx` funnel. The parser returns
only aggregate exact-match conversion counts, source/SLA buckets, and trend
summary fields; it suppresses lead names, phones, driver numbers, and driver
names and does not write back to Xcelerator.

Required workbook tabs:

- `Lead Level KPI`
- `Call Attempts Detail`
- `Failed No Outbound`
- `Recovered 24-48h`
- `Failed Over 72h`
- `No Real Discussion`
- `Source Log QA`

When `start_date` and `end_date` are supplied, FleetPulse filters the
workbook-backed aggregate KPI payload before rendering the HR Recruiting
surface. Lead KPI rows are filtered by `Lead Created At` or compatible
submitted/created intake columns, not later application, modified, or status
dates; follow-up counts are filtered by call date.
The response includes a same-length prior-period comparison, remains a
read-only projection, and includes `workbook_evidence.exception_queue` from the
approved exception tabs and matching lead-level KPI exceptions. The queue
exposes only masked lead references, KPI buckets, status, age, and source sheet;
it must not include applicant PII.

Microsoft 365/SharePoint state mode: if the SharePoint HR upload is newer than
the workbook-backed KPI recheck, leave `HR_RECRUITING_WORKBOOK_PATH` unset, set
`HR_RECRUITING_SOURCE=microsoft_365_sharepoint`, and import only sanitized lead
rows into `HR_RECRUITING_STATE_PATH`. Use `HR_CALL_ANALYSIS_STATE_PATH` or
`DEPARTMENT_CALL_ANALYSIS_STATE_PATH` for the separate sanitized Grasshopper
call-analysis state. `HR_CALL_ANALYSIS_ACTIVE_EXTENSIONS` limits HR call KPI
rollups to configured HR extensions when a Grasshopper detail export includes
other departments. The HR total-calls KPI uses date-scoped Detail rows
(`total_call_legs`) for inbound plus outbound call legs; Activity report counts
are monthly Grasshopper reference totals and must not replace the date-scoped
total. FleetPulse must remain read-only and must not persist applicant names,
phone numbers, or email addresses.

Legacy fallback only: when workbook mode is unavailable, leave
`HR_RECRUITING_WORKBOOK_PATH` unset, set `HR_RECRUITING_SOURCE=zapier_table`,
and use `POST /api/hr-recruiting/import` with `X-FleetPulse-HR-Key` to store a
read-only snapshot at `HR_RECRUITING_STATE_PATH`. Do not use the fallback as
the deployed default.

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
