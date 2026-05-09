// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [RelativePath = "api/powerbi/overview"]
        )
    ),
    Rows = Table.FromRecords(Source),
    Typed = Table.TransformColumnTypes(
        Rows,
        {
            {"total_vehicles", Int64.Type},
            {"active", Int64.Type},
            {"idle", Int64.Type},
            {"parked", Int64.Type},
            {"offline", Int64.Type},
            {"total_trips_today", Int64.Type},
            {"total_stops_today", Int64.Type},
            {"total_distance_miles", type number},
            {"avg_trip_duration_min", type number},
            {"avg_trip_duration_hours", type number},
            {"avg_trip_distance_miles", type number},
            {"target_trip_duration_hours", type number},
            {"trips_meeting_target", Int64.Type},
            {"trips_under_target", Int64.Type},
            {"trip_definition", type text},
            {"connection_name", type text},
            {"exported_at", type datetimezone},
            {"source_system", type text},
            {"source_authority", type text},
            {"projection_mode", type text}
        }
    )
in
    Typed

