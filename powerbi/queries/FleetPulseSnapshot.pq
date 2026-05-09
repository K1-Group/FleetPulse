// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/fleetpulse-snapshot",
                Query = [days = "7"]
            ]
        )
    ),
    RowCounts = Source[row_counts],
    Row = [
        connection_name = Source[connection_name],
        exported_at = Source[exported_at],
        source_system = Source[source_system],
        source_authority = Source[source_authority],
        projection_mode = Source[projection_mode],
        period_days = Source[period_days],
        overview_rows = RowCounts[overview],
        location_rows = RowCounts[locations],
        vehicle_rows = RowCounts[vehicles],
        safety_score_rows = RowCounts[safety_scores]
    ],
    Rows = Table.FromRecords({Row}),
    Typed = Table.TransformColumnTypes(
        Rows,
        {
            {"connection_name", type text},
            {"exported_at", type datetimezone},
            {"source_system", type text},
            {"source_authority", type text},
            {"projection_mode", type text},
            {"period_days", Int64.Type},
            {"overview_rows", Int64.Type},
            {"location_rows", Int64.Type},
            {"vehicle_rows", Int64.Type},
            {"safety_score_rows", Int64.Type}
        }
    )
in
    Typed

