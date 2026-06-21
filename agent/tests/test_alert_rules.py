from app.alert_rules import HAZARD_ALERT_RULES


def test_hazard_alert_rules_covers_all_five_types():
    alert_types = {rule["alert_type"] for rule in HAZARD_ALERT_RULES}
    assert alert_types == {"ppe", "zone_intrusion", "forklift_proximity", "fall", "spill"}


def test_every_rule_has_prompt_and_system_prompt():
    for rule in HAZARD_ALERT_RULES:
        assert rule["prompt"]
        assert rule["system_prompt"]
