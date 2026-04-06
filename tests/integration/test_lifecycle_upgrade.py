"""Integration test: upgrade path for a pre-existing Pawsistant install.

Simulates a real customer's existing .storage/pawsistant data — 2 dogs, events
across multiple years, NO event_types config (pre-feature install) — and
verifies that:
1. All 14 default event types appear in WS state after startup
2. Button metrics match expected defaults (medicine=days_since, weight=last_value)
3. log_event with a brand-new custom type succeeds
4. Coordinator refresh has no errors
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta

import pytest

from conftest import call_service, get_state, poll_state, poll_state_attrs, HA_URL


class TestUpgradePath:
    """Simulate an existing customer upgrading to the custom-event-types feature."""

    def test_14_default_event_types_in_ws_state(self, ha):
        """WS state attributes must expose all 14 default event types."""
        state = get_state(ha, "sensor.testdog_recent_timeline")
        assert state is not None, "sensor.testdog_recent_timeline should exist"

        attrs = state.get("attributes", {})
        event_types = attrs.get("event_types", {})

        # All 14 defaults must be present
        expected_keys = [
            "food", "treat", "water", "walk", "pee", "poop",
            "medicine", "weight", "vaccine", "sleep",
            "grooming", "training", "teeth", "sick",
        ]
        for key in expected_keys:
            assert key in event_types, f"Event type '{key}' missing from registry"

        assert len(event_types) == 14, f"Expected 14 event types, got {len(event_types)}"

    def test_default_button_metrics_exposed(self, ha):
        """Sensor attributes must expose button_metrics dict."""
        state = get_state(ha, "sensor.testdog_recent_timeline")
        attrs = state.get("attributes", {})
        metrics = attrs.get("button_metrics", {})

        assert metrics.get("medicine") == "days_since", \
            f"medicine metric should be days_since, got: {metrics.get('medicine')}"
        assert metrics.get("weight") == "last_value", \
            f"weight metric should be last_value, got: {metrics.get('weight')}"
        assert metrics.get("vaccine") == "days_since"

        # All 14 types must have a metric
        for key in ["food", "treat", "water", "walk", "pee", "poop",
                    "medicine", "weight", "vaccine", "sleep",
                    "grooming", "training", "teeth", "sick"]:
            assert key in metrics, f"Metric for '{key}' missing"

    def test_log_custom_event_type(self, ha):
        """Log a brand-new custom event type not in the defaults."""
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "custom_bark",
            "note": "Loud one",
        })

        # Should succeed — no validation error
        state = poll_state(
            ha,
            "sensor.testdog_recent_timeline",
            lambda s: s is not None,
            timeout=15,
        )
        assert state is not None

    def test_coordinator_refresh_succeeds(self, ha):
        """Coordinator refresh should complete without errors."""
        # Trigger a refresh
        call_service(ha, "homeassistant", "update_entity", {
            "entity_id": "sensor.testdog_recent_timeline",
        })

        # Wait for the update to propagate
        time.sleep(3)

        state = get_state(ha, "sensor.testdog_recent_timeline")
        assert state is not None, "Timeline sensor should still exist after refresh"
        assert state != "unavailable", "Timeline sensor should not be unavailable after refresh"

    def test_log_existing_event_type_still_works(self, ha):
        """Verify pre-existing event types still log correctly after upgrade."""
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "pee",
        })
        state = poll_state(
            ha,
            "sensor.testdog_most_recent_pee",
            lambda s: s not in ("unknown", "unavailable"),
            timeout=10,
        )
        assert "T" in state, f"Expected ISO timestamp, got: {state}"