"""
services/cost_tracker.py - API cost tracking and logging for LLM providers

Tracks token usage, latency, provider, model, and estimated cost for each
LLM request to enable cost monitoring and optimization.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Estimated cost per 1M tokens (input/output) in USD
# These are approximate and should be updated based on actual provider pricing
MODEL_PRICING = {
    "mistral-small-latest": {"input": 0.25, "output": 0.25},
    "mistral-large-latest": {"input": 2.0, "output": 6.0},
    "mistral-medium-latest": {"input": 1.0, "output": 3.0},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.10},
    "llama-3.1-70b-instant": {"input": 0.59, "output": 0.79},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
}

# Cost tracking storage (in-memory; in production, use a database)
_cost_history: list = []


def estimate_token_count(text: str) -> int:
    """
    Estimate token count for a text string.
    Rough approximation: 1 token ≈ 0.75 words or 4 characters.
    """
    if not text:
        return 0
    # Rough estimate: 4 characters per token
    return max(1, len(text) // 4)


def record_api_call(
    provider: str,
    model: str,
    input_text: str,
    output_text: str,
    latency_ms: float,
    success: bool = True,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Record an API call with cost estimation.

    Args:
        provider: LLM provider name (mistral, groq, gemini)
        model: Model name
        input_text: Input text sent to the model
        output_text: Output text received from the model
        latency_ms: Request latency in milliseconds
        success: Whether the call succeeded
        error: Error message if failed

    Returns:
        Cost record dictionary
    """
    input_tokens = estimate_token_count(input_text)
    output_tokens = estimate_token_count(output_text)

    pricing = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6),
        "latency_ms": latency_ms,
        "success": success,
        "error": error,
    }

    _cost_history.append(record)

    # Keep only last 1000 records to prevent memory growth
    if len(_cost_history) > 1000:
        _cost_history.pop(0)

    logger.info(
        f"API call: {provider}/{model} - "
        f"tokens: {input_tokens}+{output_tokens} - "
        f"cost: ${total_cost:.6f} - "
        f"latency: {latency_ms:.0f}ms - "
        f"success: {success}"
    )

    return record


def get_cost_summary() -> Dict[str, Any]:
    """Get cost summary across all providers."""
    if not _cost_history:
        return {"total_calls": 0, "total_cost_usd": 0.0, "providers": {}}

    total_cost = sum(r["total_cost_usd"] for r in _cost_history)
    total_calls = len(_cost_history)
    successful_calls = sum(1 for r in _cost_history if r["success"])

    providers = {}
    for r in _cost_history:
        provider = r["provider"]
        if provider not in providers:
            providers[provider] = {
                "calls": 0,
                "total_cost_usd": 0.0,
                "models": {},
            }
        providers[provider]["calls"] += 1
        providers[provider]["total_cost_usd"] += r["total_cost_usd"]

        model = r["model"]
        if model not in providers[provider]["models"]:
            providers[provider]["models"][model] = {
                "calls": 0,
                "total_cost_usd": 0.0,
            }
        providers[provider]["models"][model]["calls"] += 1
        providers[provider]["models"][model]["total_cost_usd"] += r[
            "total_cost_usd"
        ]

    return {
        "total_calls": total_calls,
        "successful_calls": successful_calls,
        "failed_calls": total_calls - successful_calls,
        "total_cost_usd": round(total_cost, 6),
        "providers": providers,
    }


def get_recent_calls(limit: int = 50) -> list:
    """Get recent API call records."""
    return _cost_history[-limit:]


def clear_cost_history() -> None:
    """Clear cost tracking history."""
    _cost_history.clear()