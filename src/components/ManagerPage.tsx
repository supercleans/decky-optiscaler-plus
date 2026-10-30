import { PanelSection, PanelSectionRow, Tabs } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { getStatus } from "../api";
import { resolveGame } from "../shortcuts";
import {
  subscribeManagerTarget,
  takePendingTarget,
  targetFromUrl,
} from "../navigation";
import type { ManagerTarget } from "../navigation";
import { useComponents } from "../hooks/useComponents";
import { useRunningGame } from "../hooks/useRunningGame";
import type { Game, PayloadStatus } from "../types";
import { Centered, Notice } from "./Common";
import { ComponentNotice, SetupPanel } from "./Components";
import { GameDetail } from "./GameDetail";
import { GamesList } from "./GamesList";
import { LibraryBrowser } from "./LibraryBrowser";
import { NowPlaying } from "./NowPlaying";
import { PluginUpdateNotice } from "./PluginUpdateNotice";
import { SettingsTab } from "./SettingsTab";

interface Selection {
  path: string;
  name: string;
  appid: string | null;
}

/** Full-screen page: library browser, or one game's detail view. */
export function ManagerPage() {
  const [status, setStatus] = useState<PayloadStatus | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const runningGame = useRunningGame();
  // Land on the running game when there is one; otherwise the games list is
  // what the page is for. The current app is read synchronously on mount, so
  // this is the real answer rather than a guess that corrects itself.
  const [tab, setTab] = useState(() => (runningGame ? "now" : "games"));
  const { components } = useComponents();

  /**
   * Open at whichever game was asked for.
   *
   * The Quick Access panel knows the folder and can hand it over directly; the
   * Steam context menu only knows the app id, so that has to be looked up
   * first. A request naming neither is a request for the library list.
   */
  const openTarget = useCallback((target: ManagerTarget) => {
    setResolveError(null);
    if (target.path && target.name) {
      setResolving(false);
      setSelection({ path: target.path, name: target.name, appid: target.appid ?? null });
      return;
    }
    if (!target.appid) {
      setResolving(false);
      setSelection(null);
      return;
    }
    const appid = target.appid;
    setResolving(true);
    void (async () => {
      try {
        const game = await resolveGame(appid);
        if (game.found && game.path && game.name) {
          setSelection({ path: game.path, name: game.name, appid });
        } else {
          // A Steam game with no manifest, or a non-Steam shortcut whose
          // target has moved: the folder was worked out from the shortcut's
          // executable and there was no executable there to work from.
          setResolveError(
            "Steam과 이 게임의 바로 가기 모두 존재하는 폴더를 가리키지 않아 바로 열 수 없습니다. " +
              "라이브러리 목록에서 고르거나, 게임이 있는 폴더를 사용자 지정 라이브러리로 " +
              "추가하세요.",
          );
        }
      } catch (err) {
        setResolveError(String(err));
      } finally {
        setResolving(false);
      }
    })();
  }, []);

  // The request the page was opened with, plus any that arrives while it stays
  // open — the Quick Access panel can be pulled up over this page, so picking a
  // game there has to reach a component that is already mounted.
  useEffect(() => {
    const initial = takePendingTarget() ?? targetFromUrl();
    if (initial) openTarget(initial);
    return subscribeManagerTarget(openTarget);
  }, [openTarget]);

  // Only read, never fetched from here: OptiScaler is downloaded by the
  // plugin's set-up, not by opening a page.
  useEffect(() => {
    void (async () => {
      try {
        setStatus(await getStatus());
      } catch {
        /* surfaced by the banners below */
      }
    })();
  }, []);

  // A downloaded nightly still has to be unpacked, and that needs an archiver.
  const noExtractor = status !== null && !status.extracted && !status.extractor;
  // Nothing but the set-up until the downloads are there.
  const gate = !components ? (
    <Centered>확인 중…</Centered>
  ) : !components.setup_done ? (
    <>
      <PluginUpdateNotice />
      <SetupPanel />
    </>
  ) : null;
  if (gate) {
    return <div style={{ marginTop: "40px", padding: "0 12px 40px", overflowY: "auto" }}>{gate}</div>;
  }

  return (
    <div
      style={{
        marginTop: "40px",
        height: "calc(100% - 40px)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        // Only the library list scrolls as a page; the detail view lays out its
        // own header and scrolling tab body.
        overflowY: selection ? "hidden" : "auto",
        padding: selection ? "0" : "0 12px 40px",
      }}
    >
      {!selection ? <PluginUpdateNotice /> : null}
      {!selection ? <ComponentNotice /> : null}

      {noExtractor ? (
        <PanelSection title="OptiScaler">
          <PanelSectionRow>
            <Notice tone="error" title="압축 해제 도구가 없습니다">
              OptiScaler의 압축을 풀려면 <code>7z</code>, <code>7zz</code>,
              <code> 7za</code>, <code>7zr</code>, <code>bsdtar</code> 중 하나가 필요하지만
              이 시스템에는 하나도 없습니다.
            </Notice>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {resolving ? (
        <PanelSection>
          <PanelSectionRow>
            <Notice tone="info">게임의 설치 폴더를 찾는 중…</Notice>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {resolveError ? (
        <PanelSection>
          <PanelSectionRow>
            <Notice tone="error" title="이 게임을 열 수 없습니다">
              {resolveError}
            </Notice>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {selection ? (
        <GameDetail
          gamePath={selection.path}
          gameName={selection.name}
          appid={selection.appid}
          status={status}
          runningGame={runningGame}
          onBack={() => setSelection(null)}
        />
      ) : (
        <Tabs
          activeTab={tab}
          onShowTab={setTab}
          tabs={[
            {
              id: "now",
              title: "실행 중",
              content: (
                <NowPlaying
                  runningGame={runningGame}
                  onOpenGame={(game: Game) =>
                    setSelection({ path: game.path, name: game.name, appid: game.appid })
                  }
                  onBrowse={() => setTab("games")}
                />
              ),
            },
            {
              id: "games",
              title: "게임",
              content: (
                <GamesList
                  onOpenGame={(game: Game) =>
                    setSelection({ path: game.path, name: game.name, appid: game.appid })
                  }
                />
              ),
            },
            { id: "libraries", title: "라이브러리", content: <LibraryBrowser /> },
            // Plugin-wide, so it belongs here rather than in the Quick Access
            // panel: nothing on it is about the game currently running.
            { id: "settings", title: "설정", content: <SettingsTab status={status} /> },
          ]}
        />
      )}
    </div>
  );
}
