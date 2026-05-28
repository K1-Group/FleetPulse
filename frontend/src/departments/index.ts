// FleetPulse department entry points.
//
// Each subfolder re-exports existing components in `src/components` so that
// callers can import by department without disturbing the current `App.tsx`
// imports. No component implementations live here yet — this layer is purely
// organizational during the restructure.

export * as executive from './executive'
export * as finance from './finance'
export * as operations from './operations'
export * as fleetCompliance from './fleet_compliance'
export * as peopleSystems from './people_systems'
export * as revenue from './revenue'
export * as hrRecruiting from './hr_recruiting'
