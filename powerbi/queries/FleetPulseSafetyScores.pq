// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/safety-scores",
                Query = [days = "7"]
            ]
        )
    ),
    Rows = Table.FromRecords(Source),
    Typed = Table.TransformColumnTypes(
        Rows,
        {
            {"vehicle_id", type text},
            {"vehicle_name", type text},
            {"score", type number},
            {"trend", type text},
            {"event_count", Int64.Type},
            {"speeding_events", Int64.Type},
            {"harsh_braking_events", Int64.Type},
            {"harsh_acceleration_events", Int64.Type},
            {"harsh_cornering_events", Int64.Type},
            {"period_days", Int64.Type},
            {"connection_name", type text},
            {"exported_at", type datetimezone},
            {"source_system", type text},
            {"source_authority", type text},
            {"projection_mode", type text}
        }
    )
in
    Typed

