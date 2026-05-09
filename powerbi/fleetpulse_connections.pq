// FleetPulse -> Power BI read-only web connections.
// Create a Power BI parameter named FleetPulseBaseUrl with:
// https://k1-fleetpulse.azurewebsites.net

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
