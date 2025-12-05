from __future__ import annotations


def build_vehicle_diagnostics_prompt(*, vehicle_context: str, user_query: str) -> str:
    """Template for vehicle diagnostics prompts."""
    return (
        "You are an AI assistant helping a professional vehicle technician diagnose issues.\n"
        "Use clear, structured reasoning and avoid guessing when data is insufficient.\n\n"
        "Vehicle context:\n"
        f"{vehicle_context.strip() or 'N/A'}\n\n"
        "Technician question / issue description:\n"
        f"{user_query.strip()}\n\n"
        "Respond with:\n"
        "1) Probable causes ranked by likelihood.\n"
        "2) Step-by-step diagnostic steps (with tools, tests, and expected readings).\n"
        "3) Safety considerations.\n"
        "4) Repair recommendations and parts to inspect or replace.\n"
    )


