// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/lane-stability/lanes",
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
                    status = text,
                    status_rank = Int64.Type,
                    orders = Int64.Type,
                    unique_drivers = Int64.Type,
                    stable_driver = text,
                    stable_runs = Int64.Type,
                    stable_cov_pct = number,
                    swaps = Int64.Type,
                    swap_rate_pct = number,
                    revenue = number,
                    gm = number,
                    gm_pct = number,
                    driver_pay = number,
                    num_routes = Int64.Type,
                    primary_route = text,
                    primary_route_pct = number,
                    cross_route = logical,
                    routes_used = text,
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
            {"status", type text},
            {"status_rank", Int64.Type},
            {"orders", Int64.Type},
            {"unique_drivers", Int64.Type},
            {"stable_driver", type text},
            {"stable_runs", Int64.Type},
            {"stable_cov_pct", type number},
            {"swaps", Int64.Type},
            {"swap_rate_pct", type number},
            {"revenue", type number},
            {"gm", type number},
            {"gm_pct", type number},
            {"driver_pay", type number},
            {"num_routes", Int64.Type},
            {"primary_route", type text},
            {"primary_route_pct", type number},
            {"cross_route", type logical},
            {"routes_used", type text},
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

