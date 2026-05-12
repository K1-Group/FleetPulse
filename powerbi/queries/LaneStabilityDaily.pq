// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/lane-stability/daily",
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
                    date = date,
                    orders = Int64.Type,
                    active_lanes = Int64.Type,
                    active_drivers = Int64.Type,
                    revenue = number,
                    gm = number,
                    driver_pay = number,
                    daily_stable_cov_pct = number,
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
            {"date", type date},
            {"orders", Int64.Type},
            {"active_lanes", Int64.Type},
            {"active_drivers", Int64.Type},
            {"revenue", type number},
            {"gm", type number},
            {"driver_pay", type number},
            {"daily_stable_cov_pct", type number},
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

