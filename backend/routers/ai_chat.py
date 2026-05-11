"""AI Chat Router - Intelligent fleet query processing."""

from __future__ import annotations

import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Literal

import anthropic
import openai
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

router = APIRouter()

# Provider type definition
ProviderType = Literal["anthropic", "openrouter", "demo"]
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4"

# In-memory storage for API configurations (not persisted to disk for security)
_ai_config = {
    "provider": "demo",
    "api_key": None,
    "client": None
}


def _get_anthropic_model() -> str:
    """Return the configured Anthropic model."""
    configured = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL).strip()
    return configured or DEFAULT_ANTHROPIC_MODEL


def _get_openrouter_model() -> str:
    """Return the configured OpenRouter model."""
    configured = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
    return configured or DEFAULT_OPENROUTER_MODEL


def _get_openrouter_headers() -> dict[str, str] | None:
    """Return optional OpenRouter attribution headers."""
    headers = {}
    site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
    app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers or None


def _build_openrouter_client(api_key: str) -> openai.OpenAI:
    """Build an OpenRouter client with optional attribution headers."""
    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": "https://openrouter.ai/api/v1",
    }
    headers = _get_openrouter_headers()
    if headers:
        kwargs["default_headers"] = headers
    return openai.OpenAI(**kwargs)

def _set_api_key(api_key: str, provider: ProviderType) -> bool:
    """Set API key and provider in memory and initialize client."""
    global _ai_config
    
    try:
        if provider == "anthropic":
            # Test Anthropic API key
            test_client = anthropic.Anthropic(api_key=api_key)
            test_response = test_client.messages.create(
                model=_get_anthropic_model(),
                max_tokens=10,
                messages=[{"role": "user", "content": "Test"}]
            )
            
            _ai_config = {
                "provider": "anthropic",
                "api_key": api_key,
                "client": test_client
            }
            return True
            
        elif provider == "openrouter":
            # Test OpenRouter API key
            test_client = _build_openrouter_client(api_key)
            
            # Test with a minimal request
            test_response = test_client.chat.completions.create(
                model=_get_openrouter_model(),
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )
            
            _ai_config = {
                "provider": "openrouter", 
                "api_key": api_key,
                "client": test_client
            }
            return True
            
        else:
            return False
        
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        status_text = f" status={status_code}" if status_code else ""
        print(f"API key validation failed for {provider}: {type(e).__name__}{status_text}")
        return False


# Initialize from environment variables if available
def _initialize_from_env():
    """Initialize AI client from environment variables."""
    global _ai_config

    if _is_ai_enabled():
        return

    # Check for Anthropic API key
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key and anthropic_key != "your-key-here":
        success = _set_api_key(anthropic_key, "anthropic")
        if success:
            return

    # Check for OpenRouter API key
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and openrouter_key != "your-key-here":
        success = _set_api_key(openrouter_key, "openrouter")
        if success:
            return


def _ensure_env_initialized() -> None:
    """Retry environment-backed setup for late Key Vault reference resolution."""

    if not _is_ai_enabled():
        _initialize_from_env()


def _get_ai_client():
    """Get the current AI client if available."""
    return _ai_config.get("client")


def _get_provider() -> ProviderType:
    """Get current provider."""
    return _ai_config.get("provider", "demo")


def _is_ai_enabled() -> bool:
    """Check if AI is enabled (API key is set)."""
    return _ai_config.get("client") is not None and _ai_config.get("provider") != "demo"


# Initialize on module load, after helpers it calls are defined.
_initialize_from_env()


def _get_model_name() -> str:
    """Get the model name based on provider."""
    provider = _get_provider()
    if provider == "anthropic":
        return _get_anthropic_model()
    elif provider == "openrouter":
        return _get_openrouter_model()
    else:
        return "pattern-matching"


def _get_provider_display_name() -> str:
    """Get human-readable provider name."""
    provider = _get_provider()
    if provider == "anthropic":
        return "Anthropic API"
    elif provider == "openrouter":
        return "OpenRouter (Claude Max/Pro)"
    else:
        return "Demo Mode"


async def _fetch_fleet_context() -> str:
    """Fetch current fleet data to provide context to Claude."""
    try:
        # Import here to avoid circular imports
        from services.fleet_service import get_fleet_overview
        from services.alert_service import get_recent_alerts
        from services.safety_service import get_safety_scores
        
        # Fetch current data (with fallback to mock data)
        try:
            fleet_overview = get_fleet_overview()
            alerts = get_recent_alerts()
            safety_scores = get_safety_scores()
        except:
            # Fallback to mock data if services aren't available
            fleet_overview = {
                "total_vehicles": 50,
                "active_vehicles": 42,
                "idle_vehicles": 8,
                "avg_utilization": 74,
                "fuel_efficiency": 8.2
            }
            alerts = [
                {"type": "maintenance", "priority": "high", "message": "Vehicle V023 needs brake service in 3 days"},
                {"type": "idle", "priority": "medium", "message": "8 vehicles idle > 2 hours at Fort Worth"},
                {"type": "safety", "priority": "low", "message": "New driver training module available"}
            ]
            safety_scores = FLEET_DATA["safety_scores"]
        
        context = f"""CURRENT FLEET STATUS:
Fleet Overview: {fleet_overview}

Active Alerts: {alerts}

Safety Scores by Location: {safety_scores}

Recent Performance Data:
- Idle Time Analysis: {FLEET_DATA['idle_analysis'][:3]}  
- Fuel Efficiency: {FLEET_DATA['fuel_efficiency'][-3:]}
- Maintenance Predictions: {FLEET_DATA['maintenance_predictions']}
"""
        
        return context
        
    except Exception as e:
        print(f"Error fetching fleet context: {e}")
        return "Fleet data temporarily unavailable."


CLAUDE_SYSTEM_PROMPT = """You are FleetPulse AI, an advanced fleet management intelligence assistant for K1 Logistics. You help fleet managers optimize operations across 4 locations with 50+ vehicles.

ABOUT FLEETPULSE:
FleetPulse is a GeoTab-powered fleet management platform that provides real-time analytics for:
- Vehicle tracking and utilization
- Safety scoring and incident management  
- Fuel efficiency monitoring
- Predictive maintenance
- Route optimization
- Driver behavior analysis
- Cost optimization recommendations

YOUR ROLE:
- Analyze fleet data and provide actionable insights
- Answer questions about vehicle performance, safety, maintenance, and costs
- Generate charts and visualizations (specify chart_type: bar, line, pie)
- Provide specific recommendations with estimated ROI
- Explain complex fleet metrics in simple terms
- Suggest optimizations based on data patterns

RESPONSE FORMAT:
Always provide:
1. Direct answer to the question
2. Supporting data (if relevant) 
3. Actionable insights or recommendations
4. Potential cost impact/savings

For visualizations, structure your response with:
- response: Main answer text
- data: Array of objects for charting
- chart_type: "bar", "line", or "pie"  
- insights: Array of key takeaways

FLEET LOCATIONS:
1. Fort Worth - Main hub, highest safety scores
2. Fort Worth - Efficient operations, good maintenance compliance
3. Justin TX - Airport location, high utilization
4. Kansas City - Residential area, moderate traffic
5. OKC - Business district, peak 9-5 demand
6. Justin TX - Tourism area, 24/7 operations
7. Fort Worth - High idle times, needs optimization
8. OKC - Growing market, infrastructure challenges

Be data-driven, specific, and focus on operational improvements that save money or improve safety."""


class ChatMessage(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = []
    timestamp: Optional[datetime] = None


class ChatResponse(BaseModel):
    response: str
    data: Optional[List[Dict[str, Any]]] = None
    chart_type: Optional[str] = None
    insights: Optional[List[str]] = None
    confidence: float = 0.95
    model: Optional[str] = None
    is_ai_powered: bool = False


class FleetInsight(BaseModel):
    type: str
    priority: str
    title: str
    message: str
    impact: str
    action: str


class ApiKeyRequest(BaseModel):
    api_key: str
    provider: ProviderType = "anthropic"


class ConfigResponse(BaseModel):
    ai_enabled: bool
    model: Optional[str] = None
    provider: ProviderType = "demo"
    provider_name: str = "Demo Mode"


# Mock fleet data for intelligent responses
FLEET_DATA = {
    "safety_scores": [
        {"location": "Fort Worth", "score": 94, "incidents": 1, "trend": "improving"},
        {"location": "Fort Worth", "score": 93, "incidents": 1, "trend": "stable"},
        {"location": "Justin TX", "score": 92, "incidents": 2, "trend": "stable"},
        {"location": "Kansas City", "score": 91, "incidents": 2, "trend": "improving"},
        {"location": "OKC", "score": 89, "incidents": 3, "trend": "declining"},
        {"location": "Justin TX", "score": 88, "incidents": 4, "trend": "stable"},
        {"location": "Fort Worth", "score": 87, "incidents": 4, "trend": "concerning"},
        {"location": "OKC", "score": 85, "incidents": 5, "trend": "needs_attention"},
    ],
    "idle_analysis": [
        {"location": "Fort Worth", "avg_idle_minutes": 180, "vehicles_affected": 8, "cost_impact": 2400},
        {"location": "OKC", "avg_idle_minutes": 165, "vehicles_affected": 6, "cost_impact": 1980},
        {"location": "Justin TX", "avg_idle_minutes": 120, "vehicles_affected": 9, "cost_impact": 1620},
        {"location": "OKC", "avg_idle_minutes": 95, "vehicles_affected": 7, "cost_impact": 950},
        {"location": "Justin TX", "avg_idle_minutes": 75, "vehicles_affected": 5, "cost_impact": 750},
        {"location": "Kansas City", "avg_idle_minutes": 65, "vehicles_affected": 4, "cost_impact": 520},
        {"location": "Fort Worth", "avg_idle_minutes": 45, "vehicles_affected": 3, "cost_impact": 360},
        {"location": "Fort Worth", "avg_idle_minutes": 35, "vehicles_affected": 2, "cost_impact": 280},
    ],
    "fuel_efficiency": [
        {"date": "2024-02-05", "efficiency": 8.2, "cost_per_100km": 12.30},
        {"date": "2024-02-06", "efficiency": 7.8, "cost_per_100km": 11.70},
        {"date": "2024-02-07", "efficiency": 8.5, "cost_per_100km": 12.75},
        {"date": "2024-02-08", "efficiency": 8.1, "cost_per_100km": 12.15},
        {"date": "2024-02-09", "efficiency": 7.9, "cost_per_100km": 11.85},
        {"date": "2024-02-10", "efficiency": 8.3, "cost_per_100km": 12.45},
        {"date": "2024-02-11", "efficiency": 8.6, "cost_per_100km": 12.90},
    ],
    "maintenance_predictions": [
        {"vehicle_id": "V023", "type": "brake_pads", "days_until_service": 5, "confidence": 0.92, "cost_estimate": 280},
        {"vehicle_id": "V045", "type": "oil_change", "days_until_service": 2, "confidence": 0.98, "cost_estimate": 65},
        {"vehicle_id": "V031", "type": "tire_rotation", "days_until_service": 12, "confidence": 0.87, "cost_estimate": 120},
        {"vehicle_id": "V018", "type": "transmission", "days_until_service": 15, "confidence": 0.74, "cost_estimate": 850},
    ],
    "utilization_patterns": [
        {"hour": "06:00", "utilization": 24, "demand": "low", "cost_per_hour": 45},
        {"hour": "08:00", "utilization": 56, "demand": "medium", "cost_per_hour": 78},
        {"hour": "10:00", "utilization": 70, "demand": "medium", "cost_per_hour": 95},
        {"hour": "12:00", "utilization": 84, "demand": "high", "cost_per_hour": 125},
        {"hour": "14:00", "utilization": 76, "demand": "high", "cost_per_hour": 110},
        {"hour": "16:00", "utilization": 90, "demand": "peak", "cost_per_hour": 145},
        {"hour": "18:00", "utilization": 64, "demand": "medium", "cost_per_hour": 85},
        {"hour": "20:00", "utilization": 36, "demand": "low", "cost_per_hour": 55},
    ]
}

# Advanced pattern matching for natural language queries
QUERY_PATTERNS = [
    {
        "patterns": [r"safety|safest|dangerous|accident|incident|score", r"location|where|which"],
        "handler": "safety_analysis",
        "confidence": 0.95
    },
    {
        "patterns": [r"idle|idling|waste|stationary|parked"],
        "handler": "idle_analysis", 
        "confidence": 0.92
    },
    {
        "patterns": [r"fuel|gas|efficiency|consumption|mpg|cost"],
        "handler": "fuel_analysis",
        "confidence": 0.90
    },
    {
        "patterns": [r"maintenance|repair|service|predict|due"],
        "handler": "maintenance_predictions",
        "confidence": 0.93
    },
    {
        "patterns": [r"utilization|busy|active|peak|usage|demand"],
        "handler": "utilization_analysis",
        "confidence": 0.88
    },
    {
        "patterns": [r"recommend|suggest|optimize|save|cost.?saving"],
        "handler": "cost_optimization",
        "confidence": 0.91
    },
    {
        "patterns": [r"vehicle.*\d+|specific.*vehicle|vehicle.*#"],
        "handler": "vehicle_specific",
        "confidence": 0.85
    }
]


def analyze_query(message: str) -> tuple[str, float]:
    """Analyze user query and determine the best handler."""
    message_lower = message.lower()
    
    best_handler = "general"
    best_confidence = 0.3
    
    for pattern_group in QUERY_PATTERNS:
        matches = 0
        for pattern in pattern_group["patterns"]:
            if re.search(pattern, message_lower):
                matches += 1
        
        if matches > 0:
            confidence = pattern_group["confidence"] * (matches / len(pattern_group["patterns"]))
            if confidence > best_confidence:
                best_handler = pattern_group["handler"]
                best_confidence = confidence
    
    return best_handler, best_confidence


def safety_analysis_handler(message: str) -> ChatResponse:
    """Handle safety-related queries."""
    data = FLEET_DATA["safety_scores"]
    
    # Sort by score for better insights
    sorted_data = sorted(data, key=lambda x: x["score"], reverse=True)
    
    insights = [
        f"Best performers: {sorted_data[0]['location']} ({sorted_data[0]['score']}%) and {sorted_data[1]['location']} ({sorted_data[1]['score']}%)",
        f"Attention needed: {sorted_data[-1]['location']} with {sorted_data[-1]['score']}% - {sorted_data[-1]['incidents']} incidents this month",
        f"Fleet average safety score: {sum(loc['score'] for loc in data) / len(data):.1f}%"
    ]
    
    # Check for specific location mentions
    message_lower = message.lower()
    mentioned_location = None
    for location_data in data:
        if location_data["location"].lower().replace(" ", "").replace(".", "") in message_lower.replace(" ", ""):
            mentioned_location = location_data
            break
    
    if mentioned_location:
        response = f"Safety analysis for {mentioned_location['location']}: {mentioned_location['score']}% safety score with {mentioned_location['incidents']} incidents. Status: {mentioned_location['trend'].replace('_', ' ')}"
    else:
        response = f"Safety score analysis across all {len(data)} locations. Here's the current ranking:"
    
    return ChatResponse(
        response=response,
        data=[{"location": loc["location"], "score": loc["score"], "color": "#10b981" if loc["score"] >= 90 else "#f59e0b" if loc["score"] >= 85 else "#ef4444"} for loc in sorted_data],
        chart_type="bar",
        insights=insights,
        confidence=0.95
    )


def idle_analysis_handler(message: str) -> ChatResponse:
    """Handle idle time queries."""
    data = FLEET_DATA["idle_analysis"]
    
    # Check for specific time threshold
    time_threshold = None
    time_matches = re.search(r"(\d+)\s*(min|minute|hour)", message.lower())
    if time_matches:
        time_threshold = int(time_matches.group(1))
        if "hour" in time_matches.group(2):
            time_threshold *= 60
    
    if time_threshold:
        filtered_vehicles = [loc for loc in data if loc["avg_idle_minutes"] > time_threshold]
        total_affected = sum(loc["vehicles_affected"] for loc in filtered_vehicles)
        response = f"Found {total_affected} vehicles across {len(filtered_vehicles)} locations with idle time exceeding {time_threshold} minutes:"
    else:
        response = "Idle time analysis across all locations. Fort Worth and OKC need immediate attention:"
    
    insights = [
        f"Highest idle time: {data[0]['location']} with {data[0]['avg_idle_minutes']} minutes average",
        f"Total monthly cost impact: ${sum(loc['cost_impact'] for loc in data):,}",
        f"Quick win: Focus on {data[0]['location']} - potential ${data[0]['cost_impact']:,}/month savings"
    ]
    
    return ChatResponse(
        response=response,
        data=[{"location": loc["location"], "minutes": loc["avg_idle_minutes"], "color": "#ef4444" if loc["avg_idle_minutes"] > 120 else "#f59e0b" if loc["avg_idle_minutes"] > 60 else "#10b981"} for loc in data[:8]],
        chart_type="bar",
        insights=insights,
        confidence=0.92
    )


def fuel_analysis_handler(message: str) -> ChatResponse:
    """Handle fuel efficiency queries."""
    data = FLEET_DATA["fuel_efficiency"]
    
    avg_efficiency = sum(day["efficiency"] for day in data) / len(data)
    avg_cost = sum(day["cost_per_100km"] for day in data) / len(data)
    
    insights = [
        f"7-day average efficiency: {avg_efficiency:.1f} L/100km (${avg_cost:.2f}/100km)",
        f"Best day: {min(data, key=lambda x: x['efficiency'])['date']} with {min(data, key=lambda x: x['efficiency'])['efficiency']} L/100km",
        f"Trend: {'Improving' if data[-1]['efficiency'] > data[0]['efficiency'] else 'Stable' if abs(data[-1]['efficiency'] - data[0]['efficiency']) < 0.2 else 'Declining'}"
    ]
    
    return ChatResponse(
        response="Fuel efficiency analysis for the past 7 days:",
        data=[{"day": day["date"][-5:], "efficiency": day["efficiency"]} for day in data],
        chart_type="line",
        insights=insights,
        confidence=0.90
    )


def maintenance_predictions_handler(message: str) -> ChatResponse:
    """Handle maintenance prediction queries."""
    data = FLEET_DATA["maintenance_predictions"]
    
    # Sort by urgency
    sorted_data = sorted(data, key=lambda x: x["days_until_service"])
    
    total_cost = sum(item["cost_estimate"] for item in data)
    urgent_count = len([item for item in data if item["days_until_service"] <= 7])
    
    insights = [
        f"Urgent maintenance needed: {urgent_count} vehicles within 7 days",
        f"Most urgent: Vehicle {sorted_data[0]['vehicle_id']} - {sorted_data[0]['type']} in {sorted_data[0]['days_until_service']} days",
        f"Total predicted maintenance cost: ${total_cost:,} over next 30 days"
    ]
    
    return ChatResponse(
        response=f"Predictive maintenance analysis for {len(data)} vehicles:",
        data=[{"vehicle": item["vehicle_id"], "type": item["type"], "days": item["days_until_service"], "confidence": item["confidence"] * 100, "color": "#ef4444" if item["days_until_service"] <= 3 else "#f59e0b" if item["days_until_service"] <= 7 else "#10b981"} for item in sorted_data],
        chart_type="bar",
        insights=insights,
        confidence=0.93
    )


def utilization_analysis_handler(message: str) -> ChatResponse:
    """Handle utilization pattern queries."""
    data = FLEET_DATA["utilization_patterns"]
    
    peak_hour = max(data, key=lambda x: x["utilization"])
    low_hour = min(data, key=lambda x: x["utilization"])
    
    insights = [
        f"Peak utilization: {peak_hour['utilization']}% at {peak_hour['hour']}",
        f"Lowest utilization: {low_hour['utilization']}% at {low_hour['hour']} (maintenance window opportunity)",
        f"Daily revenue potential: ${sum(hour['cost_per_hour'] for hour in data):,} at current rates"
    ]
    
    return ChatResponse(
        response="Fleet utilization patterns throughout the day:",
        data=[{"hour": hour["hour"], "rate": hour["utilization"]} for hour in data],
        chart_type="line",
        insights=insights,
        confidence=0.88
    )


def cost_optimization_handler(message: str) -> ChatResponse:
    """Handle cost optimization and recommendation queries."""
    recommendations = [
        {"category": "Route Optimization", "savings": 2400, "color": "#10b981"},
        {"category": "Idle Reduction", "savings": 1800, "color": "#3b82f6"},
        {"category": "Maintenance Scheduling", "savings": 1200, "color": "#8b5cf6"},
        {"category": "Driver Training", "savings": 900, "color": "#f59e0b"},
        {"category": "Fuel Management", "savings": 600, "color": "#06b6d4"},
    ]
    
    total_savings = sum(rec["savings"] for rec in recommendations)
    
    insights = [
        f"Total monthly savings potential: ${total_savings:,}",
        f"Top opportunity: {recommendations[0]['category']} - ${recommendations[0]['savings']}/month",
        f"ROI timeline: 3-6 months payback on optimization investments"
    ]
    
    return ChatResponse(
        response="AI-generated cost optimization recommendations based on current fleet data:",
        data=recommendations,
        chart_type="pie",
        insights=insights,
        confidence=0.91
    )


def vehicle_specific_handler(message: str) -> ChatResponse:
    """Handle vehicle-specific queries."""
    # Extract vehicle number from message
    vehicle_match = re.search(r"(?:vehicle|#)\s*(\d+)", message.lower())
    if vehicle_match:
        vehicle_num = vehicle_match.group(1)
        # Generate mock vehicle data
        vehicle_data = {
            "id": f"V{vehicle_num.zfill(3)}",
            "status": "active",
            "location": "Fort Worth",
            "idle_time": 120,
            "fuel_efficiency": 8.4,
            "safety_score": 87,
            "last_maintenance": "2024-01-15",
            "next_service": "2024-02-20"
        }
        
        return ChatResponse(
            response=f"Vehicle #{vehicle_num} analysis:",
            data=[vehicle_data],
            insights=[
                f"Current status: {vehicle_data['status']} at {vehicle_data['location']}",
                f"Performance: {vehicle_data['fuel_efficiency']} L/100km, Safety score {vehicle_data['safety_score']}%",
                f"Service due: {vehicle_data['next_service']}"
            ],
            confidence=0.85
        )
    
    return general_handler(message)


def general_handler(message: str) -> ChatResponse:
    """Handle general queries that don't match specific patterns."""
    return ChatResponse(
        response="I understand you're asking about fleet operations. I can help you with safety scores, idle time analysis, fuel efficiency, maintenance predictions, utilization patterns, and cost optimization recommendations. Try asking something like 'Which location has the best safety scores?' or 'Show me vehicles with high idle time.'",
        confidence=0.3
    )


async def _process_ai_query(message: str, conversation_history: List[Dict[str, str]]) -> ChatResponse:
    """Process query using AI (Anthropic or OpenRouter)."""
    client = _get_ai_client()
    provider = _get_provider()
    
    if not client or provider == "demo":
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        # Fetch current fleet context
        fleet_context = await _fetch_fleet_context()
        
        # Build conversation history
        messages = []
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Last 10 messages for context
            role = "user" if msg.get("type") == "user" else "assistant"
            messages.append({"role": role, "content": msg.get("content", "")})
        
        # Add current message with fleet context
        current_message = f"""CURRENT FLEET DATA:
{fleet_context}

USER QUESTION: {message}

Please analyze this question in the context of the current fleet data and provide insights, recommendations, and any relevant visualizations."""

        messages.append({"role": "user", "content": current_message})
        
        # Call AI service based on provider
        response_text = ""
        
        if provider == "anthropic":
            # Direct Anthropic API
            response = client.messages.create(
                model=_get_anthropic_model(),
                max_tokens=2000,
                system=CLAUDE_SYSTEM_PROMPT,
                messages=messages
            )
            response_text = response.content[0].text
            
        elif provider == "openrouter":
            # OpenRouter (OpenAI-compatible)
            openai_messages = [{"role": "system", "content": CLAUDE_SYSTEM_PROMPT}] + messages
            
            response = client.chat.completions.create(
                model=_get_openrouter_model(),
                messages=openai_messages,
                max_tokens=2000,
                temperature=0.7
            )
            response_text = response.choices[0].message.content
        
        # Parse response for structured data
        chart_type = None
        data = None
        insights = []
        
        # Look for chart suggestions in response
        if "bar chart" in response_text.lower() or "bar graph" in response_text.lower():
            chart_type = "bar"
        elif "line chart" in response_text.lower() or "trend" in response_text.lower():
            chart_type = "line"  
        elif "pie chart" in response_text.lower() or "distribution" in response_text.lower():
            chart_type = "pie"
        
        # Extract insights (lines starting with bullet points or numbers)
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if (line.startswith('•') or line.startswith('-') or 
                line.startswith('*') or re.match(r'^\d+\.', line)):
                insights.append(line.lstrip('•-* ').lstrip('0123456789. '))
        
        # If AI suggested a specific visualization, try to provide relevant data
        if chart_type and any(keyword in message.lower() for keyword in ['safety', 'score']):
            data = [{"location": loc["location"], "score": loc["score"], "color": "#10b981" if loc["score"] >= 90 else "#f59e0b" if loc["score"] >= 85 else "#ef4444"} for loc in FLEET_DATA["safety_scores"]]
        elif chart_type and "idle" in message.lower():
            data = [{"location": loc["location"], "minutes": loc["avg_idle_minutes"], "color": "#ef4444" if loc["avg_idle_minutes"] > 120 else "#f59e0b" if loc["avg_idle_minutes"] > 60 else "#10b981"} for loc in FLEET_DATA["idle_analysis"]]
        elif chart_type and "fuel" in message.lower():
            data = [{"day": day["date"][-5:], "efficiency": day["efficiency"]} for day in FLEET_DATA["fuel_efficiency"]]
        
        return ChatResponse(
            response=response_text,
            data=data,
            chart_type=chart_type,
            insights=insights[:3],  # Top 3 insights
            confidence=0.95,
            model=_get_model_name(),
            is_ai_powered=True
        )
        
    except Exception as e:
        print(f"{provider} API error: {e}")
        # Fall back to pattern matching
        return await _process_fallback_query(message)


async def _process_fallback_query(message: str) -> ChatResponse:
    """Fallback to pattern matching when AI is not available."""
    handler_name, confidence = analyze_query(message)
    
    # Route to appropriate handler
    handlers = {
        "safety_analysis": safety_analysis_handler,
        "idle_analysis": idle_analysis_handler,
        "fuel_analysis": fuel_analysis_handler,
        "maintenance_predictions": maintenance_predictions_handler,
        "utilization_analysis": utilization_analysis_handler,
        "cost_optimization": cost_optimization_handler,
        "vehicle_specific": vehicle_specific_handler,
        "general": general_handler
    }
    
    handler = handlers.get(handler_name, general_handler)
    response = handler(message)
    
    # Override confidence and add fallback indicators
    response.confidence = confidence
    response.model = "pattern-matching"
    response.is_ai_powered = False
    
    return response


@router.post("/chat", response_model=ChatResponse)
async def process_chat_query(chat_message: ChatMessage):
    """Process a natural language fleet query with Claude AI or fallback to pattern matching."""
    try:
        _ensure_env_initialized()
        if _is_ai_enabled():
            return await _process_ai_query(
                chat_message.message, 
                chat_message.conversation_history or []
            )
        else:
            return await _process_fallback_query(chat_message.message)
        
    except Exception as e:
        print(f"Error in chat processing: {e}")
        # Ultimate fallback
        return ChatResponse(
            response="I'm experiencing technical difficulties. Please try rephrasing your question or check specific metrics in the dashboard.",
            confidence=0.1,
            model="error-fallback",
            is_ai_powered=False
        )


# Legacy endpoint for backward compatibility
@router.post("/query", response_model=ChatResponse)
async def process_legacy_query(chat_message: ChatMessage):
    """Legacy endpoint - redirects to new chat endpoint."""
    return await process_chat_query(chat_message)


@router.post("/chat/stream")
async def process_chat_stream(chat_message: ChatMessage):
    """Process chat query with streaming response (Server-Sent Events)."""
    
    async def stream_response():
        _ensure_env_initialized()
        if not _is_ai_enabled():
            # For non-AI responses, just yield the complete response
            response = await _process_fallback_query(chat_message.message)
            yield f"data: {json.dumps(response.dict())}\n\n"
            return
        
        client = _get_ai_client()
        provider = _get_provider()
        
        if not client:
            yield f"data: {json.dumps({'error': 'AI service not available'})}\n\n"
            return
        
        try:
            # Fetch fleet context
            fleet_context = await _fetch_fleet_context()
            
            # Build conversation history
            messages = []
            for msg in chat_message.conversation_history[-10:]:
                role = "user" if msg.get("type") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("content", "")})
            
            current_message = f"""CURRENT FLEET DATA:
{fleet_context}

USER QUESTION: {chat_message.message}

Please analyze this question in the context of the current fleet data and provide insights, recommendations, and any relevant visualizations."""

            messages.append({"role": "user", "content": current_message})
            
            accumulated_text = ""
            
            if provider == "anthropic":
                # Stream from Anthropic
                with client.messages.stream(
                    model=_get_anthropic_model(),
                    max_tokens=2000,
                    system=CLAUDE_SYSTEM_PROMPT,
                    messages=messages
                ) as stream:
                    for chunk in stream:
                        if chunk.type == "content_block_delta":
                            if chunk.delta.type == "text_delta":
                                text_chunk = chunk.delta.text
                                accumulated_text += text_chunk
                                yield f"data: {json.dumps({'chunk': text_chunk, 'type': 'text'})}\n\n"
                                
            elif provider == "openrouter":
                # Stream from OpenRouter
                openai_messages = [{"role": "system", "content": CLAUDE_SYSTEM_PROMPT}] + messages
                
                stream = client.chat.completions.create(
                    model=_get_openrouter_model(),
                    messages=openai_messages,
                    max_tokens=2000,
                    temperature=0.7,
                    stream=True
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        text_chunk = chunk.choices[0].delta.content
                        accumulated_text += text_chunk
                        yield f"data: {json.dumps({'chunk': text_chunk, 'type': 'text'})}\n\n"
            
            # After streaming is complete, analyze for charts and insights
            chart_type = None
            data = None
            insights = []
            
            # Analyze accumulated text for visualizations
            if "bar chart" in accumulated_text.lower():
                chart_type = "bar"
            elif "line chart" in accumulated_text.lower():
                chart_type = "line"  
            elif "pie chart" in accumulated_text.lower():
                chart_type = "pie"
            
            # Extract insights
            lines = accumulated_text.split('\n')
            for line in lines:
                line = line.strip()
                if (line.startswith('•') or line.startswith('-') or 
                    line.startswith('*') or re.match(r'^\d+\.', line)):
                    insights.append(line.lstrip('•-* ').lstrip('0123456789. '))
            
            # Provide relevant data for charts
            if chart_type and "safety" in chat_message.message.lower():
                data = [{"location": loc["location"], "score": loc["score"], "color": "#10b981" if loc["score"] >= 90 else "#f59e0b" if loc["score"] >= 85 else "#ef4444"} for loc in FLEET_DATA["safety_scores"]]
            elif chart_type and "idle" in chat_message.message.lower():
                data = [{"location": loc["location"], "minutes": loc["avg_idle_minutes"], "color": "#ef4444" if loc["avg_idle_minutes"] > 120 else "#f59e0b" if loc["avg_idle_minutes"] > 60 else "#10b981"} for loc in FLEET_DATA["idle_analysis"]]
            elif chart_type and "fuel" in chat_message.message.lower():
                data = [{"day": day["date"][-5:], "efficiency": day["efficiency"]} for day in FLEET_DATA["fuel_efficiency"]]
            
            # Send final metadata
            final_data = {
                'type': 'complete',
                'chart_type': chart_type,
                'data': data,
                'insights': insights[:3],
                'model': _get_model_name(),
                'is_ai_powered': True
            }
            yield f"data: {json.dumps(final_data)}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Streaming error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        stream_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.post("/config")
async def set_api_key(request: ApiKeyRequest):
    """Set API key and provider in memory (not persisted to disk)."""
    try:
        success = _set_api_key(request.api_key, request.provider)
        if success:
            provider_name = _get_provider_display_name()
            return {
                "message": f"API key configured successfully for {provider_name}",
                "ai_enabled": True,
                "provider": request.provider
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid API key or failed to connect to {request.provider.title()}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting API key: {str(e)}"
        )


@router.get("/config", response_model=ConfigResponse)
async def get_ai_config():
    """Get current AI configuration status (never returns the API key)."""
    _ensure_env_initialized()
    provider = _get_provider()
    return ConfigResponse(
        ai_enabled=_is_ai_enabled(),
        model=_get_model_name() if _is_ai_enabled() else None,
        provider=provider,
        provider_name=_get_provider_display_name()
    )


@router.get("/insights", response_model=List[FleetInsight])
async def get_ai_insights():
    """Get current AI-generated fleet insights and recommendations."""
    insights = [
        FleetInsight(
            type="efficiency",
            priority="high",
            title="Idle Time Optimization",
            message="Fort Worth location shows 3x higher idle time than fleet average. Driver coaching program could reduce this by 60%.",
            impact="$2,400/month savings",
            action="Schedule Training"
        ),
        FleetInsight(
            type="maintenance",
            priority="medium",
            title="Predictive Maintenance Alert",
            message="Vehicle V023 brake wear patterns indicate service needed in 5-7 days. AI confidence: 92%.",
            impact="Prevent $850 emergency repair",
            action="Schedule Service"
        ),
        FleetInsight(
            type="revenue",
            priority="medium", 
            title="Peak Hour Optimization",
            message="Utilization analysis suggests deploying 3 additional vehicles during 4-6PM peak at OKC location.",
            impact="+$450 daily revenue",
            action="Adjust Fleet Distribution"
        ),
        FleetInsight(
            type="safety",
            priority="low",
            title="Best Practice Sharing",
            message="Fort Worth location drivers show 12% better safety performance. Their techniques could be applied fleet-wide.",
            impact="15% incident reduction",
            action="Analyze Best Practices"
        )
    ]
    
    return insights


@router.get("/analytics/summary")
async def get_analytics_summary():
    """Get comprehensive fleet analytics summary for AI processing."""
    return {
        "fleet_health": {
            "overall_score": 87,
            "safety_trend": "improving",
            "efficiency_trend": "stable",
            "utilization_rate": 74,
            "maintenance_compliance": 92
        },
        "key_metrics": {
            "total_vehicles": 50,
            "active_vehicles": 42,
            "avg_safety_score": 89.6,
            "avg_fuel_efficiency": 8.2,
            "monthly_savings_potential": 6300
        },
        "risk_indicators": [
            {"location": "Fort Worth", "risk": "high", "reason": "excessive_idle_time"},
            {"location": "OKC", "risk": "medium", "reason": "below_avg_safety"},
            {"vehicle": "V023", "risk": "medium", "reason": "maintenance_due"}
        ],
        "optimization_opportunities": [
            {"type": "route", "impact": "high", "savings": 2400},
            {"type": "idle_reduction", "impact": "high", "savings": 1800}, 
            {"type": "maintenance_schedule", "impact": "medium", "savings": 1200}
        ]
    }
