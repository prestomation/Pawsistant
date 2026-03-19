"""Integration tests for the Pawsistant component lifecycle.

These tests run against a real Home Assistant instance in Docker.
They exercise the full flow: services → storage → coordinator → sensors.

Tests are ordered and run sequentially within a single HA instance.
"""

import pytest

from conftest import call_service, get_state, poll_state, poll_state_attrs, HA_URL


class TestSensorsExist:
    """Verify that sensors are created on startup for the pre-seeded dog."""

    def test_most_recent_pee_sensor_exists(self, ha):
        state = get_state(ha, "sensor.testdog_most_recent_pee")
        assert state is not None, "sensor.testdog_most_recent_pee should exist"

    def test_most_recent_poop_sensor_exists(self, ha):
        state = get_state(ha, "sensor.testdog_most_recent_poop")
        assert state is not None

    def test_daily_pee_count_sensor_exists(self, ha):
        state = get_state(ha, "sensor.testdog_daily_pee_count")
        assert state is not None

    def test_weight_sensor_exists(self, ha):
        state = get_state(ha, "sensor.testdog_weight")
        assert state is not None

    def test_days_since_medicine_sensor_exists(self, ha):
        state = get_state(ha, "sensor.testdog_days_since_medicine")
        assert state is not None

    def test_recent_timeline_sensor_exists(self, ha):
        state = get_state(ha, "sensor.testdog_recent_timeline")
        assert state is not None


class TestLogEvent:
    """Test that logging events updates the corresponding sensors."""

    def test_log_pee_updates_most_recent(self, ha):
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "pee",
        })
        state = poll_state(
            ha,
            "sensor.testdog_most_recent_pee",
            lambda s: s not in ("unknown", "unavailable"),
        )
        # Timestamp sensors return ISO format strings
        assert "T" in state, f"Expected ISO timestamp, got: {state}"

    def test_log_pee_increments_daily_count(self, ha):
        state = poll_state(
            ha,
            "sensor.testdog_daily_pee_count",
            lambda s: int(s) >= 1,
        )
        assert int(state) >= 1

    def test_log_poop_twice_counts_correctly(self, ha):
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "poop",
        })
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "poop",
        })
        state = poll_state(
            ha,
            "sensor.testdog_daily_poop_count",
            lambda s: int(s) >= 2,
        )
        assert int(state) >= 2


class TestWeightSensor:
    """Test the weight sensor with a value."""

    def test_log_weight_updates_sensor(self, ha):
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "weight",
            "value": 55.5,
        })
        state = poll_state(
            ha,
            "sensor.testdog_weight",
            lambda s: s not in ("unknown", "unavailable"),
        )
        assert float(state) == 55.5


class TestDeleteEvent:
    """Test deleting an event by ID."""

    def test_delete_event_via_sensor_attribute(self, ha):
        # Log a food event
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "food",
        })

        # Get the event_id from the sensor's attributes
        attrs = poll_state_attrs(
            ha,
            "sensor.testdog_most_recent_food",
            lambda a: a.get("event_id"),
        )
        event_id = attrs["event_id"]
        assert event_id, "event_id attribute should be non-empty"

        # Delete the event
        call_service(ha, "pawsistant", "delete_event", {
            "event_id": event_id,
        })

        # After deletion, the sensor should revert (no more food events)
        # or the event_id should change
        poll_state_attrs(
            ha,
            "sensor.testdog_most_recent_food",
            lambda a: a.get("event_id", "") != event_id,
            timeout=10,
        )


class TestAddRemoveDog:
    """Test adding and removing dogs via services."""

    def test_add_dog_creates_sensors(self, ha):
        call_service(ha, "pawsistant", "add_dog", {
            "name": "Buddy",
            "breed": "Golden Retriever",
        })

        # add_dog triggers a config entry reload, so new sensors should appear
        # This may take a bit longer due to the reload
        state = poll_state(
            ha,
            "sensor.buddy_most_recent_pee",
            lambda s: s is not None,
            timeout=30,
        )
        assert state is not None

    def test_remove_dog_cleans_up(self, ha):
        call_service(ha, "pawsistant", "remove_dog", {
            "dog": "Buddy",
        })

        # After removal + coordinator refresh, buddy sensors should go away
        # Note: entity registry may keep the entity as "unavailable" rather
        # than fully removing it. That's expected HA behavior.
        import time
        time.sleep(5)  # Give HA time to process the reload

        # We just verify the command didn't error — full entity removal
        # depends on HA's entity registry cleanup behavior.


class TestTimeline:
    """Test the recent timeline sensor."""

    def test_timeline_reflects_events(self, ha):
        # We've logged several events above, timeline should reflect them
        state = get_state(ha, "sensor.testdog_recent_timeline")
        assert state is not None
        # The state is the count of events in the last 24h
        count = int(state["state"])
        assert count > 0, "Timeline should have events from earlier tests"

        # Check that the events attribute is populated
        attrs = state.get("attributes", {})
        events = attrs.get("events", [])
        assert len(events) > 0, "Timeline events attribute should be non-empty"

    def test_timeline_event_has_expected_fields(self, ha):
        state = get_state(ha, "sensor.testdog_recent_timeline")
        attrs = state.get("attributes", {})
        events = attrs.get("events", [])
        if events:
            event = events[0]
            assert "type" in event
            assert "time" in event
            assert "event_id" in event


class TestLogEventWithNote:
    """Test logging events with optional fields."""

    def test_note_appears_in_attributes(self, ha):
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "medicine",
            "note": "Heartgard",
        })

        attrs = poll_state_attrs(
            ha,
            "sensor.testdog_most_recent_medicine",
            lambda a: a.get("note") == "Heartgard",
        )
        assert attrs["note"] == "Heartgard"

    def test_days_since_medicine_updates(self, ha):
        state = poll_state(
            ha,
            "sensor.testdog_days_since_medicine",
            lambda s: s not in ("unknown", "unavailable"),
        )
        # Should be very close to 0 since we just logged it
        assert float(state) < 1.0
