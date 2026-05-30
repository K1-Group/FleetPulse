import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: {
    middlewareMode: true,
  },
})

const employeeData = {
  generated_at: '2026-05-30T18:00:00Z',
  projection_mode: 'read_only',
  source_authority: 'Time Doctor employee time and activity export',
  period: {
    start: '2026-05-24',
    end: '2026-05-30',
    days: 7,
    timezone: 'America/Chicago',
  },
  config: {
    source: 'time_doctor',
    lookback_days: 7,
  },
  summary: {
    employees: 2,
    active_today: 1,
    worked_hours: 14,
    idle_hours: 1.25,
    avg_productivity_pct: 85.4,
    activity_rows: 2,
    invalid_rows: 0,
    missing_timesheet_count: 1,
  },
  employees: [
    {
      employee_id: 'E1',
      employee_name: 'Ops One',
      email: 'ops.one@example.com',
      department: 'Dispatch',
      worked_hours: 8,
      productive_hours: 7,
      idle_hours: 0.5,
      productivity_pct: 87.5,
      days_reported: 1,
      active_today: true,
      latest_activity_date: '2026-05-30',
      top_projects: ['Dispatch Board'],
      source: 'time_doctor',
    },
    {
      employee_id: 'E2',
      employee_name: 'Ops Two',
      email: null,
      department: 'Billing',
      worked_hours: 6,
      productive_hours: 5,
      idle_hours: 0.75,
      productivity_pct: 83.3,
      days_reported: 1,
      active_today: false,
      latest_activity_date: '2026-05-29',
      top_projects: ['Invoice Audit'],
      source: 'time_doctor',
    },
  ],
  source_status: {
    status: 'healthy',
    message: 'Loaded read-only Time Doctor activity feed from configured file.',
    required_config: [],
    row_count: 2,
  },
  validation: {
    status: 'verified',
    state: 'time_doctor_activity_loaded',
    message: 'Verified read-only Time Doctor employee activity rows.',
    row_count: 2,
  },
}

const driverComplianceData = {
  generated_at: '2026-05-30T18:00:00Z',
  projection_mode: 'read_only',
  source_authority: 'Configured driver qualification document register',
  config: {
    warning_days: 45,
    source: 'pending_register',
  },
  summary: {
    drivers: 2,
    valid: 1,
    warning: 0,
    expired: 1,
    missing: 0,
    invalid_rows: 0,
    medical_card_expiring: 1,
    drug_test_expiring: 0,
    mvr_expiring: 0,
    document_status_counts: {
      medical_card: { valid: 1, warning: 1 },
      drug_test: { valid: 1, expired: 1 },
      mvr: { valid: 1, missing: 1 },
    },
  },
  document_types: [
    { key: 'medical_card', label: 'Medical Card', warning_days: 45 },
    { key: 'drug_test', label: 'Drug Test', warning_days: 45 },
    { key: 'mvr', label: 'MVR', warning_days: 45 },
  ],
  drivers: [
    {
      driver_id: 'D2',
      driver_name: 'Driver Warning',
      email: null,
      phone: null,
      terminal: 'Fort Worth',
      documents: {
        medical_card: { expires_on: '2026-06-10', days_remaining: 11, status: 'warning' },
        drug_test: { expires_on: '2026-05-01', days_remaining: -29, status: 'expired' },
        mvr: { expires_on: null, days_remaining: null, status: 'missing' },
      },
      overall_status: 'expired',
      next_expiration_date: '2026-06-10',
      source: 'pending_register',
    },
  ],
  source_status: {
    status: 'healthy',
    message: 'Loaded read-only driver compliance register from configured file.',
    required_config: [],
    row_count: 2,
  },
  validation: {
    status: 'verified',
    state: 'driver_compliance_register_loaded',
    message: 'Verified read-only driver compliance expiration register.',
    row_count: 2,
  },
}

try {
  const employeeModule = await server.ssrLoadModule('/src/components/EmployeeWorkforce.tsx')
  const driverComplianceModule = await server.ssrLoadModule('/src/components/DriverCompliance.tsx')
  const html = [
    renderToStaticMarkup(React.createElement(employeeModule.default, { data: employeeData, loading: false })),
    renderToStaticMarkup(React.createElement(driverComplianceModule.default, { data: driverComplianceData, loading: false })),
  ].join('\n')

  const checks = [
    ['employee heading', 'Employee Workforce - Time Doctor'],
    ['employee source', 'Read-only'],
    ['employee row', 'Ops One'],
    ['employee project', 'Dispatch Board'],
    ['driver heading', 'Driver Compliance'],
    ['medical card column', 'Medical Card'],
    ['drug test column', 'Drug Test'],
    ['mvr column', 'MVR'],
    ['driver row', 'Driver Warning'],
    ['expired badge', 'Expired'],
  ]
  const missing = checks.filter(([, text]) => !html.includes(text))
  if (missing.length) {
    throw new Error(`Workforce foundation render missing: ${missing.map(([name]) => name).join(', ')}`)
  }

  console.log(`Workforce foundation UI render verified (${html.length} chars).`)
} finally {
  await server.close()
}
