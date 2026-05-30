# Employee Workforce and Driver Compliance

FleetPulse treats both surfaces as read-only projections.

## Employee Workforce

- Source authority: Time Doctor employee time and activity evidence.
- Endpoint: `GET /api/employee-workforce`
- UI tab: `#employee-workforce`
- Dashboard section: Employee Workforce - Time Doctor
- Projection mode: `read_only`

Supported feed shapes:

- `FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH`: governed JSON, JSONL, or CSV export.
- `FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_URL`: approved Time Doctor API/export URL.

Required activity fields are flexible aliases for employee id/name/email, date,
worked minutes/hours, productive minutes/hours, idle minutes/hours, department,
and project/task.

## Driver Compliance

- Source authority: configured driver qualification document register.
- Endpoint: `GET /api/driver-compliance`
- UI tab: `#driver-compliance`
- Projection mode: `read_only`

Tracked document fields:

- `medical_card`
- `drug_test`
- `mvr`

Supported source shapes:

- `FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH`: governed JSON, JSONL, or CSV register.
- `FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_URL`: approved read-only register URL.

Until a source is configured, the endpoint returns `driver_compliance_source_pending`
with the required config list and no fabricated driver rows.
