#!/usr/bin/env python3
"""Run ESPHome sub-device availability through a real Home Assistant server."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HA_IMAGE = "ghcr.io/home-assistant/home-assistant:stable"
HA_CONTAINER_COMPONENT_PATH = "/usr/src/homeassistant/homeassistant/components/esphome"
HA_CONTAINER_AIO_PATH = "/availability-e2e/aioesphomeapi"
HTTP_TIMEOUT = 60
STARTUP_TIMEOUT = 240
STATE_TIMEOUT = 90

CHILD_TARGET = "switch.child_module_child_target"
CHILD_UNAVAILABLE_BUTTON = "button.availability_e2e_make_child_unavailable"
CHILD_AVAILABLE_BUTTON = "button.availability_e2e_make_child_available"


def log(message: str) -> None:
    """Print one harness status line."""
    print(f"[availability-e2e] {message}", flush=True)


def reserve_port() -> int:
    """Ask the kernel for an unused local TCP port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, process: subprocess.Popen[bytes], name: str) -> None:
    """Wait until a process accepts TCP connections."""
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited with status {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for {name} on port {port}")


class HomeAssistantClient:
    """Small HTTP client for onboarding and state verification."""

    def __init__(self, port: int) -> None:
        self.base_url = f"http://127.0.0.1:{port}"
        self.token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        authenticated: bool = False,
    ) -> Any:
        """Make one JSON request and return the decoded response."""
        headers = {"Accept": "application/json"}
        body: bytes | None = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        elif form is not None:
            body = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if authenticated:
            if self.token is None:
                raise RuntimeError("Authenticated request attempted before onboarding")
            headers["Authorization"] = f"Bearer {self.token}"

        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:
                response_body = response.read()
        except HTTPError as err:
            detail = err.read().decode(errors="replace")
            raise RuntimeError(
                f"Home Assistant {method} {path} returned {err.code}: {detail}"
            ) from err
        if not response_body:
            return None
        return json.loads(response_body)

    def wait_until_ready(self, process: subprocess.Popen[bytes]) -> None:
        """Wait for the onboarding endpoint to become responsive."""
        deadline = time.monotonic() + STARTUP_TIMEOUT
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"Home Assistant exited with status {process.returncode}"
                )
            try:
                self.request("GET", "/api/onboarding")
                return
            except (RuntimeError, URLError) as err:
                last_error = err
                time.sleep(1)
        raise TimeoutError("Timed out waiting for Home Assistant") from last_error

    def onboard(self) -> None:
        """Create the single ephemeral owner and finish onboarding."""
        client_id = f"{self.base_url}/"
        user_result = self.request(
            "POST",
            "/api/onboarding/users",
            data={
                "name": "Availability E2E",
                "username": "availability-e2e",
                "password": "availability-e2e",
                "client_id": client_id,
                "language": "en",
            },
        )
        token_result = self.request(
            "POST",
            "/auth/token",
            form={
                "grant_type": "authorization_code",
                "code": user_result["auth_code"],
                "client_id": client_id,
            },
        )
        self.token = token_result["access_token"]
        self.request("POST", "/api/onboarding/core_config", data={}, authenticated=True)
        self.request(
            "POST",
            "/api/onboarding/integration",
            data={"client_id": client_id, "redirect_uri": client_id},
            authenticated=True,
        )
        self.request("POST", "/api/onboarding/analytics", data={}, authenticated=True)

    def add_esphome(self, api_port: int) -> None:
        """Configure the real ESPHome integration through its config flow."""
        result = self.request(
            "POST",
            "/api/config/config_entries/flow",
            data={"handler": "esphome"},
            authenticated=True,
        )
        if result.get("type") != "form" or not (flow_id := result.get("flow_id")):
            raise RuntimeError(f"Unexpected ESPHome config-flow result: {result}")
        result = self.request(
            "POST",
            f"/api/config/config_entries/flow/{flow_id}",
            data={"host": "127.0.0.1", "port": api_port},
            authenticated=True,
        )
        if result.get("type") != "create_entry":
            raise RuntimeError(f"ESPHome config flow did not create an entry: {result}")

    def state(self, entity_id: str) -> dict[str, Any]:
        """Get one Home Assistant state."""
        result = self.request("GET", f"/api/states/{entity_id}", authenticated=True)
        if not isinstance(result, dict):
            raise RuntimeError(f"Invalid state response for {entity_id}: {result}")
        return result

    def wait_for_state(
        self, entity_id: str, predicate: Callable[[str], bool], description: str
    ) -> str:
        """Wait for an entity state to satisfy a predicate."""
        deadline = time.monotonic() + STATE_TIMEOUT
        last_state: str | None = None
        while time.monotonic() < deadline:
            try:
                last_state = str(self.state(entity_id)["state"])
            except RuntimeError:
                time.sleep(0.5)
                continue
            if predicate(last_state):
                return last_state
            time.sleep(0.5)
        raise TimeoutError(
            f"Timed out waiting for {entity_id} to be {description}; "
            f"last state was {last_state!r}"
        )

    def press(self, entity_id: str) -> None:
        """Press an ESPHome button through Home Assistant."""
        self.request(
            "POST",
            "/api/services/button/press",
            data={"entity_id": entity_id},
            authenticated=True,
        )


def write_home_assistant_config(config_dir: Path, ha_port: int) -> None:
    """Write an isolated HA config and a focused dashboard."""
    (config_dir / "configuration.yaml").write_text(
        f"""\
default_config:

homeassistant:
  auth_providers:
    - type: trusted_networks
      trusted_networks:
        - 127.0.0.1
        - ::1
      allow_bypass_login: true
    - type: homeassistant

http:
  server_host: 127.0.0.1
  server_port: {ha_port}

lovelace:
  mode: yaml
"""
    )
    (config_dir / "ui-lovelace.yaml").write_text(
        f"""\
title: ESPHome availability E2E
views:
  - title: Availability
    path: availability
    cards:
      - type: markdown
        content: >-
          This dashboard is served by the isolated ESPHome availability test.
      - type: entities
        title: Availability targets
        entities:
          - entity: {CHILD_TARGET}
            name: Child device target
      - type: entities
        title: Controls
        entities:
          - entity: {CHILD_UNAVAILABLE_BUTTON}
          - entity: {CHILD_AVAILABLE_BUTTON}
"""
    )


def compile_firmware(repo_root: Path, config_path: Path, api_port: int) -> Path:
    """Compile the host fixture and return its executable."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(repo_root), env.get("PYTHONPATH")) if part is not None
    )
    command = [
        sys.executable,
        "-m",
        "esphome",
        "-s",
        "api_port",
        str(api_port),
        "compile",
        str(config_path),
    ]
    log("Compiling the ESPHome host fixture")
    subprocess.run(command, cwd=repo_root, env=env, check=True)
    build_dir = config_path.parent / ".esphome" / "build" / "availability-e2e"
    candidates = list(build_dir.glob(".pioenvs/*/program"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one host executable under {build_dir}, found {candidates}"
        )
    return candidates[0]


def start_firmware(binary: Path, log_file: Any) -> subprocess.Popen[bytes]:
    """Start the compiled host fixture."""
    return subprocess.Popen(
        [str(binary)],
        cwd=binary.parent,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def start_home_assistant(
    *,
    podman: str,
    image: str,
    container_name: str,
    config_dir: Path,
    aio_checkout: Path,
    ha_checkout: Path,
    log_file: Any,
) -> subprocess.Popen[bytes]:
    """Start HA with the two local companion implementations mounted."""
    component_path = ha_checkout / "homeassistant" / "components" / "esphome"
    command = [
        podman,
        "run",
        "--rm",
        "--pull=missing",
        "--name",
        container_name,
        "--network=host",
        "--env",
        f"PYTHONPATH={HA_CONTAINER_AIO_PATH}",
        "--volume",
        f"{config_dir}:/config:rw",
        "--volume",
        f"{aio_checkout}:{HA_CONTAINER_AIO_PATH}:ro",
        "--volume",
        f"{component_path}:{HA_CONTAINER_COMPONENT_PATH}:ro",
        image,
    ]
    return subprocess.Popen(
        command,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    """Stop one process without masking the test result."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def tail(path: Path, lines: int = 80) -> str:
    """Return the tail of a text log."""
    try:
        return "\n".join(
            path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        )
    except OSError:
        return "<log unavailable>"


def validate_checkout(path: Path, marker: Path, label: str) -> Path:
    """Resolve a checkout path and validate one expected file."""
    resolved = path.expanduser().resolve()
    if not (resolved / marker).is_file():
        raise ValueError(f"{label} checkout does not contain {marker}: {resolved}")
    return resolved


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aio-checkout",
        type=Path,
        required=True,
        help="aioesphomeapi checkout containing the companion protocol patch",
    )
    parser.add_argument(
        "--ha-core-checkout",
        type=Path,
        required=True,
        help="Home Assistant Core checkout containing the companion integration patch",
    )
    parser.add_argument("--ha-image", default=HA_IMAGE)
    parser.add_argument("--podman", default="podman")
    parser.add_argument(
        "--interactive",
        "--keep-running",
        action="store_true",
        help="Pause with the live dashboard openable after each state transition",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    """Compile and exercise sub-device availability."""
    repo_root = Path(__file__).resolve().parents[3]
    fixture_path = Path(__file__).with_name("device.yaml")
    aio_checkout = validate_checkout(
        args.aio_checkout, Path("aioesphomeapi/api.proto"), "aioesphomeapi"
    )
    ha_checkout = validate_checkout(
        args.ha_core_checkout,
        Path("homeassistant/components/esphome/manifest.json"),
        "Home Assistant Core",
    )
    podman = shutil.which(args.podman)
    if podman is None:
        raise RuntimeError(f"Could not find container runtime {args.podman!r}")

    api_port = reserve_port()
    ha_port = reserve_port()
    container_name = f"esphome-availability-e2e-{os.getpid()}"
    firmware: subprocess.Popen[bytes] | None = None
    home_assistant: subprocess.Popen[bytes] | None = None

    with tempfile.TemporaryDirectory(prefix="esphome-availability-e2e-") as tmp:
        temp_dir = Path(tmp)
        config_path = temp_dir / "device.yaml"
        config_path.write_text(fixture_path.read_text())
        ha_config = temp_dir / "home-assistant"
        ha_config.mkdir()
        write_home_assistant_config(ha_config, ha_port)
        firmware_log = temp_dir / "firmware.log"
        ha_log = temp_dir / "home-assistant.log"

        try:
            binary = compile_firmware(repo_root, config_path, api_port)
            with ExitStack() as stack:
                firmware_log_file = stack.enter_context(firmware_log.open("wb"))
                ha_log_file = stack.enter_context(ha_log.open("wb"))
                firmware = start_firmware(binary, firmware_log_file)
                wait_for_port(api_port, firmware, "ESPHome host fixture")
                log(f"ESPHome API is listening on 127.0.0.1:{api_port}")

                home_assistant = start_home_assistant(
                    podman=podman,
                    image=args.ha_image,
                    container_name=container_name,
                    config_dir=ha_config,
                    aio_checkout=aio_checkout,
                    ha_checkout=ha_checkout,
                    log_file=ha_log_file,
                )
                client = HomeAssistantClient(ha_port)
                client.wait_until_ready(home_assistant)
                log("Home Assistant is ready; completing onboarding")
                client.onboard()
                client.add_esphome(api_port)

                initial_child = client.wait_for_state(
                    CHILD_TARGET, lambda state: state != "unavailable", "available"
                )
                log(
                    "ESPHome entity loaded in Home Assistant "
                    f"({CHILD_TARGET}={initial_child})"
                )
                log(
                    "Control buttons: "
                    f"{CHILD_UNAVAILABLE_BUTTON}, {CHILD_AVAILABLE_BUTTON}"
                )

                client.press(CHILD_UNAVAILABLE_BUTTON)
                client.wait_for_state(
                    CHILD_TARGET, lambda state: state == "unavailable", "unavailable"
                )
                log("PASS: sub-device target is unavailable")
                log(f"Dashboard: {client.base_url}/lovelace/availability")
                if args.interactive:
                    input(
                        "Inspect the unavailable state, then press Enter to recover: "
                    )

                client.press(CHILD_AVAILABLE_BUTTON)
                client.wait_for_state(
                    CHILD_TARGET,
                    lambda state: state == initial_child,
                    repr(initial_child),
                )
                log("PASS: sub-device target recovered its prior state")
                if args.interactive:
                    input("Inspect the available state, then press Enter to stop: ")
        except Exception:
            print("\n--- ESPHome host log ---", file=sys.stderr)
            print(tail(firmware_log), file=sys.stderr)
            print("\n--- Home Assistant log ---", file=sys.stderr)
            print(tail(ha_log), file=sys.stderr)
            raise
        finally:
            if home_assistant is not None and home_assistant.poll() is None:
                subprocess.run(
                    [podman, "stop", "--time", "5", container_name],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    home_assistant.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    stop_process(home_assistant)
            stop_process(firmware)


def main() -> int:
    """CLI entry point."""
    try:
        run(parse_args())
    except (OSError, RuntimeError, TimeoutError, ValueError) as err:
        print(f"availability E2E failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
