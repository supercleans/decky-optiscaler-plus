import { useCallback, useEffect, useState } from "react";
import { checkUpdates, getComponents } from "../api";
import type { ComponentsStatus } from "../types";

// One answer for every view: the set-up gate, the update notice and Settings
// see the same state, so removing the downloads in Settings takes the whole
// page back to the set-up at once.
let shared: ComponentsStatus | null = null;
const listeners = new Set<(next: ComponentsStatus | null) => void>();

function publish(next: ComponentsStatus | null) {
  shared = next;
  for (const listener of listeners) listener(next);
}

/** Hand a fresher state (from starting a job, or removing the downloads) to every view. */
export function publishComponents(next: ComponentsStatus | undefined) {
  if (next) publish(next);
}

/**
 * What the plugin has downloaded, whether it is set up, and whether newer
 * builds are out. The channels are asked once per mount (the backend keeps
 * the answer for hours); while a set-up, an update or an HLX DLSS build runs,
 * the state is read again every second, so its steps move on screen.
 */
export function useComponents() {
  const [components, setComponents] = useState<ComponentsStatus | null>(shared);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    listeners.add(setComponents);
    return () => {
      listeners.delete(setComponents);
    };
  }, []);

  const refresh = useCallback(async () => {
    try {
      publish(await getComponents());
    } catch {
      // The next tick asks again.
    }
  }, []);

  const check = useCallback(async (force = false) => {
    setChecking(true);
    try {
      publish(await checkUpdates(force));
    } catch {
      // Not knowing about an update is not worth an error in front of a game.
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void refresh().then(() => check(false));
  }, [refresh, check]);

  const busy = Boolean(components?.job.running || components?.build.running);
  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [busy, refresh]);

  return { components, refresh, check, checking, busy };
}
