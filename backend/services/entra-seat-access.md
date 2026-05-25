# FleetPulse Entra Seat Access

`entra_seat_access_service.py` maps Microsoft Entra security-group claims from
Azure App Service Authentication into FleetPulse seat metadata.

- Entra remains authoritative for identity and group membership.
- FleetPulse only projects the signed-in user's seats, allowed UI tabs, and
  optional API enforcement decisions.
- The projection does not write to Xcelerator, Geotab, SharePoint, Power BI, or
  Microsoft Entra.

Configure group object IDs with `FLEETPULSE_ENTRA_SEAT_GROUPS_JSON`; keep
`FLEETPULSE_ENTRA_SEAT_ACCESS_ENFORCED=false` until the seat rollout has been
verified with assigned users.
