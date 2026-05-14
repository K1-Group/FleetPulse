// Requires Power BI text parameter:
// FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net

let
    StartDate = Date.ToText(Date.StartOfYear(Date.From(DateTimeZone.FixedUtcNow())), "yyyy-MM-dd"),
    EndDate = Date.ToText(Date.From(DateTimeZone.FixedUtcNow()), "yyyy-MM-dd"),
    Source = Json.Document(
        Web.Contents(
            FleetPulseBaseUrl,
            [
                RelativePath = "api/powerbi/operating-cost/summary",
                Query = [start = StartDate, end = EndDate]
            ]
        )
    ),
    Rows =
        if List.Count(Source) = 0 then
            #table(
                type table [
                    period_start = date,
                    period_end = date,
                    generated_at = datetimezone,
                    complete_cost_available = logical,
                    unresolved_sources = text,
                    miles = number,
                    drive_hours = number,
                    idle_hours = number,
                    operating_hours = number,
                    trips = Int64.Type,
                    fuel_cost = number,
                    driver_pay = number,
                    insurance_cost = number,
                    other_expense_cost = number,
                    known_operating_cost = number,
                    true_operating_cost = number,
                    known_cost_per_mile = number,
                    true_cost_per_mile = number,
                    known_cost_per_drive_hour = number,
                    true_cost_per_drive_hour = number,
                    known_cost_per_operating_hour = number,
                    true_cost_per_operating_hour = number,
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
            {"generated_at", type datetimezone},
            {"complete_cost_available", type logical},
            {"unresolved_sources", type text},
            {"miles", type number},
            {"drive_hours", type number},
            {"idle_hours", type number},
            {"operating_hours", type number},
            {"trips", Int64.Type},
            {"fuel_cost", type number},
            {"driver_pay", type number},
            {"insurance_cost", type number},
            {"other_expense_cost", type number},
            {"known_operating_cost", type number},
            {"true_operating_cost", type number},
            {"known_cost_per_mile", type number},
            {"true_cost_per_mile", type number},
            {"known_cost_per_drive_hour", type number},
            {"true_cost_per_drive_hour", type number},
            {"known_cost_per_operating_hour", type number},
            {"true_cost_per_operating_hour", type number},
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
