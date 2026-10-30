import {
  ButtonItem,
  DialogButton,
  Field,
  Focusable,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  showModal,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { FaCheck } from "react-icons/fa";
import {
  applyFsr4Preset,
  autoInstall,
  getMonitor,
  install,
  installPdPlugin,
  installReframework,
  refreshWiki,
  removeReframework,
  resetConfig,
  setAutoMode,
  setGameTarget,
  uninstall,
} from "../api";
import { setLaunchOptions } from "../hooks/useRunningGame";
import {
  currentLaunchOptions,
  hasOverride,
  launchChoices,
  mergeLaunchOptions,
  overrideStem,
  recordPreviousLaunchOptions,
  recordedValue,
  resolveChoice,
  stripOverride,
} from "../launchOptions";
import type { LaunchAction, LaunchState } from "../launchOptions";
import { PREF_REMOVE_LAUNCH, isRemembering, recallLaunchAction, remember } from "../prefs";
import type {
  AutoPlan,
  GameDetail,
  MonitorReport,
  PlannedReframework,
  PlannedRequirement,
  Recommendation,
  Upscaler,
} from "../types";
import { Mono, Notice, Pill } from "./Common";
import { OPTIPATCHER_WHY, optipatcherMissed } from "./OptipatcherPanel";
import { PdPluginGuide } from "./PdPluginGuide";
import { RemovePrompt } from "./RemovePrompt";
import { customMissed, isCustom, upscalerLabel } from "./UpscalerPanel";

/**
 * Setting a game up, as a checklist rather than a page of panels.
 *
 * Three things have to happen for OptiScaler to work: the DLL goes next to the
 * game's executable, Steam has to be told to load it instead of Proton's own,
 * and the settings the wiki names for this game have to reach the ini. The old
 * Setup tab had all three, spread over nine sections and a mode switch, and
 * nothing said what had been done. This says all three before they happen and
 * keeps saying them afterwards, which is the same list read twice.
 *
 * Only the first is compulsory: the launch options and the wiki's settings each
 * carry a toggle, before the install as a choice and after it as the way to
 * undo that step alone. Everything else — the file name, the folder,
 * OptiPatcher, picking a different wiki entry — is behind "Manual setup",
 * because it is a minority of set-ups and all of it has a default that works.
 *
 * Every install also writes the preset of the upscaler picked above the list
 * (FSR 4 Lite, or HLX DLSS / HLX FSR 4 through HelixSR Scaler), so that is
 * not a step to choose but a row to check
 * afterwards: OptiScaler's own overlay can save other values over it.
 */
interface Props {
  detail: GameDetail;
  appid: string | null;
  plan: AutoPlan | null;
  recommendation: Recommendation | null;
  loadingWiki: boolean;
  /** True while a background wiki refresh could still change the plan below. */
  refreshing?: boolean;
  auto: boolean;
  /** Whether this game is the one running right now. */
  running: boolean;
  /** The upscaler picked above the list: FSR 4 Lite, HLX DLSS or HLX FSR 4. */
  upscaler: Upscaler;
  /** Why it cannot be installed now (no HelixSR build, a drop-in in the way), or null. */
  blocked?: string | null;
  /** The build a reinstall would bring: the nightly's tag, or HelixSR's. */
  newestTag?: string | null;
  onSetAuto: (enabled: boolean) => Promise<void> | void;
  onManual: () => void;
  onLogs: () => void;
  onChanged: () => Promise<void> | void;
  onReloadPlan: () => Promise<void> | void;
  onResetConfig: () => Promise<void> | void;
}

/** The numbered circle before a step, or a tick once it is done. */
function Mark({ n, done }: Readonly<{ n?: number; done?: boolean }>) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "22px",
        height: "22px",
        borderRadius: "50%",
        marginRight: "9px",
        flexShrink: 0,
        fontSize: "11px",
        fontWeight: 700,
        background: done ? "#3e8a4a" : "transparent",
        border: done ? "none" : "1.5px solid rgba(255,255,255,0.3)",
        color: done ? "#fff" : "rgba(255,255,255,0.65)",
      }}
    >
      {done ? <FaCheck size={11} /> : n}
    </span>
  );
}

function StepLabel({ n, done, children }: Readonly<{
  n?: number;
  done?: boolean;
  children: React.ReactNode;
}>) {
  return (
    <span style={{ display: "flex", alignItems: "center", minWidth: 0 }}>
      <Mark n={n} done={done} />
      <span style={{ minWidth: 0 }}>{children}</span>
    </span>
  );
}

function shorten(path: string, keep = 3) {
  const parts = path.split("/").filter(Boolean);
  return parts.length <= keep ? path : `…/${parts.slice(-keep).join("/")}`;
}

/**
 * Why there is no plan: the list could not be downloaded, or this game is not
 * on it.
 *
 * These are not the same thing and used to render identically. A game that is
 * genuinely not in the compatibility list is the ordinary case and nothing is
 * wrong; a list that would not download is a fault, usually a network one, and
 * telling the user "no wiki entry matched this game" for every game they open
 * is how "the wiki feature is not working" becomes impossible to act on. The
 * failure is printed in the words of whatever actually failed, with the one
 * button that can do anything about it.
 */
function WikiTrouble({
  recommendation,
  busy,
  onRetry,
}: Readonly<{
  recommendation: Recommendation | null;
  busy: boolean;
  onRetry: () => void;
}>) {
  const unreachable = recommendation !== null && !recommendation.list_available;
  if (!unreachable) {
    return (
      <Notice tone="warn" title="일치하는 위키 항목이 없습니다">
        OptiScaler는 대부분의 DLSS, FSR 2+, XeSS 게임에서 작동합니다. 직접 설치하거나(보통
        <Mono>dxgi.dll</Mono>) 위키 목록에서 이 게임을 직접 찾아보세요.
      </Notice>
    );
  }
  return (
    <>
      <Notice tone="error" title="호환성 목록을 다운로드할 수 없습니다">
        게임이 목록에 없다는 뜻이 아니라, 아무것도 확인하지 못했다는 뜻입니다.{" "}
        {recommendation?.list_meta?.error ? <Mono>{recommendation.list_meta.error}</Mono>
          : "위키에 연결할 수 없습니다."}{" "}
        Deck의 네트워크 연결을 확인한 뒤 다시 시도하세요. 수동 설치는 어느 경우에나 가능합니다.
      </Notice>
      <Focusable style={{ display: "flex", marginTop: "6px" }}>
        <DialogButton
          disabled={busy}
          onClick={onRetry}
          onOKActionDescription="호환성 목록 다시 다운로드"
          style={{ flexGrow: 1 }}
        >
          {busy ? "시도 중…" : "다시 시도"}
        </DialogButton>
      </Focusable>
    </>
  );
}

/** What the wiki asks to be written, as one readable line. */
function settingsSummary(plan: AutoPlan) {
  const pairs = plan.settings.map((item) => `${item.key}=${item.value}`);
  const fg =
    plan.framegen && plan.framegen.input !== "nofg"
      ? `${plan.framegen.input_label} → ${plan.framegen.output_label} 프레임 생성`
      : null;
  return [pairs.join(", "), fg].filter(Boolean).join(", 그리고 ");
}

/**
 * The REFramework step, said in one line.
 *
 * Which build matters and is not interchangeable: praydog's unified nightly and
 * the per-game pd-upscaler branch are different mods that happen to share a
 * filename, and the entries that want one explicitly do not work with the
 * other. Naming it is also what makes the step checkable by hand afterwards.
 */
function reframeworkSummary(ref: PlannedReframework) {
  const build =
    ref.variant === "pd-upscaler"
      ? "이 게임용 pd-upscaler 빌드"
      : "praydog의 nightly 빌드";
  if (ref.automatic) return `${build}를 다운로드하고 ${ref.dll} 파일을 실행 파일 옆에 둡니다.`;
  // The reason is a clause written to sit mid-sentence — "no build is known for
  // this game", "this plugin no longer downloads it for you" — and this is
  // where it starts one.
  const why = ref.reason ?? "여기서는 다운로드할 수 없습니다";
  return `${why.charAt(0).toUpperCase()}${why.slice(1)} — ${ref.page}에서 ${build}를 받아 ${ref.dll} 파일을 실행 파일 옆에 직접 두세요.`;
}

/**
 * The one file in this whole flow that cannot be automatic.
 *
 * PureDark's UpscalerBasePlugin may not be redistributed and is on Nexus Mods
 * behind a login, so the user downloads it and leaves it in Downloads, where
 * the backend finds it. The pd-upscaler games do not upscale without it: an
 * install that reports success and leaves the game rendering exactly as before
 * is the failure this row is here to stop, so where it is missing the row says
 * where to get it, where to put it, and looks again when asked.
 */
/* The prop is `wanted`, not `ref`: React reserves `ref`, strips it from the
   props object, and the component receives nothing at all. */
function PluginStep({
  wanted,
  present,
  installed,
  busy,
  onRecheck,
  onInstall,
}: Readonly<{
  wanted: PlannedReframework;
  /** Already next to this game's executable. */
  present: boolean;
  /** OptiScaler is set up here, so the file can go in on its own. */
  installed: boolean;
  busy: boolean;
  onRecheck: () => void;
  onInstall: () => void;
}>) {
  if (!wanted.plugin) return null;
  const ready = Boolean(wanted.plugin_ready);
  // Before the install, a supplied file goes in with REFramework. After it, it
  // is a button: the install has already happened without it.
  const withInstall = ready && !installed && wanted.automatic;
  return (
    <>
      <PanelSectionRow>
        <Field
          label={
            <StepLabel done={present}>
              {present ? (
                <>
                  <Mono>{wanted.plugin}</Mono> 있음
                </>
              ) : withInstall ? (
                <>
                  <Mono>{wanted.plugin}</Mono> 함께 설치
                </>
              ) : ready ? (
                <>
                  <Mono>{wanted.plugin}</Mono> 게임에 넣기
                </>
              ) : (
                <>
                  <Mono>{wanted.plugin}</Mono> 직접 받기
                </>
              )}
            </StepLabel>
          }
          description={
            present
              ? `출처: ${wanted.plugin_name}. 이 단계는 더 할 일이 없습니다.`
              : withInstall
                ? `받아 둔 ${wanted.plugin} 파일을 REFramework와 함께 실행 파일 옆에 설치합니다.
                   libxess.dll도 같은 위치에 복사합니다.`
                : ready
                  ? `받아 둔 ${wanted.plugin} 파일을 이 게임의 실행 파일 옆에 넣습니다. libxess.dll도
                     같은 위치에 복사합니다.`
                  : `이 게임에는 ${wanted.plugin_name}의 ${wanted.plugin}이(가) 필요합니다. 없으면
                     OptiScaler가 로드되어도 화면에 아무 변화가 없습니다.`
          }
          bottomSeparator="standard"
          childrenLayout="inline"
          childrenContainerWidth="min"
          focusable
        >
          {present ? (
            <Pill color="#2f6b3f">완료</Pill>
          ) : withInstall ? (
            <Pill>자동</Pill>
          ) : ready ? null : (
            <Pill color="#5a4a20">직접</Pill>
          )}
        </Field>
      </PanelSectionRow>
      {!present && ready && installed ? (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={onInstall}>
            {`${wanted.plugin} 게임에 넣기`}
          </ButtonItem>
        </PanelSectionRow>
      ) : null}
      {!present && (!ready || !wanted.plugin_verified) ? (
        <PdPluginGuide
          name={wanted.plugin}
          build={wanted.plugin_name ?? "UpscalerBasePlugin 1.1.2"}
          url={wanted.plugin_url ?? "https://www.nexusmods.com/site/mods/502"}
          folder={wanted.plugin_folder ?? "~/Downloads"}
          present={ready}
          verified={Boolean(wanted.plugin_verified)}
          busy={busy}
          onRecheck={onRecheck}
        />
      ) : null}
    </>
  );
}

/**
 * What the plan will do to the overlay's shortcut key, said out loud.
 *
 * Several REFramework entries ask for `ShortcutKey=0x24` because REF's own
 * overlay is on Insert as well. Applying it is right; applying it in silence is
 * not — "pressing Insert doesn't pop the OptiScaler overlay" is what a moved
 * key looks like from the outside, and it reads as the plugin being broken.
 */
const REQUIREMENT_KIND: Record<PlannedRequirement["kind"], string> = {
  mod: "모드",
  file: "파일",
  config: "설정 파일",
  game: "게임·런처",
};

/**
 * What else the game needs that this plugin cannot put in.
 *
 * Some games are on the list as working only with a mod OptiScaler hooks into,
 * a file copied into the folder, Engine.ini lines or an anti-cheat switched
 * off. An install that skips that loads OptiScaler and changes nothing on
 * screen, so it is said here, above the steps, with the wiki's own words and
 * where to get it — not left in prose behind "Manual setup".
 */
function RequirementsSection({ plan }: Readonly<{ plan: AutoPlan | null }>) {
  const items = plan?.requirements ?? [];
  if (items.length === 0) return null;
  const firm = items.filter((item) => item.required);
  return (
    <PanelSection title="OptiScaler 말고 필요한 것">
      <PanelSectionRow>
        <Notice tone={firm.length ? "warn" : "info"}>
          {firm.length
            ? "위키에 따르면 이 게임은 아래 항목이 있어야 OptiScaler가 동작합니다. 이 플러그인이 설치할 수 없으니 직접 준비하세요."
            : "위키가 이 게임에 아래 항목을 권합니다. 이 플러그인이 설치할 수 없으니 필요하면 직접 준비하세요."}
        </Notice>
      </PanelSectionRow>
      {items.map((item) => (
        <PanelSectionRow key={item.key}>
          <Field
            label={
              <span>
                {item.name}{" "}
                <span style={{ fontSize: "11px", opacity: 0.6 }}>{REQUIREMENT_KIND[item.kind]}</span>
              </span>
            }
            description={
              <>
                {item.detail}
                {item.link ? (
                  <div style={{ marginTop: "4px" }}>
                    <Mono>{item.link}</Mono>
                  </div>
                ) : null}
              </>
            }
            focusable
            bottomSeparator="standard"
            childrenLayout="inline"
            childrenContainerWidth="min"
            {...({ "data-requirement": item.key } as Record<string, string>)}
          >
            {item.required ? <Pill color="#8a3f6a">필수</Pill> : <Pill>권장</Pill>}
          </Field>
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}

function HotkeyNote({ plan }: Readonly<{ plan: AutoPlan }>) {
  const hotkey = plan.hotkey;
  if (!hotkey) return null;
  // Moved by the wiki entry itself, or by this plugin because REFramework
  // goes in too and the entry only said to move REF's.
  const ours = hotkey.source.startsWith("REFramework");
  const key = hotkey.name ?? hotkey.value;
  return (
    <PanelSectionRow>
      <Notice tone="info" title="오버레이가 다른 키로 열립니다">
        {plan.reframework ? "REFramework 오버레이도 Insert 키를 쓰므로 " : ""}
        {ours ? "OptiScaler 오버레이 키를 " : "이 항목은 OptiScaler 오버레이 키를 "}
        <Mono>{key}</Mono> 키로 옮깁니다. 게임에서 OptiScaler는 <Mono>{key}</Mono>,
        {plan.reframework ? " REFramework는 Insert로 엽니다." : " 키로 엽니다."} 스팀덱에서는
        Steam 입력 설정에서 뒷버튼 하나를 <Mono>{key}</Mono> 키에 지정하세요.
      </Notice>
    </PanelSectionRow>
  );
}

/**
 * FSR 4 Lite, as the folder has it now.
 *
 * Every install writes the preset, so this is not a step to take but a state
 * to check: OptiScaler's overlay saves its own values over the ini when
 * somebody presses Save there. The row says which, and puts it back.
 */
function Fsr4LiteStep({
  detail,
  busy,
  onApply,
}: Readonly<{ detail: GameDetail; busy: boolean; onApply: () => void }>) {
  const fsr4 = detail.install.fsr4;
  const ready = Boolean(fsr4?.ready);
  const name = upscalerLabel(detail.install.upscaler);
  const hlx = detail.install.engine === "helixsr";
  const changed = (fsr4?.preset?.keys ?? []).filter((key) => !key.ok);
  const description = ready
    ? hlx
      ? `HelixSR Scaler가 게임의 DLSS를 HLX DLSS로 돌립니다. 게임 설정에서 DLSS를 고르세요. 다른
          업스케일러는 플레이 중 오버레이(Insert)에서 고를 수 있습니다.`
      : isCustom(detail.install.upscaler)
        ? `${name}를 OptiScaler의 FidelityFX 업스케일러 자리에 넣어 DX12·DX11·Vulkan 게임 모두에서
            씁니다. AMD의 FSR 4와 다른 빌드는 custom 업스케일러로 함께 들어 있어 오버레이(Insert)에서
            바꿔 가며 쓸 수 있습니다.`
        : `AMD FSR 4의 INT8 Lite${
            fsr4?.ffx?.version ? `, FidelityFX ${fsr4.ffx.version}` : ""
          }. 모델 등 다른 설정은 플레이 중 OptiScaler 오버레이(Insert)에서 바꿀 수 있습니다.`
    : `ini의 ${changed
        .map((key) => `${key.key}=${key.wanted}`)
        .join(", ")} 값이 바뀌었습니다. 오버레이에서 덮어썼을 수 있습니다. 선택하면 프리셋을 다시 적용합니다.`;
  return (
    <PanelSectionRow>
      <Field
        label={
          <StepLabel done={ready}>{ready ? `${name} 켜짐` : `${name} 꺼짐`}</StepLabel>
        }
        description={description}
        onClick={busy ? undefined : onApply}
        onActivate={busy ? undefined : onApply}
        focusable
        bottomSeparator="standard"
        childrenLayout="inline"
        childrenContainerWidth="min"
      >
        {ready ? <Pill color="#2f6b3f">준비됨</Pill> : <Pill color="#5a4a20">다시 적용</Pill>}
      </Field>
    </PanelSectionRow>
  );
}

export function SetupChecklist({
  detail,
  appid,
  plan,
  recommendation,
  loadingWiki,
  refreshing,
  auto,
  running,
  upscaler,
  blocked,
  newestTag,
  onSetAuto,
  onManual,
  onLogs,
  onChanged,
  onReloadPlan,
  onResetConfig,
}: Readonly<Props>) {
  const installed = Boolean(detail.install.installed);
  /** HelixSR Scaler rather than the nightly: it brings its own OptiPatcher. */
  const hlx = upscaler === "hlx-dlss";
  const name = upscalerLabel(upscaler);
  const engineName = hlx ? "HelixSR Scaler" : "OptiScaler";
  const planned = plan?.available ? plan : null;
  const filename = detail.install.filename ?? planned?.filename ?? "dxgi.dll";
  // An .asi build is loaded by an ASI loader, so Proton has nothing to shadow
  // and there is no override to set.
  const needsOverride = !filename.toLowerCase().endsWith(".asi");

  const [withLaunch, setWithLaunch] = useState(true);
  const [withSettings, setWithSettings] = useState(true);
  // On when the wiki's OptiPatcher column says so; only offered then.
  const [withPatcher, setWithPatcher] = useState(true);
  const patcher = Boolean(planned?.optipatcher) && withPatcher && !hlx;
  const [busy, setBusy] = useState(false);
  /** Steam's current launch options, or null when the client will not say. */
  const [launchNow, setLaunchNow] = useState<string | null>(null);
  const [launchReadable, setLaunchReadable] = useState(false);
  const [report, setReport] = useState<MonitorReport | null>(null);

  const refreshLaunch = useCallback(async () => {
    if (!appid) {
      setLaunchReadable(false);
      return;
    }
    const value = await currentLaunchOptions(appid);
    setLaunchNow(value);
    setLaunchReadable(value !== null);
  }, [appid]);

  useEffect(() => {
    void refreshLaunch();
  }, [refreshLaunch]);

  useEffect(() => {
    if (!installed) return;
    void (async () => {
      try {
        setReport(await getMonitor(detail.install.path));
      } catch {
        /* the log is optional; the row falls back to what it knows */
      }
    })();
  }, [installed, detail.install.path]);

  /**
   * REFramework, when this game's entry says OptiScaler does nothing without it.
   *
   * Taken from the plan before the install and from the folder after it, which
   * are answers to two different questions: what this game needs, and what it
   * has. The second is read from the folder rather than from our own manifest
   * on purpose — somebody's existing working copy of REF counts, and
   * re-installing over it would be a worse answer than leaving it alone.
   */
  const ref = planned?.reframework ?? null;
  const refPresent = detail.reframework?.installed ?? detail.install.reframework?.installed
    ?? false;
  const pluginPresent = detail.reframework?.plugin_installed ?? false;

  /**
   * Both overrides, not just OptiScaler's.
   *
   * REFramework needs its own `WINEDLLOVERRIDES` entry for exactly the reason
   * OptiScaler's proxy does: Proton ships a dinput8 of its own and loads that
   * in preference to the game folder. The wiki never mentions it — it is
   * written for Windows, where the folder wins — so a set-up that followed the
   * entry to the letter would put REF in place and never load it.
   */
  const refStems = ref ? [ref.override] : [];
  /**
   * What Steam is to pass: whatever it passes now, with our overrides and the
   * entry's arguments put in, never in place of it. A `mangohud` or a
   * `PROTON_` variable of the user's stays where it was.
   */
  const launchWanted = mergeLaunchOptions(
    launchNow,
    [...(needsOverride ? [overrideStem(filename)] : []), ...refStems],
    planned?.launch_flags ?? [],
  );

  const overrideSet =
    launchNow !== null &&
    hasOverride(launchNow, filename) &&
    (!ref || hasOverride(launchNow, ref.override));

  /**
   * Whether this answer may still improve on its own.
   *
   * The compatibility-list row answers first and this game's own wiki page
   * arrives behind it — and the page is what names the filename to install as,
   * so acting in that window would install under the default name when the
   * entry says otherwise. Both halves matter: a page that is *pending* but no
   * longer being fetched is one the wiki would not serve, and waiting on that
   * is waiting for ever.
   */
  const settling = Boolean(recommendation?.detail_pending) && Boolean(refreshing);

  const applyLaunchOptions = async (value: string) => {
    if (!appid) return;
    // Before writing our own override, keep whatever Steam is passing now: this
    // is the last moment it is still the game's own answer rather than ours.
    // Write-once in the backend, so the install's record wins if there is one.
    if (value && installed) await recordPreviousLaunchOptions(appid, detail.install.path);
    if (setLaunchOptions(Number(appid), value)) {
      // Shown from what was written rather than read back: Steam flushes its
      // config file on its own schedule, so a read landing in that window
      // reports the old value and the row appears not to have taken.
      setLaunchNow(value);
      setLaunchReadable(true);
      void refreshLaunch();
      toaster.toast({
        title: value ? "실행 옵션을 설정했습니다" : "실행 옵션을 지웠습니다",
        body: value || detail.name,
      });
    } else {
      toaster.toast({
        title: "Steam에 연결할 수 없습니다",
        body: "실행 옵션을 직접 설정하세요.",
      });
    }
  };

  /** Step 1, plus whichever of steps 2 and 3 are switched on. */
  const run = async () => {
    if (!planned) return;
    setBusy(true);
    try {
      const folder = detail.path.split("/").filter(Boolean).pop() ?? detail.name;
      let missed: string | null = null;
      let lastResult: unknown = null;
      if (withSettings) {
        const result = await autoInstall(
          detail.target,
          detail.path,
          detail.name,
          [folder],
          patcher,
          upscaler
        );
        if (!result.ok) {
          toaster.toast({ title: "설치를 완료하지 못했습니다", body: String(result.error) });
          return;
        }
        missed = optipatcherMissed(result);
        lastResult = result;
      } else {
        const result = await install(detail.target, planned.filename, false, patcher, upscaler);
        if (!result.ok) {
          toaster.toast({ title: "설치하지 못했습니다", body: String(result.error) });
          return;
        }
        missed = optipatcherMissed(result);
        lastResult = result;
        // REFramework is not one of the wiki's *settings*, so switching those
        // off must not switch it off with them: it is the reason OptiScaler
        // can hook this game at all, and an install without it is one that
        // loads, reports nothing wrong and changes nothing on screen. The
        // automatic path above places it as part of the plan; this one has to
        // ask for it separately.
        if (ref?.automatic) {
          const added = await installReframework(detail.target, detail.path, detail.name, [folder]);
          if (!added.ok) {
            toaster.toast({
              title: "OptiScaler는 설치했지만 REFramework는 설치하지 못했습니다",
              body: String(added.error),
            });
          }
        }
        await setGameTarget(detail.path, detail.target);
        // Nothing is following the wiki, so every option stays the user's.
        await setAutoMode(detail.path, false);
      }
      if (withLaunch && appid && needsOverride) {
        await recordPreviousLaunchOptions(appid, detail.target);
        // Read again rather than taken from the page: an install can take
        // minutes, and the field is the user's to change meanwhile.
        const current = await currentLaunchOptions(appid);
        setLaunchOptions(
          Number(appid),
          mergeLaunchOptions(current, [overrideStem(planned.filename), ...refStems],
                             planned.launch_flags),
        );
      }
      const left = customMissed(lastResult);
      toaster.toast(
        missed
          ? { title: `${detail.name}: OptiPatcher 없이 설치했습니다`, body: missed }
          : left
            ? { title: `${detail.name}: 일부 custom 업스케일러 없이 설치했습니다`, body: left }
          : {
              title: `${detail.name} 설치를 마쳤습니다`,
              body: `${name} · ${engineName}를 ${planned.filename} 파일로 설치했습니다.`,
            }
      );
      await onChanged();
      await onReloadPlan();
      await refreshLaunch();
    } finally {
      setBusy(false);
    }
  };

  /**
   * Add REFramework on its own, for a game already set up or a download that
   * failed the first time.
   *
   * Its own action rather than "install everything again" because a 13 MB
   * download over a handheld's connection is the part that fails, and making
   * somebody reinstall OptiScaler to retry it is a poor answer to a flaky
   * network.
   */
  const addReframework = async () => {
    setBusy(true);
    try {
      const folder = detail.path.split("/").filter(Boolean).pop() ?? detail.name;
      const result = await installReframework(detail.target, detail.path, detail.name, [folder]);
      if (result.ok) {
        toaster.toast({ title: "REFramework를 설치했습니다", body: detail.name });
        await onChanged();
      } else {
        toaster.toast({ title: "REFramework를 설치할 수 없습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  /** Look for PDPerfPlugin.dll again, after the user has put it in Downloads. */
  const recheckPlugin = async () => {
    setBusy(true);
    try {
      await onReloadPlan();
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  /** PDPerfPlugin.dll into a game set up before the user had supplied it. */
  const addPlugin = async () => {
    setBusy(true);
    try {
      const result = await installPdPlugin(detail.install.path ?? detail.target);
      if (result.ok) {
        toaster.toast({ title: "PDPerfPlugin.dll을 넣었습니다", body: detail.name });
        await onChanged();
      } else {
        toaster.toast({ title: "PDPerfPlugin.dll을 넣을 수 없습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  /**
   * Take REFramework back out, leaving OptiScaler where it is.
   *
   * The isolation test. REFramework is a third-party DLL that hooks the engine,
   * and when a game stops booting after a set-up there is no way to learn
   * whether that was OptiScaler or REF unless one of them can come out on its
   * own. Making the install all-or-nothing left exactly that: a game that would
   * not start and nothing to bisect it with.
   */
  const dropReframework = async () => {
    setBusy(true);
    try {
      const result = await removeReframework(detail.install.path);
      if (result.ok) {
        toaster.toast({
          title: "REFramework를 제거했습니다",
          body: "OptiScaler는 그대로 설치되어 있습니다. 게임을 실행해 어느 쪽이 원인이었는지 확인하세요.",
        });
        await onChanged();
      } else {
        toaster.toast({ title: "REFramework를 제거할 수 없습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  /** Download the list again and rebuild this game's plan from it. */
  const retryWiki = async () => {
    setBusy(true);
    try {
      const result = await refreshWiki();
      await onReloadPlan();
      toaster.toast({
        title: result.count > 0 ? "호환성 목록을 다운로드했습니다" : "여전히 다운로드할 수 없습니다",
        body: result.count > 0
          ? `항목 ${result.count}개.`
          : String(result.meta?.error ?? "위키에 연결할 수 없습니다."),
      });
    } catch (exc) {
      toaster.toast({ title: "여전히 다운로드할 수 없습니다", body: String(exc) });
    } finally {
      setBusy(false);
    }
  };

  const reapply = async () => {
    if (!planned) return;
    setBusy(true);
    try {
      const folder = detail.path.split("/").filter(Boolean).pop() ?? detail.name;
      const result = await autoInstall(
        detail.target,
        detail.path,
        detail.name,
        [folder],
        undefined,
        detail.install.upscaler ?? undefined
      );
      if (result.ok) {
        toaster.toast({ title: "위키 기준으로 다시 설치했습니다", body: planned.game ?? detail.name });
        await onChanged();
        await onReloadPlan();
      } else {
        toaster.toast({ title: "다시 적용할 수 없습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  /**
   * What Steam is passing now, and what it was passing before the install.
   *
   * The pair is what makes the removal question answerable: with a record,
   * "put it back" is exact and "there were none" is a fact rather than a
   * guess; without one, only the override this plugin recognises comes out.
   */
  const launchState: LaunchState = {
    current: launchNow,
    recorded: recordedValue(detail.install.launch_record),
    // REFramework of ours goes with OptiScaler, so its override does too.
    extraStems: detail.install.reframework?.managed ? (ref ? [ref.override] : ["dinput8"]) : [],
    filename: detail.install.filename ?? filename,
  };

  const doUninstall = async (action: LaunchAction, rememberIt: boolean) => {
    setBusy(true);
    try {
      if (rememberIt) await remember(PREF_REMOVE_LAUNCH, action);
      const result = await uninstall(detail.install.path, true);
      if (result.ok) {
        toaster.toast({ title: "OptiScaler를 제거했습니다", body: detail.name });
        const chosen = launchChoices(launchState).find((choice) => choice.action === action);
        if (appid && chosen && chosen.value !== null) {
          const wrote = setLaunchOptions(Number(appid), chosen.value);
          toaster.toast({
            title: wrote
              ? chosen.value === ""
                ? "실행 옵션을 지웠습니다"
                : "실행 옵션을 복원했습니다"
              : "Steam에 연결할 수 없습니다",
            body: wrote ? chosen.value || detail.name : "실행 옵션을 직접 변경하세요.",
          });
          if (wrote) {
            setLaunchNow(chosen.value);
            setLaunchReadable(true);
          }
        }
        await onChanged();
        await refreshLaunch();
      } else {
        toaster.toast({ title: "제거하지 못했습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  const confirmUninstall = async () => {
    // Both reads happen before the modal opens: it is a plain render of an
    // answer already known, so nothing on it can arrive after the user has
    // looked at it and moved on.
    const [rememberedAction, canRemember] = await Promise.all([
      recallLaunchAction(PREF_REMOVE_LAUNCH),
      isRemembering(),
    ]);
    // A remembered answer is only honoured while it still applies to this game:
    // "put back what was there" means nothing for a game with no record, and a
    // game Steam does not own has no choices at all.
    const choices = appid ? launchChoices(launchState) : [];
    const applicable =
      resolveChoice(choices, rememberedAction)?.action === rememberedAction
        ? rememberedAction
        : null;
    showModal(
      <RemovePrompt
        gameName={detail.name}
        filename={detail.install.filename}
        backedUp={detail.install.backed_up.length}
        launch={appid ? launchState : null}
        remembered={applicable}
        canRemember={canRemember}
        onConfirm={(action, rememberIt) => void doUninstall(action, rememberIt)}
      />
    );
  };

  /**
   * Reinstall over the game's own install with the upscaler picked above:
   * the nightly and HelixSR Scaler swap places, the preset changes, and the
   * filename, the ini and the launch options stay as they are.
   */
  const switchUpscaler = async () => {
    setBusy(true);
    try {
      const result = await install(
        detail.install.path,
        detail.install.filename ?? filename,
        true,
        Boolean(planned?.optipatcher) && !hlx,
        upscaler
      );
      if (result.ok) {
        toaster.toast({ title: `${name}로 바꿨습니다`, body: `${detail.name} · ${engineName}` });
        await onChanged();
      } else {
        toaster.toast({ title: `${name}로 바꾸지 못했습니다`, body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  const doReset = async () => {
    setBusy(true);
    try {
      const result = await resetConfig(detail.install.path);
      if (result.ok) {
        await onResetConfig();
        toaster.toast({
          title: "설정을 초기화했습니다",
          body: `기본 OptiScaler.ini를 ${upscalerLabel(detail.install.upscaler)} 설정과 함께 복원했습니다.`,
        });
      } else {
        toaster.toast({ title: "초기화하지 못했습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  const applyPreset = async () => {
    setBusy(true);
    try {
      const result = await applyFsr4Preset(detail.install.path);
      if (result.ok) {
        toaster.toast({
          title: `${upscalerLabel(detail.install.upscaler)} 설정을 다시 적용했습니다`,
          body: "다음 실행부터 적용됩니다.",
        });
        await onChanged();
      } else {
        toaster.toast({ title: "설정을 다시 적용할 수 없습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  // -- what the log row has to say -----------------------------------------
  const problems = report?.problems?.length ?? 0;
  const logSummary = !report?.log_present
    ? "아직 로그가 없습니다. 여기서 로그를 켜고 게임을 한 번 실행하세요."
    : problems > 0
      ? `로그에 경고 또는 오류가 ${problems}개 있습니다.`
      : "로그에 문제가 없습니다.";
  const logPill = !report?.log_present ? (
    <Pill>로그 없음</Pill>
  ) : problems > 0 ? (
    <Pill color="#5a4a20">{problems}</Pill>
  ) : (
    <Pill color="#2f6b3f">문제 없음</Pill>
  );

  const foldRows = (
    <PanelSection>
      <PanelSectionRow>
        <Field
          label="수동 설치"
          description="파일 이름, 폴더, OptiPatcher, 실행 옵션."
          onClick={onManual}
          onActivate={onManual}
          focusable
          bottomSeparator="standard"
          childrenLayout="inline"
          childrenContainerWidth="min"
        >
          <span style={{ opacity: 0.5 }}>›</span>
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field
          label="로그"
          // What the log says once there is one: that sentence used to be on
          // the "Not running" row, which was never a step of setting a game up.
          description={
            installed
              ? logSummary
              : "OptiScaler가 로드한 항목, 찾은 GPU, 오류."
          }
          onClick={onLogs}
          onActivate={onLogs}
          focusable
          bottomSeparator="standard"
          childrenLayout="inline"
          childrenContainerWidth="min"
        >
          {installed ? logPill : <Pill>로그 없음</Pill>}
        </Field>
      </PanelSectionRow>
    </PanelSection>
  );

  // -- not set up yet -------------------------------------------------------
  if (!installed) {
    // REFramework, when this game needs it, goes first: it is what OptiScaler
    // hooks into, so it is the step everything below depends on. It is not
    // offered as a toggle the way the launch options and the wiki's settings
    // are — those are choices, and "install OptiScaler in a configuration that
    // cannot work" is not one.
    const refStep = ref && ref.automatic ? 1 : 0;
    const steps = refStep + 1 +
      (patcher ? 1 : 0) +
      (planned && needsOverride && appid && withLaunch ? 1 : 0) +
      (planned && withSettings ? 1 : 0);
    /** Step numbers, so inserting one above does not renumber by hand. */
    let step = 0;
    const next = () => (step += 1);
    const runLabel = busy
      ? "설치 중…"
      : settling
        ? "이 게임 항목 읽는 중…"
        : steps >= 2
          ? `${steps}단계 모두 실행`
          : "설치만 하기";

    return (
      <>
        <PanelSection title={detail.name}>
          <PanelSectionRow>
            {loadingWiki ? (
              <Notice tone="info">OptiScaler 위키 확인 중…</Notice>
            ) : planned ? (
              <Notice tone="success" title="이 게임은 자동 설치할 수 있습니다">
                OptiScaler 위키의 “{planned.game}” 항목과 일치합니다
                {recommendation?.compatibility
                  ? ` — 보고 상태: ${recommendation.compatibility}`
                  : ""}
                .
                {/* The list row answers on its own; this game's own wiki page
                    is being fetched behind it and fills the rest in. Said out
                    loud because the steps below can change when it lands —
                    but only while it is actually still being fetched. A page
                    the wiki will not serve stays pending for ever, and saying
                    "still reading" about it for ever is a lie the user cannot
                    act on. */}
                {settling
                  ? " 이 게임의 항목을 아직 읽는 중입니다. 아래 단계가 곧 채워질 수 있습니다."
                  : ""}
              </Notice>
            ) : (
              <WikiTrouble
                recommendation={recommendation}
                busy={busy}
                onRetry={() => void retryWiki()}
              />
            )}
          </PanelSectionRow>
          {!planned && !loadingWiki ? (
            <PanelSectionRow>
              <Focusable style={{ display: "flex" }}>
                <DialogButton
                  onClick={onManual}
                  onOKActionDescription="이 게임 수동 설치"
                  style={{ flexGrow: 1 }}
                >
                  수동 설치
                </DialogButton>
              </Focusable>
            </PanelSectionRow>
          ) : null}
        </PanelSection>

        <RequirementsSection plan={planned} />

        {planned ? (
          <PanelSection>
            {ref ? (
              <PanelSectionRow>
                <Field
                  label={
                    <StepLabel n={ref.automatic ? next() : undefined} done={refPresent}>
                      {refPresent ? "REFramework 이미 있음" : "REFramework 설치"}
                    </StepLabel>
                  }
                  description={
                    refPresent
                      ? `${detail.reframework?.dll ?? ref.dll} 파일이 이미 실행 파일 옆에 있습니다.
                         이 항목이 요구하는 빌드로 교체하고, 기존 파일은 따로 보관합니다.`
                      : `이것이 없으면 OptiScaler가 이 게임에 후킹할 수 없습니다(위키
                         “${ref.source}” 참고). ${reframeworkSummary(ref)}`
                  }
                  bottomSeparator="standard"
                  childrenLayout="inline"
                  childrenContainerWidth="min"
                  focusable
                >
                  {ref.automatic ? (
                    <span style={{ fontSize: "11px", opacity: 0.5 }}>필수</span>
                  ) : (
                    <Pill color="#5a4a20">직접</Pill>
                  )}
                </Field>
              </PanelSectionRow>
            ) : null}

            {ref ? (
              <PluginStep
                wanted={ref}
                present={pluginPresent}
                installed={false}
                busy={busy}
                onRecheck={() => void recheckPlugin()}
                onInstall={() => void addPlugin()}
              />
            ) : null}

            <PanelSectionRow>
              <Field
                label={
                  <StepLabel n={next()}>
                    {engineName}를 <Mono>{planned.filename}</Mono> 파일로 설치
                  </StepLabel>
                }
                description={
                  hlx
                    ? `HelixSR Desktop이 이 기기에서 빌드한 HelixSR Scaler를 ${name}를 켠 상태로
                      ${shorten(detail.target)}에 설치합니다. 게임을 렌더링하는 실행 파일이 있는
                      곳입니다. HelixSR Scaler에 들어 있는 OptiPatcher도 그대로 함께 켜집니다.`
                    : isCustom(upscaler)
                      ? `OptiScaler nightly를 ${shorten(detail.target)}에 설치하고, ${name}를 내려받아
                        OptiScaler의 FidelityFX 업스케일러 자리에 넣습니다. DX12·DX11·Vulkan 게임
                        모두 이 빌드를 씁니다. AMD의 FSR 4와 다른 빌드는 custom 업스케일러로 함께
                        넣어 오버레이(Insert)에서 바꿔 쓸 수 있습니다. 게임을 렌더링하는 실행 파일이
                        있는 곳입니다.`
                      : `OptiScaler nightly를 FSR 4 Lite로 ${shorten(detail.target)}에 설치합니다.
                        cyboman의 FSR 4.1.2 Lite exact·lossy와 HLX FSR 4도 내려받아 custom
                        업스케일러로 함께 넣어, 플레이 중 오버레이(Insert)에서 바꿔 쓸 수 있습니다.
                        게임을 렌더링하는 실행 파일이 있는 곳입니다.`
                }
                bottomSeparator="standard"
                childrenLayout="inline"
                childrenContainerWidth="min"
              >
                <span style={{ fontSize: "11px", opacity: 0.5 }}>필수</span>
              </Field>
            </PanelSectionRow>

            {/* Only where the wiki's OptiPatcher column lists the game: a
                patcher with no pattern for it does nothing there. */}
            {planned.optipatcher && !hlx ? (
              <PanelSectionRow>
                <ToggleField
                  label={
                    <StepLabel n={withPatcher ? next() : undefined}>
                      OptiPatcher 함께 설치 — 위키 권장
                    </StepLabel>
                  }
                  description={OPTIPATCHER_WHY}
                  checked={withPatcher}
                  disabled={busy}
                  bottomSeparator="standard"
                  onChange={setWithPatcher}
                />
              </PanelSectionRow>
            ) : null}

            {needsOverride && appid ? (
              <PanelSectionRow>
                <ToggleField
                  label={<StepLabel n={next()}>Steam 실행 옵션 설정</StepLabel>}
                  description={
                    ref
                      ? `${launchWanted} — 없으면 Proton이 자체 ${planned.filename} 및
                         ${ref.dll} 파일을 로드해 두 모드 모두 작동하지 않습니다. 지금 있는 실행
                         옵션은 그대로 두고 필요한 값만 더합니다.`
                      : `${launchWanted} — 없으면 Proton이 자체 ${planned.filename} 파일을
                         로드합니다. 지금 있는 실행 옵션은 그대로 두고 필요한 값만 더합니다.`
                  }
                  checked={withLaunch}
                  disabled={busy}
                  bottomSeparator="standard"
                  onChange={setWithLaunch}
                />
              </PanelSectionRow>
            ) : null}

            {!appid && needsOverride ? (
              <PanelSectionRow>
                <Notice tone="warn" title="실행 옵션을 직접 설정하세요">
                  이 게임은 Steam이 아닌 사용자 지정 폴더에서 추가되어 여기서 설정할 수 없습니다.
                  게임을 시작하는 런처에 <Mono>{planned.launch_options}</Mono>를 추가하세요.
                </Notice>
              </PanelSectionRow>
            ) : null}

            <PanelSectionRow>
              <ToggleField
                label={
                  <StepLabel n={next()}>
                    {planned.settings.length > 0
                      ? `항목이 요구하는 설정 ${planned.settings.length}개 적용`
                      : "이 게임의 위키 항목 따르기"}
                  </StepLabel>
                }
                description={
                  settingsSummary(planned) ||
                  "이 항목은 특별한 설정이 필요 없지만, 켜 두면 이후 위키 변경 사항이 이 게임에 반영됩니다."
                }
                checked={withSettings}
                disabled={busy}
                bottomSeparator="standard"
                onChange={setWithSettings}
              />
            </PanelSectionRow>

            {planned && withSettings ? <HotkeyNote plan={planned} /> : null}

            {!detail.writable ? (
              <PanelSectionRow>
                <Notice tone="error" title="폴더에 쓸 수 없습니다">
                  <Mono>{shorten(detail.target)}</Mono>
                </Notice>
              </PanelSectionRow>
            ) : null}

            {blocked ? (
              <PanelSectionRow>
                <Notice tone="warn" title={`${name}를 지금은 설치할 수 없습니다`}>
                  {blocked}
                </Notice>
              </PanelSectionRow>
            ) : null}

            <PanelSectionRow>
              <Focusable style={{ display: "flex" }}>
                <DialogButton
                  disabled={busy || settling || !detail.writable || Boolean(blocked)}
                  onClick={() => void run()}
                  onOKActionDescription="이 게임 설치"
                  style={{ flexGrow: 1 }}
                >
                  {runLabel}
                </DialogButton>
              </Focusable>
            </PanelSectionRow>
          </PanelSection>
        ) : null}

        {foldRows}

        <PanelSection>
          <PanelSectionRow>
            <Focusable
              focusWithinClassName="gpfocuswithin"
              style={{ fontSize: "12px", opacity: 0.6, padding: "4px 0", lineHeight: 1.45 }}
            >
              잃는 파일은 없습니다. OptiScaler가 교체하는 파일은 따로 보관했다가 제거할 때
              복원합니다.
            </Focusable>
          </PanelSectionRow>
        </PanelSection>
      </>
    );
  }

  // -- already set up -------------------------------------------------------
  const backedUp = detail.install.backed_up.length;
  return (
    <>
      <PanelSection title={detail.name}>
        <PanelSectionRow>
          <Field
            label={<StepLabel done><Mono>{detail.install.filename}</Mono> 파일로 설치됨</StepLabel>}
            description={[
              detail.install.engine === "helixsr"
                ? `HelixSR Scaler ${detail.install.version ?? "?"} (${(detail.install.tag ?? "").replace("helixsr-", "HelixSR ")})`
                : detail.install.version
                  ? `OptiScaler ${detail.install.version}${detail.install.tag ? ` (${detail.install.tag})` : ""}`
                  : "알 수 없는 빌드",
              // A game keeps its build until it is installed again, so say when
              // a newer one is already here: the nightly downloaded, or a newer
              // HelixSR build from HelixSR Desktop.
              detail.install.tag && newestTag && detail.install.tag !== newestTag
                ? `${newestTag} 있음 — 다시 설치하면 업데이트됩니다`
                : null,
              backedUp > 0 ? `파일 ${backedUp}개 따로 보관` : null,
              detail.install.managed ? "이 플러그인이 관리" : "외부에서 설치됨",
            ]
              .filter(Boolean)
              .join(" · ")}
            onClick={onManual}
            onActivate={onManual}
            focusable
            bottomSeparator="standard"
            childrenLayout="inline"
            childrenContainerWidth="min"
          >
            <Pill>변경</Pill>
          </Field>
        </PanelSectionRow>

        {detail.install.managed && (detail.install.upscaler ?? "fsr4-lite") !== upscaler ? (
          <PanelSectionRow>
            <Field
              label={<StepLabel>{name}로 바꾸기</StepLabel>}
              description={
                blocked ??
                `지금은 ${upscalerLabel(detail.install.upscaler)}입니다. ${engineName}로 다시 설치하고 ${name}
                 설정을 적용합니다. 파일 이름, 실행 옵션, 다른 설정은 그대로 둡니다.`
              }
              onClick={busy || blocked ? undefined : () => void switchUpscaler()}
              onActivate={busy || blocked ? undefined : () => void switchUpscaler()}
              focusable
              bottomSeparator="standard"
              childrenLayout="inline"
              childrenContainerWidth="min"
            >
              <Pill color={blocked ? undefined : "#3a6ea5"}>{blocked ? "불가" : "바꾸기"}</Pill>
            </Field>
          </PanelSectionRow>
        ) : null}

        {detail.install.managed ? (
          <Fsr4LiteStep detail={detail} busy={busy} onApply={() => void applyPreset()} />
        ) : null}

        {needsOverride && appid ? (
          launchReadable ? (
            <PanelSectionRow>
              <ToggleField
                label={
                  <StepLabel done={overrideSet}>
                    {overrideSet ? "실행 옵션 설정됨" : "실행 옵션 설정 안 됨"}
                  </StepLabel>
                }
                description={
                  overrideSet
                    ? launchNow ?? launchWanted
                    : `${launchWanted} 없이는 Proton이 자체 ${detail.install.filename} 파일을 로드합니다.`
                }
                checked={overrideSet}
                disabled={busy}
                bottomSeparator="standard"
                onChange={(checked) =>
                  void applyLaunchOptions(
                    checked ? launchWanted : stripOverride(launchNow ?? "", filename, refStems)
                  )
                }
              />
            </PanelSectionRow>
          ) : (
            <PanelSectionRow>
              <Field
                label={<StepLabel>Steam 실행 옵션</StepLabel>}
                description={`Steam이 이 게임의 실행 옵션을 알려 주지 않아 여기서 확인할 수
                  없습니다. 다시 설정해도 문제없습니다.`}
                onClick={() => void applyLaunchOptions(launchWanted)}
                onActivate={() => void applyLaunchOptions(launchWanted)}
                focusable
                bottomSeparator="standard"
                childrenLayout="inline"
                childrenContainerWidth="min"
              >
                <Pill>설정</Pill>
              </Field>
            </PanelSectionRow>
          )
        ) : null}

        {/* Only for the games whose entry asks for it. For everything else
            there is no such thing as REFramework being missing, and a row
            saying so would be a permanent unticked step on every game in the
            library. */}
        {ref ? (
          <>
            {/* A toggle rather than a tick, and this is the one place the
                "not a choice" reasoning was wrong. REFramework is required for
                the game to work — but it is also a third-party DLL that can
                stop the game booting, and when that happens the only way to
                find out which of the two mods did it is to remove one. An
                install with no way to bisect it is a bug report nobody can
                answer. */}
            {ref.automatic || refPresent ? (
              <PanelSectionRow>
                <ToggleField
                  label={
                    <StepLabel done={refPresent}>
                      {refPresent ? "REFramework 설치됨" : "REFramework 없음"}
                    </StepLabel>
                  }
                  description={
                    refPresent
                      ? [
                          detail.reframework?.revision
                            ? `빌드 ${detail.reframework.revision.slice(0, 12)}`
                            : ref.variant === "pd-upscaler"
                              ? "pd-upscaler 빌드"
                              : "nightly 빌드",
                          detail.install.reframework?.managed
                            ? "이 플러그인이 설치함"
                            : "폴더에 이미 있었음",
                          "게임이 실행되지 않으면 끄세요",
                        ].join(" · ")
                      : `이것이 없으면 OptiScaler가 로드되어도 화면에 아무 변화가 없습니다(이 게임
                         항목의 “${ref.source}” 참고). ${reframeworkSummary(ref)}`
                  }
                  checked={refPresent}
                  disabled={busy}
                  bottomSeparator="standard"
                  onChange={(checked) =>
                    void (checked ? addReframework() : dropReframework())}
                />
              </PanelSectionRow>
            ) : (
              <PanelSectionRow>
                <Field
                  label={<StepLabel done={refPresent}>REFramework 없음</StepLabel>}
                  description={`이것이 없으면 OptiScaler가 로드되어도 화면에 아무 변화가 없습니다(이
                    게임 항목의 “${ref.source}” 참고). ${reframeworkSummary(ref)}`}
                  focusable
                  bottomSeparator="standard"
                  childrenLayout="inline"
                  childrenContainerWidth="min"
                >
                  <Pill color="#5a4a20">직접</Pill>
                </Field>
              </PanelSectionRow>
            )}
            <PluginStep
              wanted={ref}
              present={pluginPresent}
              installed
              busy={busy}
              onRecheck={() => void recheckPlugin()}
              onInstall={() => void addPlugin()}
            />
          </>
        ) : null}

        {planned && auto ? <HotkeyNote plan={planned} /> : null}

        {!planned && !loadingWiki ? (
          recommendation && !recommendation.list_available ? (
            // Same distinction as before the install: a list that would not
            // download is a fault, not a verdict on this game.
            <PanelSectionRow>
              <WikiTrouble
                recommendation={recommendation}
                busy={busy}
                onRetry={() => void retryWiki()}
              />
            </PanelSectionRow>
          ) : (
            <PanelSectionRow>
              <Field
                label={<StepLabel>일치하는 위키 항목 없음</StepLabel>}
                description="자동으로 최신 상태로 유지되는 설정이 없습니다. “수동 설치”에서 항목을 직접 고르거나 설정을 직접 관리하세요."
                onClick={onManual}
                onActivate={onManual}
                focusable
                bottomSeparator="standard"
                childrenLayout="inline"
                childrenContainerWidth="min"
              >
                <span style={{ opacity: 0.5 }}>›</span>
              </Field>
            </PanelSectionRow>
          )
        ) : null}

        {planned ? (
          <PanelSectionRow>
            <ToggleField
              label={
                <StepLabel done={auto}>
                  {auto ? "위키 항목 따르는 중" : "위키 항목 따르지 않음"}
                </StepLabel>
              }
              description={
                auto
                  ? `${settingsSummary(planned) || "특별한 설정 없음"} — 최신 상태로 유지됩니다.`
                  : "모든 옵션을 직접 관리합니다. 켜면 이 게임에 필요한 옵션을 위키에 맞춰 유지합니다."
              }
              checked={auto}
              disabled={busy}
              bottomSeparator="standard"
              onChange={(checked) => void onSetAuto(checked)}
            />
          </PanelSectionRow>
        ) : null}

        {/* Only while this game is up. "Not running" was being listed as the
            last step of setting a game up, which it never was: nothing about it
            is a step, and a game sitting in the library is not half-configured
            for being closed. What the log had to say is one row down, under
            Logs, where it belongs whether or not the game is running. */}
        {running ? (
          <PanelSectionRow>
            <Field
              label={<StepLabel done>실행 중</StepLabel>}
              description={`게임에서 Insert를 누르면 OptiScaler 오버레이가 열립니다. ${logSummary}`}
              onClick={onLogs}
              onActivate={onLogs}
              focusable
              bottomSeparator="standard"
              childrenLayout="inline"
              childrenContainerWidth="min"
            >
              {logPill}
            </Field>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <RequirementsSection plan={planned} />

      {foldRows}

      <PanelSection>
        <PanelSectionRow>
          {/* One row rather than three stacked buttons: on a handheld the
              things you rarely do should not each cost a screenful, and
              removing has to stay reachable without hunting for it. */}
          <Focusable style={{ display: "flex", gap: "8px" }} flow-children="horizontal">
            {planned ? (
              <DialogButton
                disabled={busy}
                onClick={() => void reapply()}
                onOKActionDescription="위키 기준으로 다시 설치"
                style={{ flex: "1 1 0", minWidth: 0, fontSize: "13px", padding: "8px 6px" }}
              >
                다시 설치
              </DialogButton>
            ) : null}
            <DialogButton
              disabled={busy}
              onClick={() => void doReset()}
              onOKActionDescription="설정을 기본값으로 초기화"
              style={{ flex: "1 1 0", minWidth: 0, fontSize: "13px", padding: "8px 6px" }}
            >
              설정 초기화
            </DialogButton>
            <DialogButton
              disabled={busy}
              onClick={() => void confirmUninstall()}
              onOKActionDescription="OptiScaler 제거"
              style={{
                flex: "1 1 0",
                minWidth: 0,
                fontSize: "13px",
                padding: "8px 6px",
                color: "#ff9d9d",
              }}
            >
              제거
            </DialogButton>
          </Focusable>
        </PanelSectionRow>
        <PanelSectionRow>
          <Focusable
            focusWithinClassName="gpfocuswithin"
            style={{ fontSize: "12px", opacity: 0.6, padding: "4px 0", lineHeight: 1.45 }}
          >
            {backedUp > 0
              ? `제거하면 따로 보관한 파일 ${backedUp}개를 복원합니다.`
              : "제거하면 설치한 파일을 모두 삭제합니다."}
          </Focusable>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}
