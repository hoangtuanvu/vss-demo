SYSTEM_PROMPT = (
    "You are a warehouse safety monitoring system watching a live video feed. "
    "Analyze each frame for the specific hazard described and alert only when "
    "it is clearly present."
)

HAZARD_ALERT_RULES: list[dict] = [
    {
        "alert_type": "ppe",
        "prompt": "Alert if a person is visible without a hard hat or hi-vis vest in a designated PPE-required zone.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "zone_intrusion",
        "prompt": "Alert if a person enters a marked restricted or no-go zone.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "forklift_proximity",
        "prompt": "Alert if a forklift and a pedestrian are within close proximity (less than approximately 2 meters) of each other.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "fall",
        "prompt": "Alert if a person is on the ground and not moving for more than a few seconds.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "spill",
        "prompt": "Alert if there is a liquid spill, dropped pallet, or other obstruction blocking a walkway.",
        "system_prompt": SYSTEM_PROMPT,
    },
]
