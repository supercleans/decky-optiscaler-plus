import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { resolveGame } from "../shortcuts";
import type { Game, GameDetail, RunningGame } from "../types";
import { Centered, KeyValue, Notice, Pill } from "./Common";
import { upscalerLabel } from "./UpscalerPanel";

/**
 * The running game, first thing on the page: whether it is set up, and whether
 * FSR 4 Lite is on. Its settings are changed in OptiScaler's own overlay, which
 * applies most of them without a restart, so there are no controls here.
 */
export function NowPlaying({
  runningGame,
  onOpenGame,
  onBrowse,
}: {
  runningGame: RunningGame | null;
  onOpenGame: (game: Game) => void;
  onBrowse: () => void;
}) {
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [resolving, setResolving] = useState(false);

  const resolve = useCallback(async () => {
    if (!runningGame) {
      setDetail(null);
      return;
    }
    setResolving(true);
    try {
      const result = await resolveGame(runningGame.appid);
      setDetail(result.found && result.detail ? result.detail : null);
    } catch {
      setDetail(null);
    } finally {
      setResolving(false);
    }
  }, [runningGame]);

  useEffect(() => {
    void resolve();
  }, [resolve]);

  const installed = Boolean(detail?.install.installed);

  if (!runningGame) {
    return (
      <PanelSection title="실행 중인 게임 없음">
        <PanelSectionRow>
          <Notice tone="info">
            게임을 실행하면 OptiScaler 설치 여부가 여기에 표시됩니다. 그 전에는 설치할 게임을
            고르세요.
          </Notice>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={onBrowse}>
            게임 찾아보기
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  if (resolving && !detail) return <Centered>{runningGame.name} 찾는 중…</Centered>;

  if (!installed) {
    return (
      <PanelSection title={runningGame.name}>
        <PanelSectionRow>
          <Notice tone="info">
            {detail
              ? "이 게임에는 아직 OptiScaler가 설치되지 않았습니다."
              : "설치된 Steam 게임이 아닌 것 같아 폴더를 찾을 수 없습니다."}
          </Notice>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => (detail ? onOpenGame(detail as unknown as Game) : onBrowse())}
          >
            {detail ? "OptiScaler 설치" : "게임 찾아보기"}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const ffx = detail?.install.fsr4?.ffx;
  const fsr4Ready = Boolean(detail?.install.fsr4?.ready);

  return (
    <>
      <PanelSection title={runningGame.name}>
        <PanelSectionRow>
          <div style={{ padding: "2px 0" }}>
            <div style={{ marginBottom: "4px" }}>
              <Pill color="#2f6b3f">
                {detail!.install.engine === "helixsr" ? "HelixSR Scaler" : "OptiScaler"} ·{" "}
                {detail!.install.filename}
              </Pill>
              {fsr4Ready ? (
                <Pill color="#3a6ea5">{upscalerLabel(detail!.install.upscaler)}</Pill>
              ) : (
                <Pill color="#5a4a20">{upscalerLabel(detail!.install.upscaler)} 꺼짐</Pill>
              )}
            </div>
            {/* The version OptiScaler's own FFX Settings box prints. */}
            {ffx?.version ? (
              <KeyValue
                label="FidelityFX"
                value={`${ffx.version}${ffx.fsr4_capable ? " · FSR 4 지원" : ""}`}
              />
            ) : null}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <Notice tone="info">설정은 OptiScaler 오버레이(Insert 키)에서 변경합니다.</Notice>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() =>
              onOpenGame({
                path: detail!.path,
                name: detail!.name,
                appid: String(runningGame.appid),
              } as Game)
            }
          >
            설치 및 로그
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}
