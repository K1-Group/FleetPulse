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

const sampleData = {
  generated_at: '2026-05-30T12:00:00Z',
  projection_mode: 'read_only',
  source_authority: 'K1 Group LLC / Xcelerator ReviewOrders rows',
  period: {
    days: 180,
    end: '2026-05-30',
    start: '2025-12-02',
  },
  thresholds: {
    cost_per_truck_hour: 90,
    minimum_history_samples: 1,
    stop_threshold_minutes: 60,
  },
  filters: {
    delivery: null,
    pickup: null,
  },
  summary: {
    address_pairs: 1,
    drivers_compared: 2,
    estimated_opportunity_cost_vs_pair_average: 45,
    evidence_matches: 2,
    invalid_route_rows: 0,
    measured_orders: 2,
    opportunity_minutes_vs_pair_average: 30,
    route_rows_in_period: 2,
    route_rows_read: 2,
  },
  address_pairs: [
    {
      address_pair_key: 'fort-worth-dallas',
      avg_route_minutes: 75,
      best_route_minutes: 60,
      delivery_address: 'Dallas DC',
      driver_benchmarks: [
        {
          avg_route_minutes: 60,
          best_route_minutes: 60,
          coaching_direction: 'Potential benchmark driver; verify load and dwell comparability before using for incentives.',
          driver_id: 'D1',
          driver_name: 'Driver One',
          estimated_opportunity_cost_vs_pair_average: 0,
          measured_orders: 1,
          opportunity_minutes_vs_pair_average: 0,
          stop_events_over_threshold: 0,
          variance_vs_pair_average_minutes: -15,
          worst_route_minutes: 60,
        },
        {
          avg_route_minutes: 90,
          best_route_minutes: 90,
          coaching_direction: 'Review dwell evidence and dispatch constraints before coaching.',
          driver_id: 'D2',
          driver_name: 'Driver Two',
          estimated_opportunity_cost_vs_pair_average: 22.5,
          measured_orders: 1,
          opportunity_minutes_vs_pair_average: 15,
          stop_events_over_threshold: 1,
          variance_vs_pair_average_minutes: 15,
          worst_route_minutes: 90,
        },
      ],
      driver_pay_total: 360,
      estimated_opportunity_cost_vs_pair_average: 45,
      evidence: {
        emails: {
          match_count: 1,
          matches: [],
          message: 'Configured read-only evidence feed has matching emails.',
          status: 'matched',
        },
        voice_recordings: {
          match_count: 1,
          matches: [],
          message: 'Configured read-only evidence feed has matching voice recordings.',
          status: 'matched',
        },
      },
      measured_orders: 2,
      median_route_minutes: 75,
      missing_actual_time_orders: 0,
      opportunity_minutes_vs_pair_average: 30,
      orders: 2,
      pickup_address: 'Fort Worth Yard',
      projection_mode: 'read_only',
      recent_orders: [
        {
          driver_id: 'D2',
          driver_name: 'Driver Two',
          duration_source: 'actual_xcelerator_timestamps',
          order_id: '152',
          route_date: '2026-05-21',
          route_minutes: 90,
          stop_minutes: 61,
          stop_over_threshold: true,
        },
        {
          driver_id: 'D1',
          driver_name: 'Driver One',
          duration_source: 'actual_xcelerator_timestamps',
          order_id: '151',
          route_date: '2026-05-20',
          route_minutes: 60,
          stop_minutes: 60,
          stop_over_threshold: false,
        },
      ],
      revenue_total: 1000,
      route_minutes_source: 'actual Xcelerator timestamps or explicit actual route minutes',
      source_authority: 'K1 Group LLC / Xcelerator ReviewOrders rows',
      stop_events_over_threshold: 1,
      stop_threshold_minutes: 60,
      worst_route_minutes: 90,
    },
  ],
  evidence_sources: {
    emails: 1,
    message: '',
    path: '/tmp/evidence.json',
    projection_mode: 'read_only',
    required_config: [],
    source_authority: 'Configured read-only voice/email evidence',
    status: 'healthy',
    voice_recordings: 1,
  },
  source_meta: {
    xcelerator: {
      status: 'healthy',
    },
  },
  recommendations: [
    'Use address-pair averages as a planning benchmark; keep Xcelerator as the operational source of truth.',
  ],
}

try {
  const module = await server.ssrLoadModule('/src/components/AddressBenchmarkScan.tsx')
  const html = renderToStaticMarkup(
    React.createElement(module.AddressBenchmarkScanView, {
      data: sampleData,
      days: 180,
      delivery: '',
      error: null,
      loading: false,
      onDaysChange: () => {},
      onDeliveryChange: () => {},
      onPickupChange: () => {},
      onRunScan: () => {},
      pickup: '',
    }),
  )

  const checks = [
    ['heading', 'Pickup Delivery History'],
    ['read-only marker', 'Read-only scan'],
    ['source status', 'Xcelerator Healthy'],
    ['lane label', 'Fort Worth Yard to Dallas DC'],
    ['strict stop label', '1 stops &gt;60m'],
    ['driver row', 'Driver Two'],
    ['evidence count', '1 voice'],
    ['order row', '152'],
  ]

  const missing = checks.filter(([, text]) => !html.includes(text))
  if (missing.length) {
    throw new Error(`Address benchmark render missing: ${missing.map(([name]) => name).join(', ')}`)
  }

  console.log(`Address benchmark UI render verified (${html.length} chars).`)
} finally {
  await server.close()
}
