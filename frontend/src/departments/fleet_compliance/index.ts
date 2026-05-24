// Fleet & Compliance department — Fleet & Compliance Manager Seat composition.

export { default as MaintenancePredictor } from '../../components/MaintenancePredictor'
export { default as DriverCoaching } from '../../components/DriverCoaching'
export { default as GeofenceManager } from '../../components/GeofenceManager'
export { default as FuelAnalytics } from '../../components/FuelAnalytics'
export { default as ComplianceDashboard } from '../../components/ComplianceDashboard'
export { default as DataConnector } from '../../components/DataConnector'
export { default as VehicleList } from '../../components/VehicleList'
export { default as SafetyScorecard } from '../../components/SafetyScorecard'
export { default as LocationCard } from '../../components/LocationCard'

export const DEPARTMENT_ID = 'fleet_compliance' as const
export const SEAT_ID = 'fleet_compliance_manager' as const
