// Operations department — Operations Manager Seat dashboard composition.

export { default as ControlTower } from '../../components/ControlTower'
export { default as OperatingSystem } from '../../components/OperatingSystem'
export { default as RouteReplay } from '../../components/RouteReplay'
export { default as FleetReports } from '../../components/FleetReports'
export { default as StabilityDashboard } from '../../components/StabilityDashboard'
export { default as FleetMap } from '../../components/FleetMap'

export const DEPARTMENT_ID = 'operations' as const
export const SEAT_ID = 'operations_manager' as const
