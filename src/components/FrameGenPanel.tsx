import { PanelSection, PanelSectionRow, SliderField, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useCallback, useEffect, useRef, useState } from "react";
import { getFrameGeneration, releaseLsfgWrapper, setFrameGeneration } from "../api";
import type { LsfgSettings } from "../api";
import { setLaunchOptions } from "../hooks/useRunningGame";
import { currentLaunchOptions } from "../launchOptions";
import {
  DEFAULT_WORKAROUNDS,
  fromWrapperState,
  hasLsfgLaunch,
  hasLsfgWrapper,
  lsfgLaunchOptions,
  PROFILE_KEY,
  readWorkarounds,
  withoutLsfg,
} from "../lsfgLaunch";
import type { LsfgWorkarounds } from "../lsfgLaunch";
import type { FrameGeneration } from "../types";
import { Mono, Notice } from "./Common";

/** What a game starts with when frame generation is turned on: decky-lsfg-vk's defaults. */
const DEFAULTS: LsfgSettings = {
  multiplier: 2,
  flow_scale: 0.8,
  performance_mode: false,
  override_present_mode: true,
  preserve_swapchain_image_count: false,
};
/** A slider's value is written once it rests, not on every step of a drag. */
const SETTLE_MS = 300;

const MULTIPLIER_NOTCHES = [
  { notchIndex: 0, label: "끔", value: 1 },
  ...[2, 3, 4, 5, 6].map((n, i) => ({ notchIndex: i + 1, label: `${n}배`, value: n })),
];

const WORKAROUND_ROWS: [keyof Omit<LsfgWorkarounds, "fpsCap">, string, string][] = [
  ["disableGamescopeWsi", "Gamescope WSI 끄기", "ENABLE_GAMESCOPE_WSI=0. 게임 모드에서 lsfg-vk의 프레임 페이싱에 필요합니다."],
  ["disableHdr", "HDR 끄기", "DXVK_HDR=0."],
  ["disableSteamDeck", "Steam Deck 모드 끄기", "SteamDeck=0. 게임의 Deck 전용 설정을 끕니다."],
  ["disableVkBasalt", "vkBasalt 끄기", "DISABLE_VKBASALT=1."],
  ["zink", "Zink (OpenGL 게임)", "OpenGL 게임을 Zink로 Vulkan 위에서 돌려 lsfg-vk가 걸리게 합니다."],
];

/** Why lsfg-vk will not generate frames yet, or null when it can. */
function notReady(state: FrameGeneration): string | null {
  const lossless = state.lossless;
  if (!lossless.installed) {
    return "Steam에서 Lossless Scaling을 사서 설치하고, 속성 → 게임 버전 및 베타에서 lsfg-vk 브랜치를 고르세요.";
  }
  if (lossless.branch !== "lsfg-vk") {
    return `Lossless Scaling이 ${lossless.branch} 브랜치입니다. Steam의 속성 → 게임 버전 및 베타에서 lsfg-vk 브랜치로 바꾸세요.`;
  }
  if (!lossless.dll) return "Lossless Scaling의 lsfg-vk 브랜치에 lsfg-vk.dll이 아직 없습니다. Steam에서 받기가 끝났는지 확인하세요.";
  return null;
}

/**
 * Frame generation for one game, through lsfg-vk: Lossless Scaling's frame
 * generation as a Vulkan layer, on top of any upscaler and in any game Proton
 * runs.
 *
 * Using it is a profile in lsfg-vk's configuration for the game (the one
 * decky-lsfg-vk shows too) and its launch options: LSFGVK_PROFILE naming that
 * profile and the workarounds, all plain variables (lsfgLaunch.ts). That takes
 * a restart. Everything in the profile — the multiplier, off at 1, the flow
 * scale, the lighter model and the two presentation quirks — changes while
 * the game runs, so the side panel (``compact``) has those over a running
 * game, as decky-lsfg-vk's does. A game run by decky-lsfg-vk's ~/.lsfg wrapper
 * leaves it when set up here, its workarounds carried over.
 */
export function FrameGenPanel({
  appid,
  name,
  compact = false,
}: Readonly<{
  appid: string | null;
  name: string;
  /** In the side panel over a running game: the live controls, without the explanation. */
  compact?: boolean;
}>) {
  const [state, setState] = useState<FrameGeneration | null>(null);
  const [launch, setLaunch] = useState<string>("");
  const [busy, setBusy] = useState(false);
  // What a slider shows while it moves, before it is written.
  const [draft, setDraft] = useState<Partial<Record<keyof LsfgSettings | "fpsCap", number>>>({});
  const timers = useRef<Record<string, number>>({});

  const load = useCallback(async () => {
    try {
      setState(await getFrameGeneration(appid ?? ""));
      setLaunch((appid ? await currentLaunchOptions(appid) : null) ?? "");
    } catch {
      setState(null);
    }
  }, [appid]);
  useEffect(() => {
    void load();
    const pending = timers.current;
    return () => Object.values(pending).forEach((timer) => window.clearTimeout(timer));
  }, [load]);

  if (!state) return null;
  const profile = state.profile;
  const settings: LsfgSettings = profile
    ? {
        multiplier: profile.multiplier,
        flow_scale: profile.flow_scale,
        performance_mode: profile.performance_mode,
        override_present_mode: profile.override_present_mode ?? true,
        preserve_swapchain_image_count: profile.preserve_swapchain_image_count ?? false,
      }
    : DEFAULTS;
  const workarounds = readWorkarounds(launch);
  const wrapped = hasLsfgWrapper(launch);

  const writeLaunch = (current: string, next: string) => {
    if (!appid || next === current) return;
    if (setLaunchOptions(Number(appid), next)) {
      setLaunch(next);
    } else {
      toaster.toast({ title: "실행 옵션을 바꾸지 못했습니다", body: `Steam에서 직접 넣으세요: ${next || "(비움)"}` });
    }
  };

  /** decky-lsfg-vk's wrapper out of this game, its workarounds kept as variables here. */
  const leaveWrapper = async (current: string, base: LsfgWorkarounds): Promise<LsfgWorkarounds> => {
    if (!appid || !hasLsfgWrapper(current)) return base;
    const released = await releaseLsfgWrapper(appid);
    toaster.toast({
      title: "decky-lsfg-vk의 ~/.lsfg를 뺐습니다",
      body: released.removed
        ? "이 게임의 워크어라운드를 옮기고, 더 쓰는 게임이 없어 ~/.lsfg 파일도 지웠습니다."
        : "이 게임의 워크어라운드는 실행 옵션으로 옮겼습니다.",
    });
    return { ...base, ...fromWrapperState(released.workarounds) };
  };

  const write = async (next: LsfgSettings | null) => {
    if (!appid) return null;
    const result = await setFrameGeneration(appid, name, next);
    setState(result);
    if (!result.ok) toaster.toast({ title: "lsfg-vk 설정을 바꾸지 못했습니다", body: String(result.error) });
    return result.ok ? result : null;
  };

  const use = async (on: boolean) => {
    if (!appid) return;
    setBusy(true);
    try {
      const current = (await currentLaunchOptions(appid)) ?? "";
      if (!on) {
        if (await write(null)) writeLaunch(current, withoutLsfg(current));
        return;
      }
      const result = await write(settings);
      if (!result?.profile) return;
      // Kept from launch options set up here before, or carried over from the wrapper.
      const base = hasLsfgLaunch(current) ? readWorkarounds(current) : DEFAULT_WORKAROUNDS;
      const carried = await leaveWrapper(current, base);
      writeLaunch(current, lsfgLaunchOptions(current, result.profile.name, carried));
    } catch (exc) {
      toaster.toast({ title: "lsfg-vk 설정을 바꾸지 못했습니다", body: String(exc) });
    } finally {
      setBusy(false);
    }
  };

  const change = async (patch: Partial<LsfgSettings>) => {
    try {
      const result = await write({ ...settings, ...patch });
      // The profile renamed elsewhere (decky-lsfg-vk names it after the game too): follow it.
      if (result?.profile && hasLsfgLaunch(launch) && !launch.includes(`"${result.profile.name}"`)) {
        writeLaunch(launch, lsfgLaunchOptions(launch, result.profile.name, workarounds));
      }
    } catch (exc) {
      toaster.toast({ title: "lsfg-vk 설정을 바꾸지 못했습니다", body: String(exc) });
    }
  };

  const changeWorkarounds = async (patch: Partial<LsfgWorkarounds>) => {
    if (!profile || !appid) return;
    const current = (await currentLaunchOptions(appid)) ?? launch;
    const base = await leaveWrapper(current, readWorkarounds(current));
    writeLaunch(current, lsfgLaunchOptions(current, profile.name, { ...base, ...patch }));
  };

  /** A slider: shown as it moves, written once it rests. */
  const slide = (key: keyof LsfgSettings | "fpsCap", next: number) => {
    setDraft((d) => ({ ...d, [key]: next }));
    window.clearTimeout(timers.current[key]);
    timers.current[key] = window.setTimeout(() => {
      setDraft((d) => {
        const rest = { ...d };
        delete rest[key];
        return rest;
      });
      if (key === "fpsCap") void changeWorkarounds({ fpsCap: next });
      else void change({ [key]: next });
    }, SETTLE_MS);
  };

  const multiplier = draft.multiplier ?? settings.multiplier;
  const flow = draft.flow_scale ?? settings.flow_scale;
  const fpsCap = draft.fpsCap ?? workarounds.fpsCap;
  const warning = state.installed ? notReady(state) : null;

  return (
    <PanelSection title="프레임 생성 (lsfg-vk)">
      {!state.installed ? (
        <PanelSectionRow>
          <Notice tone="info" title="lsfg-vk가 설치되어 있지 않습니다">
            {compact
              ? "라이브러리 및 설정 → 설정 → 받은 파일에서 설치할 수 있습니다."
              : "설정 → 받은 파일에서 lsfg-vk를 설치하면 Lossless Scaling의 프레임 생성을 게임별로 켤 수 있습니다."}
          </Notice>
        </PanelSectionRow>
      ) : (
        <>
          {warning ? (
            <PanelSectionRow>
              <Notice tone="warn" title="Lossless Scaling이 준비되지 않았습니다">
                {warning}
              </Notice>
            </PanelSectionRow>
          ) : null}
          <PanelSectionRow>
            <ToggleField
              label="lsfg-vk 사용"
              description={
                !appid
                  ? "Steam 앱 ID가 없는 게임에는 켤 수 없습니다."
                  : "이 게임의 프로필과 실행 옵션을 만듭니다. 켜고 끄기는 게임을 다시 시작하면 적용되고, 아래 설정은 게임 중에도 바로 바뀝니다."
              }
              checked={profile !== null}
              disabled={busy || !appid}
              bottomSeparator="standard"
              onChange={(on) => void use(on)}
            />
          </PanelSectionRow>
          {profile ? (
            <>
              <PanelSectionRow>
                <SliderField
                  label={`배수 · ${multiplier === 1 ? "끔" : `${multiplier}배`}`}
                  description={compact ? undefined : "끔이면 프레임을 만들지 않습니다. 게임 중에 바로 바뀝니다."}
                  value={multiplier}
                  min={1}
                  max={6}
                  step={1}
                  notchCount={6}
                  notchLabels={MULTIPLIER_NOTCHES}
                  notchTicksVisible
                  showValue={false}
                  onChange={(next) => slide("multiplier", next)}
                  {...({ "data-lsfg": "multiplier" } as Record<string, string>)}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <SliderField
                  label={`Flow Scale · ${Math.round(flow * 100)}%`}
                  description={compact ? undefined : "움직임 계산 해상도입니다. 낮을수록 빠르고 화질은 떨어집니다."}
                  value={flow}
                  min={0.25}
                  max={1}
                  step={0.01}
                  showValue={false}
                  onChange={(next) => slide("flow_scale", next)}
                  {...({ "data-lsfg": "flow_scale" } as Record<string, string>)}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label="성능 모드"
                  description={compact ? undefined : "더 가벼운 모델을 씁니다. 대부분의 게임에 권장됩니다."}
                  checked={settings.performance_mode}
                  bottomSeparator="standard"
                  onChange={(on) => void change({ performance_mode: on })}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label="Present Mode 덮어쓰기"
                  description={compact ? undefined : "화면 표시 방식을 VSync(FIFO)로 고정합니다. 기본으로 켜져 있습니다."}
                  checked={settings.override_present_mode}
                  bottomSeparator="standard"
                  onChange={(on) => void change({ override_present_mode: on })}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label="Swapchain 이미지 수 유지"
                  description={compact ? undefined : "게임이 정한 swapchain 이미지 수를 그대로 둡니다. 문제가 있는 게임에서만 켭니다."}
                  checked={settings.preserve_swapchain_image_count}
                  bottomSeparator="standard"
                  onChange={(on) => void change({ preserve_swapchain_image_count: on })}
                />
              </PanelSectionRow>
              {compact ? null : (
                <>
                  <PanelSectionRow>
                    <Notice tone="info" title="워크어라운드 (다음 실행부터)">
                      실행 옵션의 변수로 넣습니다. 이 게임의 lsfg-vk 프로필은 <Mono>{profile.name}</Mono>이고,
                      실행 옵션의 <Mono>{PROFILE_KEY}</Mono>가 이 프로필을 지정합니다(decky-lsfg-vk와 함께 씀).
                      {wrapped
                        ? " 지금은 decky-lsfg-vk의 ~/.lsfg로 실행됩니다. 여기서 바꾸면 이 게임의 워크어라운드를 실행 옵션으로 옮기고 ~/.lsfg를 뺍니다."
                        : ""}
                    </Notice>
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <SliderField
                      label={`기본 FPS 상한 · ${fpsCap > 0 ? `${fpsCap}` : "없음"}`}
                      description="DXVK 게임에서 프레임 생성 전 기본 프레임을 묶습니다(DXVK_FRAME_RATE). 0이면 끔."
                      value={fpsCap}
                      min={0}
                      max={60}
                      step={1}
                      showValue={false}
                      onChange={(next) => slide("fpsCap", next)}
                      {...({ "data-lsfg": "fps_cap" } as Record<string, string>)}
                    />
                  </PanelSectionRow>
                  {WORKAROUND_ROWS.map(([key, label, about]) => (
                    <PanelSectionRow key={key}>
                      <ToggleField
                        label={label}
                        description={about}
                        checked={workarounds[key]}
                        disabled={busy}
                        bottomSeparator="standard"
                        onChange={(on) => void changeWorkarounds({ [key]: on })}
                        {...({ "data-workaround": key } as Record<string, string>)}
                      />
                    </PanelSectionRow>
                  ))}
                </>
              )}
            </>
          ) : null}
          {state.error ? (
            <PanelSectionRow>
              <Notice tone="warn" title="lsfg-vk 설정을 읽지 못했습니다">
                {state.error}
              </Notice>
            </PanelSectionRow>
          ) : null}
        </>
      )}
    </PanelSection>
  );
}
