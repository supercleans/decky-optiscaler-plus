import { toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { checkPluginUpdate } from "../api";
import type { PluginUpdate } from "../types";

/**
 * Decky Loader's own frontend bridge. Not part of @decky/api, so it is reached
 * as the global the loader defines, and every use checks it is there.
 */
declare global {
  // eslint-disable-next-line no-var
  var DeckyBackend:
    | { callable?: <A extends unknown[], R>(route: string) => (...args: A) => Promise<R> }
    | undefined;
}

/** Decky's InstallType.UPDATE: replace the installed copy of the same name. */
const INSTALL_TYPE_UPDATE = 2;

/**
 * Hand the release to Decky's own installer.
 *
 * Decky downloads the zip, checks it against the SHA-256, and asks the user to
 * confirm before replacing anything; once installed it reloads the plugin. This
 * only starts that, so it resolves as soon as Decky's prompt is up.
 */
export async function installPluginUpdate(update: PluginUpdate) {
  const backend = globalThis.DeckyBackend;
  if (!backend || typeof backend.callable !== "function") {
    throw new Error(
      "이 Decky Loader에서는 플러그인이 업데이트를 시작할 수 없습니다. 릴리스 페이지에서 새 zip을 설치하세요."
    );
  }
  if (!update.update_available || !update.url || !update.sha256 || !update.latest) {
    throw new Error("설치할 새 릴리스가 없습니다.");
  }
  await backend.callable<[string, string, string, string, number], unknown>(
    "utilities/install_plugin"
  )(update.url, update.name, update.latest, update.sha256, INSTALL_TYPE_UPDATE);
}

/**
 * Whether a newer plugin release is out. Asked once per mount; the backend
 * keeps its answer for hours, so this costs nothing on the next open.
 */
export function usePluginUpdate() {
  const [update, setUpdate] = useState<PluginUpdate | null>(null);
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);

  const check = useCallback(async (force = false) => {
    setChecking(true);
    try {
      setUpdate(await checkPluginUpdate(force));
    } catch {
      // Not knowing about an update is not worth an error in front of a game.
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check(false);
  }, [check]);

  const install = useCallback(async () => {
    if (!update) return;
    setInstalling(true);
    try {
      await installPluginUpdate(update);
      toaster.toast({
        title: `${update.latest} 버전 업데이트를 확인하세요`,
        body: "Decky가 설치 전에 확인을 요청한 뒤 플러그인을 다시 불러옵니다.",
      });
    } catch (exc) {
      toaster.toast({ title: "업데이트를 시작할 수 없습니다", body: String(exc) });
    } finally {
      setInstalling(false);
    }
  }, [update]);

  return { update, checking, installing, check, install };
}
