// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [RelativePath = "api/powerbi/vehicles"]
        )
    ),
    Rows = Table.FromRecords(Source),
    Typed = Table.TransformColumnTypes(
        Rows,
        {
            {"id", type text},
            {"name", type text},
            {"status", type text},
            {"location_name", type text},
            {"odometer_km", type number},
            {"last_contact", type datetimezone},
            {"latitude", type number},
            {"longitude", type number},
            {"bearing", type number},
            {"speed", type number},
            {"connection_name", type text},
            {"exported_at", type datetimezone},
            {"source_system", type text},
            {"source_authority", type text},
            {"projection_mode", type text}
        }
    )
in
    Typed

