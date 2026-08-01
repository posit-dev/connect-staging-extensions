// The server serves this screen only while the Visitor API Key integration is
// missing, so re-check until it is there and then load the dashboard. Otherwise the
// screen is static and a viewer has to know to reload it themselves.

const CHECK_INTERVAL_MS = 3000; // How often to re-check whether setup is done.

const timer = setInterval(async () => {
  try {
    const { status } = await fetch("whoami").then((res) => res.json());
    if (status !== "unconfigured") {
      clearInterval(timer);
      // Reload this frame only. Reloading the whole window would close the Connect
      // settings panel the viewer is using to add the integration.
      location.reload();
    }
  } catch {
    // Connect restarts the content when an integration is added, so ignore the
    // failures while it comes back and try again on the next tick.
  }
}, CHECK_INTERVAL_MS);
