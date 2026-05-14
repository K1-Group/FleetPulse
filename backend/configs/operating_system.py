"""K1 seat-based operating system contract derived from the org-chart deck.

The data in this module is a read-only portal contract. It defines fixed seats,
their accountability relationships, KPI targets, and source-of-truth boundaries;
it does not pull, overwrite, or fabricate live Xcelerator, Geotab, QuickBooks,
or Time Doctor records.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

ORG_CHART_SOURCE = {
    "name": "k1-seat-based-org-chart.pptx",
    "sharepoint_url": "https://netorgft3187866-my.sharepoint.com/personal/rami_k1group_net/_layouts/15/Doc.aspx?sourcedoc=%7B19B6D9F7-C9E9-4278-A9CB-D23823D2638B%7D&file=k1-seat-based-org-chart.pptx&action=edit",
    "last_modified": "2026-05-13T17:34:08Z",
}

REVENUE_TARGETS = {
    "annual_target": 30_000_000,
    "monthly_target": 2_500_000,
    "weekly_target": 576_923,
    "business_day_target": 115_385,
    "gross_margin_target_percent": 18,
}

SCORECARD_WEIGHTS = {
    "kpi": 70,
    "queue_sla": 20,
    "work_evidence": 10,
}

ACCESS_BUNDLE = [
    "Employee Portal",
    "Microsoft Teams",
    "Xcelerator",
    "QuickBooks",
    "Geotab",
    "SharePoint",
]

CONFIGURATION_ITEMS = [
    {
        "name": "Operating system API key required",
        "env_var": "FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY",
        "fallback_env_var": None,
        "system": "FleetPulse",
        "secret": False,
        "purpose": "Requires API-key authentication for the seat contract endpoints.",
    },
    {
        "name": "Operating system API key",
        "env_var": "FLEETPULSE_OPERATING_SYSTEM_API_KEY",
        "fallback_env_var": "OPERATING_SYSTEM_API_KEY",
        "system": "FleetPulse",
        "secret": True,
        "purpose": "Protects the seat contract endpoints. Store production values in GitHub Secrets or Key Vault.",
    },
    {
        "name": "Xcelerator API base URL",
        "env_var": "XCELERATOR_API_BASE_URL",
        "fallback_env_var": None,
        "system": "Xcelerator",
        "secret": False,
        "purpose": "Reference pointer for future read-only Xcelerator queue and KPI adapters.",
    },
    {
        "name": "Geotab server",
        "env_var": "GEOTAB_SERVER",
        "fallback_env_var": None,
        "system": "Geotab",
        "secret": False,
        "purpose": "Telemetry authority pointer for fleet, maintenance, and safety evidence.",
    },
    {
        "name": "QuickBooks company ID",
        "env_var": "QBO_COMPANY_ID",
        "fallback_env_var": None,
        "system": "QuickBooks",
        "secret": False,
        "purpose": "Posted-accounting reference pointer for finance seat evidence.",
    },
    {
        "name": "Time Doctor API base URL",
        "env_var": "TIMEDOCTOR_API_BASE_URL",
        "fallback_env_var": None,
        "system": "Time Doctor",
        "secret": False,
        "purpose": "Work-evidence pointer for the 10% scorecard evidence lane.",
    },
    {
        "name": "SharePoint site ID",
        "env_var": "SHAREPOINT_SITE_ID",
        "fallback_env_var": None,
        "system": "SharePoint",
        "secret": False,
        "purpose": "Document, SOP, approval, and seat-assignment library pointer.",
    },
]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "required"}


@dataclass(frozen=True)
class OperatingSystemRuntimeConfig:
    api_key: str = ""
    require_api_key: bool = True
    items: tuple[dict, ...] = ()

    @classmethod
    def from_env(cls) -> "OperatingSystemRuntimeConfig":
        api_key = (
            os.getenv("FLEETPULSE_OPERATING_SYSTEM_API_KEY", "").strip()
            or os.getenv("OPERATING_SYSTEM_API_KEY", "").strip()
        )
        return cls(
            api_key=api_key,
            require_api_key=_env_bool("FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY", True),
            items=tuple(CONFIGURATION_ITEMS),
        )

    @property
    def api_key_required(self) -> bool:
        return self.require_api_key or bool(self.api_key)

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key)

    def is_authorized(self, provided_key: str | None) -> bool:
        if not self.api_key_required:
            return True
        return bool(provided_key and hmac.compare_digest(provided_key, self.api_key))

    def status_items(self) -> list[dict]:
        statuses: list[dict] = []
        for item in self.items:
            value = os.getenv(item["env_var"], "").strip()
            fallback_env_var = item.get("fallback_env_var")
            if not value and fallback_env_var:
                value = os.getenv(fallback_env_var, "").strip()
            statuses.append(
                {
                    "name": item["name"],
                    "env_var": item["env_var"],
                    "fallback_env_var": fallback_env_var,
                    "system": item["system"],
                    "secret": item["secret"],
                    "configured": bool(value),
                    "purpose": item["purpose"],
                }
            )
        return statuses


SOURCE_BOUNDARIES = [
    {
        "system": "Xcelerator",
        "entity": "K1 Group LLC",
        "authority": [
            "revenue",
            "dispatch",
            "load_lifecycle",
            "driver_pay",
            "contracts",
            "partner_management",
        ],
        "portal_rule": "Reference final operational and financial state; do not override with FleetPulse data.",
    },
    {
        "system": "Geotab",
        "entity": "K1 Logistics Inc",
        "authority": [
            "telemetry",
            "faults",
            "maintenance",
            "safety",
            "fleet_performance",
        ],
        "portal_rule": "Use telemetry as carrier operations evidence; do not write dispatch or finance state.",
    },
    {
        "system": "QuickBooks",
        "entity": "K1 Group LLC",
        "authority": ["posted_accounting", "paid_status", "cash_reporting"],
        "portal_rule": "Expose accounting status as a reference after posting; Xcelerator remains the operating control layer.",
    },
    {
        "system": "Time Doctor",
        "entity": "Shared operating support",
        "authority": ["work_evidence"],
        "portal_rule": "Use only as scorecard evidence, never as the primary KPI source.",
    },
    {
        "system": "Power BI",
        "entity": "Shared analytics",
        "authority": ["read_only_analytics"],
        "portal_rule": "Read-only rollups for management review.",
    },
]

PORTAL_WORKFLOW = [
    {
        "step": 1,
        "name": "Seat Assignment",
        "contract": "Employee is assigned to a fixed seat with effective dates.",
    },
    {
        "step": 2,
        "name": "Access Bundle",
        "contract": "Portal, Teams, Xcelerator, QBO, Geotab, and SharePoint access follows the seat.",
    },
    {
        "step": 3,
        "name": "Daily Queue",
        "contract": "Work queue and SOP are shown from the task/KPI contract.",
    },
    {
        "step": 4,
        "name": "Scorecard",
        "contract": "Outcomes dominate: KPI 70%, queue SLA 20%, Time Doctor evidence 10%.",
    },
    {
        "step": 5,
        "name": "Replace / Promote",
        "contract": "Seat score triggers coaching, replacement, or promotion decisions.",
    },
]

MANAGER_SEATS = [
    {
        "seat_id": "executive_command",
        "label": "Executive Command Seat",
        "primary_score": "monthly run rate to 30m",
        "entity_scope": "K1 Group LLC / K1 Logistics Inc",
        "source_authorities": ["Xcelerator", "Geotab", "QuickBooks", "Power BI"],
        "targets": {
            "monthly_revenue_run_rate": ">= $2,500,000",
            "gross_margin": ">= 18%",
            "critical_seat_fill_rate": "100%",
        },
        "daily_work": [
            "Review monthly run rate and margin exposure.",
            "Clear critical seat, approval, and exception blockers.",
            "Hold managers accountable to fixed seat contracts.",
        ],
    },
    {
        "seat_id": "revenue_manager",
        "label": "Revenue Manager Seat",
        "primary_score": "pipeline to booked revenue",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "SharePoint", "Power BI"],
        "targets": {
            "booked_revenue_month": ">= $1,250,000 from managed seats",
            "pipeline_coverage": ">= 3x next-60-day sales target",
            "revenue_seat_average_score": ">= 85%",
        },
        "daily_work": [
            "Manage sales seat capacity.",
            "Review pipeline coverage and booked revenue.",
            "Remove pricing, contract, and customer blockers.",
        ],
    },
    {
        "seat_id": "operations_manager",
        "label": "Operations Manager Seat",
        "primary_score": "service execution capacity",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "Geotab", "Power BI"],
        "targets": {
            "on_time_delivery_rate": ">= 95%",
            "active_load_exception_rate": "<= 5%",
            "operations_seat_average_score": ">= 85%",
        },
        "daily_work": [
            "Manage execution queues from order entry through customer service.",
            "Watch service failures and stale load states.",
            "Escalate dispatch and customer-impacting exceptions.",
        ],
    },
    {
        "seat_id": "finance_controller",
        "label": "Finance Controller Seat",
        "primary_score": "cash margin control",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "QuickBooks", "SharePoint"],
        "targets": {
            "weekly_gross_margin": ">= 18%",
            "ar_over_30_days": "<= 15% of AR",
            "finance_seat_average_score": ">= 90%",
        },
        "daily_work": [
            "Manage billing, collections, AP, and driver-pay readiness.",
            "Protect cash conversion and posted accounting controls.",
            "Approve or escalate finance exceptions.",
        ],
    },
    {
        "seat_id": "fleet_compliance_manager",
        "label": "Fleet & Compliance Manager Seat",
        "primary_score": "fleet readiness and safety",
        "entity_scope": "K1 Logistics Inc",
        "source_authorities": ["Geotab", "SharePoint", "Power BI"],
        "targets": {
            "truck_availability": ">= 90%",
            "critical_safety_actions_open": "0 past due",
            "fleet_compliance_seat_average_score": ">= 90%",
        },
        "daily_work": [
            "Manage asset readiness and safety queues.",
            "Track Geotab faults, PM compliance, and coaching actions.",
            "Escalate critical safety and compliance issues.",
        ],
    },
    {
        "seat_id": "people_systems_manager",
        "label": "People & Systems Manager Seat",
        "primary_score": "seat fill and system uptime",
        "entity_scope": "Shared operating support",
        "source_authorities": ["SharePoint", "Microsoft Teams", "Time Doctor", "Power BI"],
        "targets": {
            "seat_fill_rate": ">= 95%",
            "training_completion": "100%",
            "critical_integration_uptime": ">= 99%",
        },
        "daily_work": [
            "Manage fixed-seat assignments, training, and access lifecycle.",
            "Monitor integration health and incident follow-through.",
            "Coordinate system readiness across teams.",
        ],
    },
]

FUNCTIONAL_SEATS = [
    {
        "seat_id": "lead_generation",
        "label": "Lead Generation Seat",
        "manager_seat_id": "revenue_manager",
        "primary_score": "qualified prospect volume",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "SharePoint"],
        "daily_work": [
            "Build targeted prospect list.",
            "Research accounts and contacts.",
            "Create qualified lead records.",
            "Flag bad-fit or duplicate prospects.",
        ],
        "targets": {
            "qualified_leads_weekly": ">= 50",
            "new_opportunities_weekly": ">= 15",
            "bad_fit_rate": "<= 15%",
        },
    },
    {
        "seat_id": "sales_development",
        "label": "Sales Development Seat",
        "manager_seat_id": "revenue_manager",
        "primary_score": "qualified meeting creation",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "Microsoft Teams"],
        "daily_work": [
            "Respond to assigned leads.",
            "Run outbound call and email blocks.",
            "Book qualified meetings.",
            "Update CRM disposition for every touch.",
        ],
        "targets": {
            "first_response_time": "<= 15 min business hours",
            "meetings_booked_weekly": ">= 12",
            "show_rate": ">= 75%",
        },
    },
    {
        "seat_id": "account_executive",
        "label": "Account Executive Seat",
        "manager_seat_id": "revenue_manager",
        "primary_score": "booked revenue",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "SharePoint"],
        "daily_work": [
            "Advance open opportunities.",
            "Prepare quotes and proposals.",
            "Resolve contract and pricing blockers.",
            "Update close plans and next actions.",
        ],
        "targets": {
            "booked_revenue_monthly": ">= $250,000",
            "gross_margin_percent": ">= 18%",
            "win_rate": ">= 25%",
        },
    },
    {
        "seat_id": "account_manager",
        "label": "Account Manager Seat",
        "manager_seat_id": "revenue_manager",
        "primary_score": "retention and expansion",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "SharePoint", "Microsoft Teams"],
        "daily_work": [
            "Review account exceptions.",
            "Follow up on service failures.",
            "Identify expansion opportunities.",
            "Document customer touches.",
        ],
        "targets": {
            "retention_rate": ">= 95%",
            "revenue_expansion_monthly": ">= $50,000",
            "sla_compliance": ">= 98%",
        },
    },
    {
        "seat_id": "pricing_margin",
        "label": "Pricing & Margin Seat",
        "manager_seat_id": "revenue_manager",
        "primary_score": "quote margin compliance",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "SharePoint"],
        "daily_work": [
            "Price quote requests.",
            "Check margin rules.",
            "Flag rate exceptions.",
            "Maintain pricing notes and approval references.",
        ],
        "targets": {
            "quote_margin_compliance": ">= 98%",
            "pricing_turnaround": "<= 30 min",
            "margin_leakage": "<= 2%",
        },
    },
    {
        "seat_id": "order_entry",
        "label": "Order Entry Seat",
        "manager_seat_id": "operations_manager",
        "primary_score": "clean order creation",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator"],
        "daily_work": [
            "Validate inbound order data.",
            "Create approved Xcelerator orders.",
            "Attach required references.",
            "Resolve validation failures before dispatch.",
        ],
        "targets": {
            "first_pass_order_success": ">= 97%",
            "standard_order_entry_time": "<= 5 min",
            "validation_failure_rate": "<= 3%",
        },
    },
    {
        "seat_id": "dispatch",
        "label": "Dispatch Seat",
        "manager_seat_id": "operations_manager",
        "primary_score": "on-time dispatch execution",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "Geotab"],
        "daily_work": [
            "Review ready-to-dispatch queue.",
            "Assign and confirm drivers.",
            "Monitor acceptance warnings.",
            "Document approved dispatch actions.",
        ],
        "targets": {
            "loads_dispatched_day": ">= 8",
            "on_time_dispatch_rate": ">= 96%",
            "acceptance_sla": ">= 95%",
        },
    },
    {
        "seat_id": "track_trace",
        "label": "Track & Trace Seat",
        "manager_seat_id": "operations_manager",
        "primary_score": "status freshness and ETA accuracy",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "Geotab", "Microsoft Teams"],
        "daily_work": [
            "Monitor stale statuses.",
            "Update customers on ETA risk.",
            "Use Geotab location references for visibility.",
            "Escalate pickup or delivery exceptions.",
        ],
        "targets": {
            "check_call_compliance": ">= 98%",
            "eta_accuracy": "+/- 30 min",
            "same_day_exception_resolution": ">= 95%",
        },
    },
    {
        "seat_id": "capacity_coverage",
        "label": "Capacity Coverage Seat",
        "manager_seat_id": "operations_manager",
        "primary_score": "covered load board",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "SharePoint"],
        "daily_work": [
            "Review uncovered load board.",
            "Contact approved carriers.",
            "Confirm carrier documents are valid.",
            "Record lane coverage and rate evidence.",
        ],
        "targets": {
            "lane_coverage": "100% of active board",
            "carrier_acceptance_rate": ">= 40%",
            "rate_savings": ">= 3% below target where safe",
        },
    },
    {
        "seat_id": "customer_service",
        "label": "Customer Service Seat",
        "manager_seat_id": "operations_manager",
        "primary_score": "customer issue resolution",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "Microsoft Teams", "SharePoint"],
        "daily_work": [
            "Respond to customer requests.",
            "Open and update service cases.",
            "Coordinate with operations on exceptions.",
            "Close resolved issues with notes.",
        ],
        "targets": {
            "customer_first_response": "<= 2 business hours",
            "issue_resolution_rate": ">= 90%",
            "escalation_rate": "<= 5%",
        },
    },
    {
        "seat_id": "billing",
        "label": "Billing Seat",
        "manager_seat_id": "finance_controller",
        "primary_score": "invoice readiness",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "QuickBooks", "SharePoint"],
        "daily_work": [
            "Review delivered-not-invoice-ready queue.",
            "Verify POD and billing packet.",
            "Create or clear invoice-ready exceptions.",
            "Attach billing evidence and approval references.",
        ],
        "targets": {
            "delivered_to_invoice_ready": "<= 24 hours",
            "invoice_completeness": ">= 97%",
            "billing_exception_aging": "<= 5% over 48h",
        },
    },
    {
        "seat_id": "ar",
        "label": "AR Seat",
        "manager_seat_id": "finance_controller",
        "primary_score": "cash collection discipline",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["QuickBooks", "Xcelerator", "SharePoint"],
        "daily_work": [
            "Review past-due invoices.",
            "Send collection touches.",
            "Record promise-to-pay notes.",
            "Escalate disputed balances.",
        ],
        "targets": {
            "ar_aging_30_percent": "<= 15% of AR",
            "cash_collected_weekly": ">= forecast",
            "collection_touch_compliance": "100% due accounts",
        },
    },
    {
        "seat_id": "ap",
        "label": "AP Seat",
        "manager_seat_id": "finance_controller",
        "primary_score": "clean payable processing",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["QuickBooks", "Xcelerator", "SharePoint"],
        "daily_work": [
            "Process vendor invoices.",
            "Match invoice to load or PO.",
            "Flag duplicate-payment risk.",
            "Route exceptions for approval.",
        ],
        "targets": {
            "invoices_processed_day": ">= 50",
            "ap_aging_30_percent": "<= 10%",
            "duplicate_payment_rate": "0",
        },
    },
    {
        "seat_id": "driver_pay_settlement",
        "label": "Driver Pay Settlement Seat",
        "manager_seat_id": "finance_controller",
        "primary_score": "settlement accuracy",
        "entity_scope": "K1 Group LLC",
        "source_authorities": ["Xcelerator", "SharePoint"],
        "daily_work": [
            "Review driver-pay readiness.",
            "Research pay exceptions.",
            "Verify Xcelerator settlement data.",
            "Document disputes and approval references.",
        ],
        "targets": {
            "settlement_accuracy": ">= 99%",
            "pay_exception_resolution": "<= 1 business day",
            "unsupported_override_count": "0",
        },
    },
    {
        "seat_id": "fleet_maintenance",
        "label": "Fleet Maintenance Seat",
        "manager_seat_id": "fleet_compliance_manager",
        "primary_score": "fleet readiness",
        "entity_scope": "K1 Logistics Inc",
        "source_authorities": ["Geotab", "SharePoint"],
        "daily_work": [
            "Review Geotab faults.",
            "Track PM due items.",
            "Coordinate repairs.",
            "Update maintenance evidence.",
        ],
        "targets": {
            "pm_compliance": "100%",
            "out_of_service_rate": "<= 5%",
            "mean_time_to_repair": "<= 4 hours",
        },
    },
    {
        "seat_id": "safety_compliance",
        "label": "Safety & Compliance Seat",
        "manager_seat_id": "fleet_compliance_manager",
        "primary_score": "safety action closure",
        "entity_scope": "K1 Logistics Inc",
        "source_authorities": ["Geotab", "SharePoint", "Power BI"],
        "daily_work": [
            "Review HOS and safety alerts.",
            "Open coaching tasks.",
            "Track compliance documents.",
            "Escalate critical violations.",
        ],
        "targets": {
            "hos_violations_30d": "0",
            "coaching_completion": "100%",
            "incident_rate": "< 1 per million miles",
        },
    },
    {
        "seat_id": "seat_admin_hr",
        "label": "Seat Admin / HR Seat",
        "manager_seat_id": "people_systems_manager",
        "primary_score": "seat lifecycle readiness",
        "entity_scope": "Shared operating support",
        "source_authorities": ["SharePoint", "Microsoft Teams", "Time Doctor"],
        "daily_work": [
            "Review open seats.",
            "Process seat assignments.",
            "Trigger access grant or revoke.",
            "Track training completion.",
        ],
        "targets": {
            "days_to_fill_seat": "<= 21 days",
            "training_completion": "100%",
            "access_deprovision_sla": "<= 4 hours",
        },
    },
    {
        "seat_id": "systems_operator",
        "label": "Systems Operator Seat",
        "manager_seat_id": "people_systems_manager",
        "primary_score": "integration reliability",
        "entity_scope": "Shared operating support",
        "source_authorities": ["SharePoint", "Microsoft Teams", "Power BI"],
        "daily_work": [
            "Review integration health.",
            "Resolve failed jobs.",
            "Check secret and webhook status.",
            "Document incidents.",
        ],
        "targets": {
            "integration_uptime": ">= 99%",
            "failed_job_resolution": "<= 4 hours",
            "secret_rotation_compliance": "100%",
        },
    },
]

MANAGEMENT_TREE = [
    {
        "manager_seat_id": "executive_command",
        "functional_seat_ids": [
            "revenue_manager",
            "operations_manager",
            "finance_controller",
            "fleet_compliance_manager",
            "people_systems_manager",
        ],
    },
    {
        "manager_seat_id": "revenue_manager",
        "functional_seat_ids": [
            "lead_generation",
            "sales_development",
            "account_executive",
            "account_manager",
            "pricing_margin",
        ],
    },
    {
        "manager_seat_id": "operations_manager",
        "functional_seat_ids": [
            "order_entry",
            "dispatch",
            "track_trace",
            "capacity_coverage",
            "customer_service",
        ],
    },
    {
        "manager_seat_id": "finance_controller",
        "functional_seat_ids": ["billing", "ar", "ap", "driver_pay_settlement"],
    },
    {
        "manager_seat_id": "fleet_compliance_manager",
        "functional_seat_ids": ["fleet_maintenance", "safety_compliance"],
    },
    {
        "manager_seat_id": "people_systems_manager",
        "functional_seat_ids": ["seat_admin_hr", "systems_operator"],
    },
]
