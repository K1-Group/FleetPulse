// FleetPulse -> Power BI read-only web connections.
//
// Best practice:
// 1. Create a Power BI text parameter named FleetPulseBaseUrl:
//    https://k1-fleetpulse.azurewebsites.net
// 2. Create one Blank Query per file in powerbi/queries.
// 3. Add measures from powerbi/fleetpulse_measures.dax.
//
// This file remains as a quick single-query reference that returns all
// connections as a record. For a production report, use the separate query
// files because Power BI tables are easier to model, refresh, and validate.

let
    FleetPulseOverview =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/overview"))
        ),

    FleetPulseLocations =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/locations"))
        ),

    FleetPulseVehicles =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/vehicles"))
        ),

    FleetPulseSafetyScores =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/safety-scores?days=7"))
        ),

    LaneStabilityCompany =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/lane-stability/company?days=7"))
        ),

    LaneStabilityByService =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/lane-stability/by-service?days=7"))
        ),

    LaneStabilityLanes =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/lane-stability/lanes?days=7"))
        ),

    LaneStabilityRoutes =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/lane-stability/routes?days=7"))
        ),

    LaneStabilityDaily =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/lane-stability/daily?days=7"))
        ),

    LaneStabilityTrend =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/lane-stability/trend?days=7"))
        ),

    OperatingCostSummary =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/operating-cost/summary?days=180"))
        ),

    OperatingCostWeekly =
        Table.FromRecords(
            Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/operating-cost/weekly?days=180"))
        ),

    FleetPulseSnapshot =
        Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/fleetpulse-snapshot?days=7"))
in
    [
        FleetPulseOverview = FleetPulseOverview,
        FleetPulseLocations = FleetPulseLocations,
        FleetPulseVehicles = FleetPulseVehicles,
        FleetPulseSafetyScores = FleetPulseSafetyScores,
        LaneStabilityCompany = LaneStabilityCompany,
        LaneStabilityByService = LaneStabilityByService,
        LaneStabilityLanes = LaneStabilityLanes,
        LaneStabilityRoutes = LaneStabilityRoutes,
        LaneStabilityDaily = LaneStabilityDaily,
        LaneStabilityTrend = LaneStabilityTrend,
        OperatingCostSummary = OperatingCostSummary,
        OperatingCostWeekly = OperatingCostWeekly,
        FleetPulseSnapshot = FleetPulseSnapshot
    ]
