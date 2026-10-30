import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { resolveGame } from "../shortcuts";
import type { Game, GameDetail, RunningGame } from "../types";
import { useComponents } from "../hooks/useComponents";
import { ComponentNotice, SetupPanel } from "./Components";
import { GamesList } from "./GamesList";
import { PluginUpdateNotice } from "./PluginUpdateNotice";
import { TabStrip } from "./TabStrip";
import { Centered, Notice, Pill } from "./Common";
import { upscalerLabel } from "./UpscalerPanel";

/**
 * The Quick Access panel: the plugin's front door, opened over a running game.
 *
 * Two tabs: whether the running game is set up, or a different game to set up.
 * OptiScaler's settings are changed in its own overlay (Insert in game), so
 * there are no controls for them here; setup, logs and library management live
 * on the full page, which this hands off to.
 *
 * It is deliberately terse. This column is ~310px wide and is read with a game
 * running behind it.
 */
export function QuickPanel({
  runningGame,
  onOpenManager,
}: Readonly<{
  runningGame: RunningGame | null;
  onOpenManager: (gamePath?: string, gameName?: string, appid?: string) => void;
}>) {
  // Land on the running game when there is one; otherwise the list is the only
  // thing this panel can usefully show.
  const [tab, setTab] = useState(runningGame ? "now" : "games");
  const { components } = useComponents();

  // Nothing but the set-up until the downloads are there.
  if (!components) return <Centered>확인 중…</Centered>;
  if (!components.setup_done) {
    return (
      <>
        <PluginUpdateNotice />
        <SetupPanel />
      </>
    );
  }

  return (
    <>
      <PluginUpdateNotice />
      <ComponentNotice />
      <TabStrip
        tabs={[
          { id: "now", title: "실행 중" },
          { id: "games", title: "게임" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "now" ? (
        <NowPlayingTab
          runningGame={runningGame}
          onOpenManager={onOpenManager}
          onBrowse={() => setTab("games")}
        />
      ) : (
        <>
          {/* Four rows a page: the pager stays on screen under them, one line
              per game. The full page has room for the reasons. */}
          <GamesList
            pageSize={4}
            compact
            onOpenGame={(game: Game) =>
              onOpenManager(game.path, game.name, game.appid ?? undefined)
            }
          />
          <PanelSection>
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={() => onOpenManager()}>
                라이브러리 및 설정
              </ButtonItem>
            </PanelSectionRow>
          </PanelSection>
        </>
      )}
    </>
  );
}

function NowPlayingTab({
  runningGame,
  onOpenManager,
  onBrowse,
}: Readonly<{
  runningGame: RunningGame | null;
  onOpenManager: (gamePath?: string, gameName?: string, appid?: string) => void;
  onBrowse: () => void;
}>) {
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [resolving, setResolving] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const resolve = useCallback(async () => {
    if (!runningGame) {
      setDetail(null);
      setNotFound(false);
      return;
    }
    setResolving(true);
    setNotFound(false);
    try {
      const result = await resolveGame(runningGame.appid);
      if (result.found && result.detail) {
        setDetail(result.detail);
      } else {
        setDetail(null);
        setNotFound(true);
      }
    } catch {
      setNotFound(true);
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
          <ButtonItem layout="below" onClick={onBrowse}>
            게임 찾아보기
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <>
      <PanelSection title={runningGame.name}>
        <PanelSectionRow>
          <div style={{ padding: "2px 0" }}>
            <InstallPill filename={detail?.install.filename} resolving={resolving} />
            {installed ? (
              <Fsr4Pill
                ready={Boolean(detail?.install.fsr4?.ready)}
                label={upscalerLabel(detail?.install.upscaler)}
              />
            ) : null}
          </div>
        </PanelSectionRow>
        {installed ? (
          <PanelSectionRow>
            {/* Settings are OptiScaler's own to change, in its overlay, and
                most of them apply without a restart there. */}
            <Notice tone="info">설정은 OptiScaler 오버레이(Insert 키)에서 변경합니다.</Notice>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      {resolving ? <Centered>게임을 찾는 중…</Centered> : null}

      {!resolving && notFound ? (
        <PanelSection>
          <PanelSectionRow>
            <Notice tone="warn">설치된 Steam 게임이 아닙니다. 게임 폴더를 라이브러리로 추가하세요.</Notice>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => onOpenManager()}>
              게임 관리
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {!resolving && !notFound && detail ? (
        <PanelSection>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => onOpenManager(detail.path, detail.name, String(runningGame.appid))}
            >
              {installed ? "설치 및 로그" : "OptiScaler 설치"}
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      ) : null}
    </>
  );
}

/** Whether OptiScaler is set up for this game, and under which name. */
function InstallPill({
  filename,
  resolving,
}: Readonly<{ filename?: string | null; resolving: boolean }>) {
  if (filename) return <Pill color="#2f6b3f">{filename}</Pill>;
  return <Pill>{resolving ? "확인 중…" : "설치 안 됨"}</Pill>;
}

/** Whether the upscaler's preset (FSR 4 Lite, or HLX) is in place. */
function Fsr4Pill({ ready, label }: Readonly<{ ready: boolean; label: string }>) {
  return ready ? (
    <Pill color="#3a6ea5">{label}</Pill>
  ) : (
    <Pill color="#5a4a20">{label} 꺼짐</Pill>
  );
}
