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

    FleetPulseSnapshot =
        Json.Document(Web.Contents(FleetPulseBaseUrl & "/api/powerbi/fleetpulse-snapshot?days=7"))
in
    [
        FleetPulseOverview = FleetPulseOverview,
        FleetPulseLocations = FleetPulseLocations,
        FleetPulseVehicles = FleetPulseVehicles,
        FleetPulseSafetyScores = FleetPulseSafetyScores,
        FleetPulseSnapshot = FleetPulseSnapshot
    ]
