// Executive department — Executive Command Seat dashboard composition.
// Re-exports existing components without moving the source files.

export { default as Dashboard } from '../../components/Dashboard'
export { default as FleetAnalytics } from '../../components/FleetAnalytics'
export { default as FleetChat } from '../../components/FleetChat'
export { default as AlertFeed } from '../../components/AlertFeed'
export { default as Leaderboard } from '../../components/Leaderboard'
export { default as AgenticMonitor } from '../../components/AgenticMonitor'
export { default as DashboardValidationSummary } from '../../components/DashboardValidationSummary'

export const DEPARTMENT_ID = 'executive' as const
export const SEAT_ID = 'executive_command' as const
