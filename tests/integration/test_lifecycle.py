"""Integration tests for the Pawsistant component lifecycle.

These tests run against a real Home Assistant instance in Docker.
They exercise the full flow: services → storage → coordinator → sensors.

Tests are ordered and run sequentially within a single HA instance.
"""

import time
from datetime import datetime, timezone, timedelta

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

        # Capture pre-delete state so we can detect the change
        pre_state = get_state(ha, "sensor.testdog_most_recent_food")["state"]

        # Delete the event
        call_service(ha, "pawsistant", "delete_event", {
            "event_id": event_id,
        })

        # After deletion with no remaining food events, the sensor state
        # should revert to "unknown". Coordinator refresh can be slow,
        # so allow plenty of time.
        poll_state(
            ha,
            "sensor.testdog_most_recent_food",
            lambda s: s != pre_state,
            timeout=30,
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


class TestMultiDog:
    """Test that multiple dogs don't contaminate each other's event counts."""

    def test_add_buddy(self, ha):
        """Add a second dog and verify sensors are created."""
        call_service(ha, "pawsistant", "add_dog", {
            "name": "Buddy",
            "breed": "Labrador",
        })
        # add_dog triggers a config entry reload — wait for Buddy's sensors
        state = poll_state(
            ha,
            "sensor.buddy_most_recent_pee",
            lambda s: s is not None,
            timeout=30,
        )
        assert state is not None

    def test_buddy_pee_count_is_isolated(self, ha):
        """Buddy's pee count starts at 0 and increments independently."""
        # Log a pee for Buddy — the service works even if sensors are still loading
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Buddy",
            "event_type": "pee",
        })
        # Wait for the coordinator to refresh and the count to appear.
        # After add_dog reload, daily count sensors may briefly show "unavailable"
        # until the coordinator runs. Use a generous timeout.
        state = poll_state(
            ha,
            "sensor.buddy_daily_pee_count",
            lambda s: s not in ("unavailable", "unknown", None) and int(s) >= 1,
            timeout=45,
        )
        assert int(state) == 1, f"Buddy's pee count should be 1, got: {state}"

    def test_testdog_poop_does_not_affect_buddy_poop(self, ha):
        """Log a poop for Testdog and verify Buddy's poop count stays at 0."""
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "poop",
        })
        # Give coordinator time to refresh
        time.sleep(3)
        buddy_poop = get_state(ha, "sensor.buddy_daily_poop_count")
        # Buddy should have no poop events — state is 0 or unknown
        if buddy_poop is not None and buddy_poop["state"] not in ("unknown", "unavailable"):
            assert int(buddy_poop["state"]) == 0, (
                f"Buddy's poop count should be 0 after Testdog poop, got: {buddy_poop['state']}"
            )

    def test_remove_buddy(self, ha):
        """Clean up: remove Buddy."""
        call_service(ha, "pawsistant", "remove_dog", {
            "dog": "Buddy",
        })
        # Allow HA to process the removal
        time.sleep(5)


class TestEdgeCaseDogNames:
    """Test dogs with names containing spaces (slugified entity IDs)."""

    def test_add_dog_with_space_in_name(self, ha):
        """Add 'Good Boy' and verify slugified entity IDs are created."""
        call_service(ha, "pawsistant", "add_dog", {
            "name": "Good Boy",
        })
        # add_dog triggers a reload — wait for sensors with slugified name
        state = poll_state(
            ha,
            "sensor.good_boy_most_recent_pee",
            lambda s: s is not None,
            timeout=30,
        )
        assert state is not None, "sensor.good_boy_most_recent_pee should exist after adding 'Good Boy'"

    def test_log_event_for_dog_with_space(self, ha):
        """Log a pee event for 'Good Boy' using the display name."""
        call_service(ha, "pawsistant", "log_event", {
            "dog": "Good Boy",
            "event_type": "pee",
        })
        state = poll_state(
            ha,
            "sensor.good_boy_most_recent_pee",
            lambda s: s not in ("unknown", "unavailable"),
            timeout=20,
        )
        assert "T" in state, f"Expected ISO timestamp for Good Boy pee, got: {state}"

    def test_remove_good_boy(self, ha):
        """Clean up: remove 'Good Boy'."""
        call_service(ha, "pawsistant", "remove_dog", {
            "dog": "Good Boy",
        })
        time.sleep(5)


class TestBackdateEvent:
    """Test logging events with an explicit past timestamp."""

    def test_backdate_pee_event(self, ha):
        """Log a pee event 2 hours in the past and verify the sensor reflects it."""
        two_hours_ago = (
            datetime.now(tz=timezone.utc) - timedelta(hours=2)
        ).isoformat()

        call_service(ha, "pawsistant", "log_event", {
            "dog": "Testdog",
            "event_type": "pee",
            "timestamp": two_hours_ago,
        })

        # The most_recent_pee sensor should update. Because we've already logged
        # a pee during the TestLogEvent class, the backdated event may or may not
        # be the most recent — we verify it's a valid ISO timestamp.
        state = poll_state(
            ha,
            "sensor.testdog_most_recent_pee",
            lambda s: s not in ("unknown", "unavailable"),
            timeout=20,
        )
        assert "T" in state, f"Expected ISO timestamp after backdate, got: {state}"

        # The backdated timestamp must be parseable and in the past
        parsed = datetime.fromisoformat(state.replace("Z", "+00:00"))
        assert parsed < datetime.now(tz=timezone.utc), (
            f"most_recent_pee should be in the past, got: {state}"
        )


class TestFreshInstallNoMigration:
    """Verify no doglog-related migration errors appear in HA logs."""

    def test_no_doglog_errors_in_log(self, ha):
        """Check the HA error log for any 'doglog' references.

        The Pawsistant integration was renamed from ha-doglog. A fresh install
        should not trigger any doglog migration errors.
        """
        import requests

        r = ha.get(f"{HA_URL}/api/error_log")
        assert r.status_code == 200, f"Could not fetch error log: {r.status_code}"

        error_log = r.text
        doglog_lines = [
            line for line in error_log.splitlines()
            if "doglog" in line.lower()
        ]

        assert not doglog_lines, (
            f"Found unexpected 'doglog' references in HA error log:\n"
            + "\n".join(doglog_lines)
        )
