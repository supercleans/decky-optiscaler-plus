import { ButtonItem, DialogButton, Focusable, Tabs } from "@decky/ui";
import { toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { applyAutoSettings, getDropin, getGame, getHelixsrStatus } from "../api";
import { useAutoPlan } from "../hooks/useAutoPlan";
import type {
  DropinStatus,
  GameDetail as GameDetailData,
  HelixsrStatus,
  PayloadStatus,
  RunningGame,
  Upscaler,
} from "../types";
import { Centered, Pill } from "./Common";
import { DetailHeader } from "./DetailHeader";
import { DropinPanel } from "./DropinPanel";
import { FrameGenPanel } from "./FrameGenPanel";
import { InstallPanel } from "./InstallPanel";
import { MonitorTab } from "./MonitorTab";
import { SetupChecklist } from "./SetupChecklist";
import {
  UpscalerPanel,
  currentUpscaler,
  recommendedUpscaler,
  upscalerBlocker,
  upscalerLabel,
  upscalerMethod,
} from "./UpscalerPanel";

interface Props {
  gamePath: string;
  gameName: string;
  appid: string | null;
  status: PayloadStatus | null;
  runningGame: RunningGame | null;
  onBack: () => void;
}

/**
 * The way back out of "Manual setup" and "Logs".
 *
 * A real button rather than a styled `Focusable`: these views open in the Setup
 * tab's place, so B is the page's own back action and cannot be the one that
 * returns here — the row *is* the only way back, and a `Focusable` that happens
 * to take activation was too easy to read as a heading and scroll straight past.
 * It is rendered at both ends of the view it heads, because the manual panel is
 * several screens long and scrolling back to the top to leave it is not a way
 * out either.
 */
function BackRow({
  label,
  onBack,
  position = "top",
}: {
  label: string;
  onBack: () => void;
  position?: "top" | "bottom";
}) {
  const top = position === "top";
  return (
    <Focusable
      style={{ display: "flex", margin: top ? "2px 0 6px" : "10px 0 4px", padding: "0 2px" }}
    >
      <DialogButton
        onClick={onBack}
        onOKActionDescription="설치로 돌아가기"
        // Marker for the UI harness, the same way TabStrip marks its tabs.
        {...({ "data-back": "setup" } as Record<string, string>)}
        style={{
          flexGrow: 1,
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "8px 12px",
          fontSize: "14px",
          minWidth: 0,
        }}
      >
        <span style={{ opacity: 0.7 }}>‹</span>
        {top ? (
          <>
            <span style={{ opacity: 0.7 }}>설치</span>
            <span style={{ opacity: 0.4 }}>/</span>
            <span style={{ fontWeight: 600 }}>{label}</span>
          </>
        ) : (
          <span style={{ fontWeight: 600 }}>단계별 설치로 돌아가기</span>
        )}
      </DialogButton>
    </Focusable>
  );
}

/** Wraps a tab's content so it scrolls within the tab area when it can, and
 *  falls back to scrolling the page when the flex height does not resolve. */
function TabBody({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ maxHeight: "100%", overflowY: "auto", paddingBottom: "24px" }}>
      {children}
    </div>
  );
}

/**
 * One game, set up from one tab.
 *
 * There is no settings screen here on purpose: OptiScaler's own overlay (Insert
 * in game) is where its options are changed, and it changes most of them
 * without a restart. This page puts OptiScaler in, with the FSR 4 Lite preset
 * every install writes, and keeps the steps around it honest.
 */
export function GameDetail({
  gamePath,
  gameName,
  appid,
  status,
  runningGame,
  onBack,
}: Props) {
  const [detail, setDetail] = useState<GameDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("install");
  // The Setup tab is a checklist; the two things it links to open in its place
  // rather than as tabs of their own, because neither is a place to stay.
  const [setupView, setSetupView] = useState<"checklist" | "manual" | "logs">("checklist");
  /** The FSR drop-in's state here, which decides how a drop-in upscaler goes in. */
  const [dropin, setDropin] = useState<DropinStatus | null>(null);
  /** HelixSR Desktop's build, which HLX DLSS comes from. */
  const [helixsr, setHelixsr] = useState<HelixsrStatus | null>(null);
  const [checkingHelixsr, setCheckingHelixsr] = useState(false);
  /** The upscaler picked; until the user picks, the one the game has. */
  const [picked, setPicked] = useState<Upscaler | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [found, swapped] = await Promise.all([
        getGame(gamePath, gameName),
        getDropin(gamePath).catch(() => null),
      ]);
      setDetail(found);
      setDropin(swapped);
    } catch (exc) {
      toaster.toast({ title: "게임을 읽을 수 없습니다", body: String(exc) });
    } finally {
      setLoading(false);
    }
  }, [gamePath, gameName]);

  const recheckHelixsr = useCallback(async () => {
    setCheckingHelixsr(true);
    try {
      setHelixsr(await getHelixsrStatus());
    } catch {
      setHelixsr(null);
    } finally {
      setCheckingHelixsr(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void recheckHelixsr();
  }, [recheckHelixsr]);

  // A different game starts at the top of its own checklist, with its own upscaler.
  useEffect(() => {
    setSetupView("checklist");
    setPicked(null);
  }, [gamePath]);

  const installed = Boolean(detail?.install.installed);
  const targetDir = detail?.install.installed ? detail.install.path : null;
  const isRunning =
    runningGame !== null && appid !== null && String(runningGame.appid) === appid;
  const {
    plan,
    recommendation,
    loading: loadingWiki,
    refreshing: refreshingWiki,
    auto,
    setAuto,
    reload: reloadPlan,
  } = useAutoPlan(gamePath, gameName);

  /**
   * Switching automatic on re-applies the wiki's settings; switching it off
   * only stops them being maintained.
   *
   * Turning it off deliberately does not undo anything. The wiki's settings are
   * the ones that make the game work at all, so reverting them on the way to
   * "let me adjust one thing myself" would break the game to grant a wish
   * nobody made.
   */
  const changeAuto = async (enabled: boolean) => {
    await setAuto(enabled);
    if (!enabled || !targetDir) return;
    const folder = gamePath.split("/").filter(Boolean).pop() ?? gameName;
    const result = await applyAutoSettings(targetDir, gamePath, gameName, [folder]);
    if (result.ok) {
      toaster.toast({ title: "자동 설정을 적용했습니다", body: detailName(plan, gameName) });
    } else {
      toaster.toast({ title: "위키 설정을 적용할 수 없습니다", body: String(result.error) });
    }
  };

  /** After an install or a removal, the list follows what the game has now. */
  const reload = async () => {
    setPicked(null);
    await load();
  };

  if (loading && !detail) return <Centered>게임 폴더를 읽는 중…</Centered>;
  if (!detail) {
    return (
      <Centered>
        <div>게임 폴더를 읽을 수 없습니다.</div>
        <ButtonItem layout="below" onClick={onBack}>
          뒤로
        </ButtonItem>
      </Centered>
    );
  }

  // The upscaler first; how it goes in follows. The drop-in panel is there for
  // a drop-in upscaler and for a drop-in already in place (to take it out), the
  // checklist for an OptiScaler one and for an OptiScaler already in place.
  const dropinPossible = Boolean(dropin?.possible);
  const current = currentUpscaler(detail, dropin);
  const selected: Upscaler = picked ?? current ?? recommendedUpscaler(detail.gpu);
  const method = upscalerMethod(selected, dropinPossible);
  const blocker = upscalerBlocker(selected, helixsr, detail.gpu);
  const showDropin = method === "dropin" || Boolean(dropin?.installed);
  const showChecklist = method !== "dropin" || installed;
  const checklistUpscaler: Upscaler =
    method !== "dropin" ? selected : detail.install.upscaler ?? "fsr4-lite";
  // What the OptiScaler ways need first, by the wiki: REFramework (a step of
  // the checklist) and anything else it names as required.
  const optiscalerNeeds = [
    ...(plan?.reframework?.required ? ["REFramework"] : []),
    ...(plan?.requirements ?? []).filter((item) => item.required).map((item) => item.name),
  ];
  const newestTag =
    detail.install.engine === "helixsr"
      ? helixsr?.found
        ? `helixsr-${helixsr.version ?? "unknown"}`
        : null
      : detail.current_tag ?? null;

  const tabs = [
    {
      id: "install",
      title: "설치",
      content: (
        <TabBody>
          {setupView === "checklist" ? (
            <>
              <UpscalerPanel
                selected={selected}
                current={current}
                dropinPossible={dropinPossible}
                optiscalerNeeds={optiscalerNeeds}
                gpu={detail.gpu}
                helixsr={helixsr}
                checkingHelixsr={checkingHelixsr}
                onSelect={setPicked}
                onRecheckHelixsr={() => void recheckHelixsr()}
              />
              {/* On top of whichever upscaler: a Vulkan layer, not part of the install. */}
              <FrameGenPanel appid={appid} name={detail.name} />
              {showDropin ? (
                <DropinPanel
                  gamePath={detail.path}
                  running={isRunning}
                  upscaler={method === "dropin" ? selected : dropin?.upscaler ?? "fsr412l-lossy"}
                  blocked={method === "dropin" ? blocker : null}
                  onChanged={reload}
                />
              ) : null}
              {showChecklist ? (
                <SetupChecklist
                  detail={detail}
                  appid={appid}
                  plan={plan}
                  recommendation={recommendation}
                  loadingWiki={loadingWiki}
                  refreshing={refreshingWiki}
                  auto={auto}
                  running={isRunning}
                  upscaler={checklistUpscaler}
                  blocked={
                    method === "dropin"
                      ? null
                      : dropin?.installed
                        ? "이 게임에는 FSR 드롭인이 적용되어 있습니다. 위에서 드롭인을 먼저 제거하세요."
                        : blocker
                  }
                  newestTag={newestTag}
                  onSetAuto={(enabled) => changeAuto(enabled)}
                  onManual={() => setSetupView("manual")}
                  onLogs={() => setSetupView("logs")}
                  onChanged={reload}
                  onReloadPlan={() => reloadPlan(false)}
                  onResetConfig={load}
                />
              ) : null}
            </>
          ) : (
            <>
              <BackRow
                label={setupView === "manual" ? "수동 설치" : "로그"}
                onBack={() => setSetupView("checklist")}
              />
              {setupView === "manual" ? (
                <InstallPanel
                  detail={detail}
                  status={status}
                  appid={appid}
                  upscaler={method === "dropin" ? detail.install.upscaler ?? "fsr4-lite" : selected}
                  blocked={method === "dropin" ? null : blocker}
                  onChanged={reload}
                />
              ) : (
                <MonitorTab targetDir={targetDir ?? detail.target} running={isRunning} />
              )}
              <BackRow
                label={setupView === "manual" ? "수동 설치" : "로그"}
                onBack={() => setSetupView("checklist")}
                position="bottom"
              />
            </>
          )}
        </TabBody>
      ),
    },
  ];

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <DetailHeader
        title={detail.name}
        onBack={onBack}
        badges={
          <>
            {installed ? (
              <Pill color="#2f6b3f">{detail.install.filename}</Pill>
            ) : (
              <Pill>설치 안 됨</Pill>
            )}
            {detail.install.fsr4?.ffx?.version ? (
              <Pill>FFX {detail.install.fsr4.ffx.version}</Pill>
            ) : null}
            {installed && detail.install.fsr4?.ready ? (
              <Pill color="#3a6ea5">{upscalerLabel(detail.install.upscaler)}</Pill>
            ) : dropin?.installed ? (
              <Pill color="#3a6ea5">{upscalerLabel(dropin.upscaler)} 드롭인</Pill>
            ) : null}
            {isRunning ? <Pill color="#3a6ea5">실행 중</Pill> : null}
          </>
        }
      />

      <div style={{ flexGrow: 1, minHeight: 0 }}>
        <Tabs activeTab={activeTab} onShowTab={setActiveTab} tabs={tabs} autoFocusContents />
      </div>
    </div>
  );
}

/** The wiki entry's own name for a game, for a toast that names what was used. */
function detailName(plan: { game: string | null } | null, fallback: string) {
  return plan?.game ?? fallback;
}
