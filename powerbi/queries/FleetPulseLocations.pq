// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [RelativePath = "api/powerbi/locations"]
        )
    ),
    Rows = Table.FromRecords(Source),
    Typed = Table.TransformColumnTypes(
        Rows,
        {
            {"name", type text},
            {"address", type text},
            {"latitude", type number},
            {"longitude", type number},
            {"vehicle_count", Int64.Type},
            {"active", Int64.Type},
            {"safety_score", type number},
            {"connection_name", type text},
            {"exported_at", type datetimezone},
            {"source_system", type text},
            {"source_authority", type text},
            {"projection_mode", type text}
        }
    )
in
    Typed

