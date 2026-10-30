import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { getDropin, installDropin, removeDropin } from "../api";
import type { DropinStatus, Upscaler } from "../types";
import { Mono, Notice } from "./Common";
import { upscalerLabel } from "./UpscalerPanel";

/**
 * FSR 4 through the game's own FSR 3.1, by swapping its DLL: no OptiScaler and
 * no REFramework. Shown for a game that ships FSR 3.1 as a DX12 DLL, when a
 * drop-in upscaler is picked or one is already in place.
 *
 * ``upscaler`` is the drop-in to put in: one of cyboman's FSR 4.1.2 Lite
 * builds or HLX FSR 4 from HelixSR's releases, downloaded; or AMD's own FSR
 * 4.1.2 from the OptiScaler nightly, as a test. One already in place of
 * another kind is swapped for it. The drop-in and OptiScaler never share a folder: the backend refuses
 * either while the other is in.
 */
export function DropinPanel({
  gamePath,
  running,
  upscaler,
  blocked,
  onChanged,
}: Readonly<{
  gamePath: string;
  running: boolean;
  upscaler: Upscaler;
  /** Why the picked drop-in cannot go in now (no HelixSR build), or null. */
  blocked?: string | null;
  onChanged: () => Promise<void> | void;
}>) {
  const [state, setState] = useState<DropinStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setState(await getDropin(gamePath));
    } catch {
      setState(null);
    }
  }, [gamePath]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!state?.possible) return null;

  const name = upscalerLabel(upscaler);
  const act = async (install: boolean) => {
    setBusy(true);
    try {
      const result = install
        ? await installDropin(gamePath, upscaler)
        : await removeDropin(gamePath);
      if (!result.ok) {
        toaster.toast({
          title: install ? "드롭인을 적용하지 못했습니다" : "드롭인을 제거하지 못했습니다",
          body: String(result.error),
        });
        return;
      }
      toaster.toast({
        title: install ? `${name} 드롭인을 적용했습니다` : "FSR 드롭인을 제거했습니다",
        body: install
          ? `게임 설정에서 FSR을 선택하면 ${name}로 동작합니다.`
          : "게임의 원래 FSR 파일을 복원했습니다.",
      });
      await load();
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  const hlx = upscaler === "hlx-fsr4";
  const amd = upscaler === "fsr4-lite";
  const other = state.installed && (state.upscaler ?? "fsr412l-lossy") !== upscaler;
  const optiscaler = Boolean(state.optiscaler_installed) && !state.installed;
  const layout = hlx
    ? "게임의 FSR 3.1 파일 자리에 HLX FSR 4를 넣고, 원래 파일은 옆에 *.original.dll로 둡니다(HLX FSR 4가 처리하지 않는 요청을 넘깁니다)."
    : state.layout === "monolithic"
      ? "통합형 FSR 3.1 DLL을 AMD 로더와 FSR 4 업스케일러로 바꿉니다."
      : "게임의 FSR 3.1 업스케일러 파일을 FSR 4로 바꿉니다.";
  const installedName = upscalerLabel(state.upscaler ?? "fsr412l-lossy");

  return (
    <PanelSection title="FSR 드롭인">
      <PanelSectionRow>
        {state.installed && state.intact && !other ? (
          <Notice tone="success" title={`${installedName} 드롭인 적용됨`}>
            {state.tag} · {state.variant}. 게임 설정에서 FSR을 선택하면 {installedName}로
            동작합니다. OptiScaler와 REFramework 없이 동작합니다.
          </Notice>
        ) : state.installed && !state.intact ? (
          <Notice tone="warn" title="게임 업데이트로 원래 파일이 돌아왔습니다">
            드롭인 기록은 있지만 FSR 파일이 바뀌어 있습니다. 다시 적용하거나 제거하세요.
          </Notice>
        ) : other ? (
          <Notice tone="info" title={`${installedName} 드롭인이 적용되어 있습니다`}>
            {name}로 바꾸면 지금 드롭인을 제거하고 원래 파일을 복원한 뒤 {name}를 넣습니다.
          </Notice>
        ) : optiscaler ? (
          <Notice tone="info" title="OptiScaler가 설치되어 있습니다">
            드롭인과 OptiScaler는 함께 쓸 수 없습니다. 드롭인을 쓰려면 아래에서 먼저 OptiScaler를
            제거하세요.
          </Notice>
        ) : blocked ? (
          <Notice tone="warn" title={`${name} 드롭인을 지금은 넣을 수 없습니다`}>
            {blocked}
          </Notice>
        ) : (
          <Notice tone="info" title={`OptiScaler 없이 ${name} 사용 가능`}>
            이 게임은 자체 FSR 3.1 파일이 있어서, 파일을 바꾸는 것만으로{" "}
            {hlx
              ? "HLX FSR 4(HelixSR 공식 릴리스에서 받음)"
              : amd
                ? "AMD의 FSR 4.1.2(OptiScaler nightly에 들어 있는 파일)"
                : `${name}(cyboman의 Steam Deck용 빌드)`}
            를 쓸 수 있습니다. OptiScaler와 REFramework가 필요 없습니다. {layout} 원본은 백업했다가
            제거할 때 복원합니다. 온라인 게임이나 안티치트가 있는 게임에는 쓰지 마세요.
            {amd
              ? " 시험용입니다: AMD 파일의 GPU 확인이 Steam Deck을 거부하면 FSR을 골라도 게임이 FSR 4를 쓰지 못하거나 FSR 옵션이 사라질 수 있습니다. 그러면 드롭인을 제거하고 다른 업스케일러를 고르세요."
              : ""}
          </Notice>
        )}
      </PanelSectionRow>
      {state.installed ? (
        <>
          {!state.intact || other ? (
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy || running || Boolean(blocked)}
                onClick={() => void act(true)}
              >
                {busy ? "처리 중…" : other ? `${name}로 바꾸기` : "다시 적용"}
              </ButtonItem>
            </PanelSectionRow>
          ) : null}
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || running} onClick={() => void act(false)}>
              {busy ? "처리 중…" : "드롭인 제거"}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : !optiscaler && !blocked ? (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy || running} onClick={() => void act(true)}>
            {busy
              ? "다운로드하고 적용하는 중…"
              : running
                ? "게임을 종료한 뒤 적용할 수 있습니다"
                : `${name} 드롭인 적용`}
          </ButtonItem>
        </PanelSectionRow>
      ) : null}
      {state.dir ? (
        <PanelSectionRow>
          <div style={{ fontSize: "12px", opacity: 0.7, padding: "2px 0" }}>
            위치: <Mono>{state.dir}</Mono>
          </div>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}
