"""Fixtures and helpers for Pawsistant Docker integration tests.

Auth is bootstrapped via HA's onboarding API (no pre-seeded auth files needed).
The onboarding endpoint works without authentication when onboarding hasn't
been completed yet.
"""

import time

import pytest
import requests

HA_URL = "http://localhost:8123"
HA_STARTUP_TIMEOUT = 120  # seconds


def _wait_for_ha():
    """Block until HA responds to requests (no auth needed for this check)."""
    deadline = time.monotonic() + HA_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{HA_URL}/api/", timeout=5)
            # 401 means HA is up but needs auth — that's fine
            if r.status_code in (200, 401):
                return
        except requests.ConnectionError:
            pass
        time.sleep(2)
    raise TimeoutError(f"Home Assistant did not start within {HA_STARTUP_TIMEOUT}s")


def _complete_onboarding():
    """Complete HA onboarding and return a long-lived access token.

    Steps:
      1. Create owner user via /api/onboarding/users
      2. Exchange the returned auth_code for an access token
      3. Complete remaining onboarding steps (core config, analytics)
    """
    # Step 1: Create the owner user
    r = requests.post(
        f"{HA_URL}/api/onboarding/users",
        json={
            "client_id": f"{HA_URL}/",
            "name": "Test",
            "username": "test",
            "password": "testtest1",
            "language": "en",
        },
        timeout=10,
    )
    if r.status_code == 200:
        auth_code = r.json()["auth_code"]
    elif r.status_code == 403:
        # Onboarding already completed (container restarted) — log in instead
        return _login("test", "testtest1")
    else:
        raise RuntimeError(f"Failed to create onboarding user: {r.status_code} {r.text}")

    # Step 2: Exchange auth_code for tokens
    r = requests.post(
        f"{HA_URL}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": f"{HA_URL}/",
        },
        timeout=10,
    )
    r.raise_for_status()
    token_data = r.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")

    headers = {"Authorization": f"Bearer {access_token}"}

    # Step 3: Complete remaining onboarding steps
    requests.post(
        f"{HA_URL}/api/onboarding/core_config",
        headers=headers,
        json={},
        timeout=10,
    )
    requests.post(
        f"{HA_URL}/api/onboarding/analytics",
        headers=headers,
        json={},
        timeout=10,
    )
    requests.post(
        f"{HA_URL}/api/onboarding/integration",
        headers=headers,
        json={"client_id": f"{HA_URL}/", "redirect_uri": f"{HA_URL}/?auth_callback=1"},
        timeout=10,
    )

    # Step 4: Create a long-lived access token via the websocket API (or reuse short-lived)
    # The short-lived token works fine for tests, but let's create a long-lived one
    # by calling the auth/long_lived_access_token API.
    # Actually, the short-lived token is valid for 30 minutes — plenty for tests.

    return access_token


def _login(username, password):
    """Log in with existing credentials and return an access token."""
    # Start an auth flow
    r = requests.post(
        f"{HA_URL}/auth/login_flow",
        json={
            "client_id": f"{HA_URL}/",
            "handler": ["homeassistant", None],
            "redirect_uri": f"{HA_URL}/?auth_callback=1",
        },
        timeout=10,
    )
    r.raise_for_status()
    flow_id = r.json()["flow_id"]

    # Submit credentials
    r = requests.post(
        f"{HA_URL}/auth/login_flow/{flow_id}",
        json={"username": username, "password": password, "client_id": f"{HA_URL}/"},
        timeout=10,
    )
    r.raise_for_status()
    result = r.json()

    # Exchange auth code for tokens
    r = requests.post(
        f"{HA_URL}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": result["result"],
            "client_id": f"{HA_URL}/",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ha_token():
    """Wait for HA to start, complete onboarding, and return an access token."""
    _wait_for_ha()
    return _complete_onboarding()


@pytest.fixture(scope="session")
def ha(ha_token):
    """Return a requests.Session pre-configured with HA auth headers."""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    })
    session.base_url = HA_URL

    # Wait for pawsistant entities to appear (integration needs to load)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            r = session.get(f"{HA_URL}/api/states")
            if r.status_code == 200:
                states = r.json()
                entity_ids = [s["entity_id"] for s in states]
                if any("testdog" in eid for eid in entity_ids):
                    break
        except Exception:
            pass
        time.sleep(2)

    return session


# ---------------------------------------------------------------------------
# Helper functions (used by tests)
# ---------------------------------------------------------------------------


def get_state(ha, entity_id):
    """Get the state object for an entity. Returns None if not found."""
    r = ha.get(f"{HA_URL}/api/states/{entity_id}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def call_service(ha, domain, service, data=None, return_response=False):
    """Call a HA service and return the response."""
    r = ha.post(
        f"{HA_URL}/api/services/{domain}/{service}",
        json=data or {},
    )
    r.raise_for_status()
    result = r.json()

    if return_response and isinstance(result, dict):
        return result
    return result


def poll_state(ha, entity_id, condition, timeout=15):
    """Poll a sensor's state until condition(state_value) is True.

    Returns the state value when condition is met.
    Raises TimeoutError if timeout expires.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state_obj = get_state(ha, entity_id)
        if state_obj is not None:
            value = state_obj["state"]
            try:
                if condition(value):
                    return value
            except (ValueError, TypeError):
                pass
        time.sleep(1)
    # One last attempt for a clear error
    state_obj = get_state(ha, entity_id)
    state_val = state_obj["state"] if state_obj else "<entity not found>"
    raise TimeoutError(
        f"Timed out waiting for {entity_id} to satisfy condition. "
        f"Last state: {state_val}"
    )


def poll_state_attrs(ha, entity_id, condition, timeout=15):
    """Poll a sensor's attributes until condition(attributes) is True.

    Returns the attributes dict when condition is met.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state_obj = get_state(ha, entity_id)
        if state_obj is not None:
            attrs = state_obj.get("attributes", {})
            try:
                if condition(attrs):
                    return attrs
            except (ValueError, TypeError):
                pass
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {entity_id} attributes to satisfy condition")
