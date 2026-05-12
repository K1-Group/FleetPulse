// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/lane-stability/company",
                Query = [days = "7"]
            ]
        )
    ),
    Rows = Table.FromRecords(Source),
    Typed = Table.TransformColumnTypes(
        Rows,
        {
            {"period_start", type date},
            {"period_end", type date},
            {"generated_at", type datetimezone},
            {"feed_status", type text},
            {"feed_message", type text},
            {"total_orders", Int64.Type},
            {"billed_orders", Int64.Type},
            {"total_revenue", type number},
            {"total_revenue_source", type text},
            {"total_gm", type number},
            {"gm_pct", type number},
            {"total_driver_pay", type number},
            {"team_subset_revenue", type number},
            {"team_subset_gm", type number},
            {"weighted_stable_cov_pct", type number},
            {"baseline_weighted_stable_cov_pct", type number},
            {"delta_vs_baseline_pct", type number},
            {"total_lanes", Int64.Type},
            {"critical", Int64.Type},
            {"at_risk", Int64.Type},
            {"watch", Int64.Type},
            {"stable", Int64.Type},
            {"cross_route_lanes", Int64.Type},
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

