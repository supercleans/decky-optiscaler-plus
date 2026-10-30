import { ButtonItem, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { getOptipatcherStatus, installOptipatcher } from "../api";
import type { OptipatcherStatus } from "../types";
import { Notice } from "./Common";

/** What OptiPatcher buys a game it covers, the same wherever it is offered. */
export const OPTIPATCHER_WHY =
  "게임이 GPU를 확인하는 부분을 실행 중에 패치해, GPU를 NVIDIA로 속이지(스푸핑) 않고도 " +
  "DLSS 및 DLSS-FG 입력을 열어 줍니다. 스푸핑 때문에 생기는 충돌이나 잘못된 설정을 피할 수 " +
  "있고, Red Dead Redemption 2처럼 이것이 있어야 OptiScaler가 동작하는 게임도 있습니다.";

/** What OptiPatcher does to a game the wiki does not list it for. */
export const OPTIPATCHER_UNLISTED =
  "OptiScaler 위키에 이 게임은 OptiPatcher 지원으로 등록되어 있지 않습니다. 패턴이 없는 " +
  "게임에서는 아무 효과가 없습니다.";

/**
 * Why an install that asked for OptiPatcher went in without it, or null.
 *
 * It is downloaded on first use, and a failed download does not fail the
 * install, so the install's answer is where that has to be read. `install`
 * returns it at the top level, `autoInstall` under `install`.
 */
export function optipatcherMissed(result: unknown): string | null {
  type Shape = { optipatcher?: { installed?: boolean; error?: string | null } };
  const outer = result as Shape & { install?: Shape };
  const patcher = outer?.optipatcher ?? outer?.install?.optipatcher;
  return patcher && !patcher.installed && patcher.error ? patcher.error : null;
}

/**
 * OptiPatcher, added or removed after the fact.
 *
 * It is a separate ASI from the OptiScaler project that patches supported games
 * so their DLSS / DLSS-FG inputs are visible without spoofing the GPU through
 * DXGI. Games differ on whether they need it, so it stays opt-in rather than
 * being installed for everyone. ``recommended`` is the wiki entry's OptiPatcher
 * column, when an entry matched.
 */
export function OptipatcherPanel({
  targetDir,
  recommended,
}: {
  targetDir: string;
  recommended?: boolean;
}) {
  const [status, setStatus] = useState<OptipatcherStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getOptipatcherStatus(targetDir));
    } catch (exc) {
      setError(String(exc));
    }
  }, [targetDir]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!status) return null;

  const toggle = async (enabled: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const result = await installOptipatcher(targetDir, enabled);
      if (!result.ok) setError(result.error ?? "OptiPatcher를 변경할 수 없습니다");
      await refresh();
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection title="OptiPatcher">
      <PanelSectionRow>
        <ToggleField
          label="OptiPatcher 설치"
          description={
            status.available
              ? `${recommended ? "위키 권장. " : ""}${OPTIPATCHER_WHY}`
              : "OptiPatcher를 다운로드할 수 없고 이 플러그인에도 포함되어 있지 않습니다."
          }
          checked={status.installed}
          disabled={busy || !status.available}
          bottomSeparator="standard"
          onChange={(checked) => void toggle(checked)}
        />
      </PanelSectionRow>

      {error ? (
        <PanelSectionRow>
          <Notice tone="error">{error}</Notice>
        </PanelSectionRow>
      ) : null}

      {recommended && !status.installed && status.available ? (
        <PanelSectionRow>
          <Notice tone="warn" title="위키에서 이 게임에 OptiPatcher를 권장합니다">
            OptiScaler 위키에 이 게임은 OptiPatcher 지원으로 등록되어 있습니다. 위 토글로
            켜면 다음 실행부터 적용됩니다.
          </Notice>
        </PanelSectionRow>
      ) : null}
      {recommended === false && status.installed ? (
        <PanelSectionRow>
          <Notice tone="info" title="위키 권장 게임이 아닙니다">
            {OPTIPATCHER_UNLISTED}
          </Notice>
        </PanelSectionRow>
      ) : null}

      {/* Each rolling build adds games, so an older one may not know this one. */}
      {status.installed && status.outdated ? (
        <>
          <PanelSectionRow>
            <Notice tone="warn" title="새 OptiPatcher 빌드가 있습니다">
              이 게임에는 이전 빌드가 설치되어 있습니다. 새 빌드에는 더 많은 게임의 패치가
              들어 있습니다.
            </Notice>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={() => void toggle(true)}>
              {busy ? "업데이트 중…" : `${status.version ?? "새 빌드"}(으)로 업데이트`}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : null}

      <PanelSectionRow>
        <Notice tone="info" title={status.installed ? "설치됨" : "확인 방법"}>
          {status.installed
            ? "패치가 실제로 적용되면 OptiScaler 오버레이의 게임 제목 옆에 (OP)가 표시되고 Spoof는 OFF로 나옵니다."
            : "켜고 나면 OptiScaler 오버레이의 게임 제목 옆 (OP) 표시로 패치가 적용됐는지 볼 수 있습니다. 패턴이 없는 게임에는 아무 영향이 없습니다."}{" "}
          빌드: {status.version ?? "아직 다운로드하지 않음 — 켜면 최신 rolling 빌드를 받습니다"}.
        </Notice>
      </PanelSectionRow>
    </PanelSection>
  );
}
