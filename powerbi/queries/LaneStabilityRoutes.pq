// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/lane-stability/routes",
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
                    feed_status = text,
                    service = text,
                    lane = text,
                    route = text,
                    orders = Int64.Type,
                    route_pct_of_lane = number,
                    primary_driver = text,
                    primary_driver_runs = Int64.Type,
                    route_stable_cov_pct = number,
                    lane_stable_cov_pct = number,
                    lane_status = text,
                    lane_status_rank = Int64.Type,
                    revenue = number,
                    gm = number,
                    gm_pct = number,
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
            {"feed_status", type text},
            {"service", type text},
            {"lane", type text},
            {"route", type text},
            {"orders", Int64.Type},
            {"route_pct_of_lane", type number},
            {"primary_driver", type text},
            {"primary_driver_runs", Int64.Type},
            {"route_stable_cov_pct", type number},
            {"lane_stable_cov_pct", type number},
            {"lane_status", type text},
            {"lane_status_rank", Int64.Type},
            {"revenue", type number},
            {"gm", type number},
            {"gm_pct", type number},
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

