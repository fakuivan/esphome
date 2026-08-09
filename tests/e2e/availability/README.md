# ESPHome availability Home Assistant E2E

This opt-in harness verifies sub-device availability against a real Home
Assistant server and its real ESPHome integration. It is not part of the normal
test suite because it pulls and starts a Home Assistant container.

The harness needs local checkouts containing the companion aioesphomeapi and
Home Assistant Core changes. It bind-mounts those sources into an official Home
Assistant image; it does not install or upload either checkout.

Run it from an ESPHome development environment:

```bash
python tests/e2e/availability/run.py \
  --aio-checkout ../aioesphomeapi-availability \
  --ha-core-checkout ../home-assistant-core-availability \
  --keep-running
```

The test does the following:

1. Compiles and starts the ESPHome host fixture.
2. Starts an isolated Home Assistant container and completes onboarding.
3. Adds the host fixture through Home Assistant's ESPHome config flow.
4. Presses an ESPHome button through Home Assistant to make a sub-device
   unavailable.
5. Verifies the associated Home Assistant entity is `unavailable`.
6. Requests availability again and verifies its prior state returns.

With `--keep-running` (also available as `--interactive`), the test prints a
browser URL and pauses once while the target is unavailable and again after it
recovers. The isolated server has one ephemeral user and accepts trusted
localhost browser connections, so the dashboard opens without a login prompt.
The server and host fixture stop after the second prompt.

The default image is `ghcr.io/home-assistant/home-assistant:stable`. Pass
`--ha-image` to test an exact release, development image, or image digest.
