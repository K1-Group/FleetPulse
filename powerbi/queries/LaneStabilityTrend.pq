// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/lane-stability/trend",
                Query = [days = "7"]
            ]
        )
    ),
    Rows =
        if List.Count(Source) = 0 then
            #table(
                type table [
                    period_start = date,
                    period_end = date,
                    service = text,
                    lane = text,
                    trend_type = text,
                    baseline_stable_cov_pct = number,
                    current_stable_cov_pct = number,
                    delta_stable_cov_pct = number,
                    baseline_status = text,
                    current_status = text,
                    current_revenue = number,
                    current_orders = Int64.Type,
                    current_num_routes = Int64.Type,
                    current_primary_route = text,
                    connection_name = text,
                    exported_at = datetimezone,
                    source_system = text,
                    source_authority = text,
                    projection_mode = text
                ],
                {}
            )
        else
            Table.FromRecords(Source),
    Typed = Table.TransformColumnTypes(
        Rows,
        {
            {"period_start", type date},
            {"period_end", type date},
            {"service", type text},
            {"lane", type text},
            {"trend_type", type text},
            {"baseline_stable_cov_pct", type number},
            {"current_stable_cov_pct", type number},
            {"delta_stable_cov_pct", type number},
            {"baseline_status", type text},
            {"current_status", type text},
            {"current_revenue", type number},
            {"current_orders", Int64.Type},
            {"current_num_routes", Int64.Type},
            {"current_primary_route", type text},
            {"connection_name", type text},
            {"exported_at", type datetimezone},
            {"source_system", type text},
            {"source_authority", type text},
            {"projection_mode", type text}
        },
        [Culture = "en-US", MissingField = MissingField.UseNull]
    )
in
    Typed

