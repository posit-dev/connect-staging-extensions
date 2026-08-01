// The server serves this screen only while the Visitor API Key integration is
// missing, so re-check until it is there and then load the dashboard. Otherwise the
// screen is static and a viewer has to know to reload it themselves.

const CHECK_INTERVAL_MS = 3000; // How often to re-check whether setup is done.

const timer = setInterval(async () => {
  try {
    const { status } = await fetch("whoami").then((res) => res.json());
    // Wait for a working identity specifically: "unavailable" means Connect is having
    // trouble, which setup can't fix.
    if (status === "signed-in") {
      clearInterval(timer);
      // Go to the app rather than reload, because this screen is also reachable
      // directly at /setup.html, where reloading would just show it again. Staying in
      // this frame keeps the Connect settings panel the viewer is using open.
      location.replace(".");
    }
  } catch {
    // Connect restarts the content when an integration is added, so ignore the
    // failures while it comes back and try again on the next tick.
  }
}, CHECK_INTERVAL_MS);
