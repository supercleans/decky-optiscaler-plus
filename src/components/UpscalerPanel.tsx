import { ButtonItem, ConfirmModal, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { buildHlxDlss, cancelHlxDlssBuild, getHlxDlssBuild } from "../api";
import type {
  DropinStatus,
  GameDetail,
  GpuInfo,
  HelixsrStatus,
  HlxBuildStatus,
  Upscaler,
} from "../types";
import { Mono, Notice, Pill } from "./Common";

/** How an upscaler gets into a game: OptiScaler's nightly, HelixSR Scaler, or a drop-in. */
export type UpscalerMethod = "nightly" | "scaler" | "dropin";

export const UPSCALER_INFO: Record<Upscaler, { label: string; about: string }> = {
  "fsr4-lite": {
    label: "FSR 4 Lite",
    about: "AMD FSR 4.1.2의 INT8 Lite 모델. FSR 3.1이 있는 게임은 OptiScaler nightly에 들어 있는 AMD 파일을 드롭인으로 넣고(시험: Steam Deck에서 동작하지 않을 수 있음), 없는 게임은 OptiScaler로 넣습니다.",
  },
  "fsr412l-exact": {
    label: "FSR 4.1.2 Lite exact",
    about: "cyboman의 FSR 4.1.2 Lite 빌드. AMD Lite와 화질이 같고 조금 빠릅니다. FSR 3.1이 있는 게임은 드롭인, 없는 게임은 OptiScaler로 넣습니다.",
  },
  "fsr412l-lossy": {
    label: "FSR 4.1.2 Lite lossy",
    about: "cyboman의 FSR 4.1.2 Lite 재학습 빌드. AMD Lite보다 약 18% 빠르고 화질은 조금 다릅니다. FSR 3.1이 있는 게임은 드롭인, 없는 게임은 OptiScaler로 넣습니다.",
  },
  "hlx-fsr4": {
    label: "HLX FSR 4",
    about: "HelixSR가 자체 파이프라인으로 돌리는 AMD FSR 4 신경망. HelixSR 공식 릴리스에서 받습니다. FSR 3.1이 있는 게임은 드롭인, 없는 게임은 OptiScaler로 넣습니다.",
  },
  "hlx-dlss": {
    label: "HLX DLSS",
    about: "HelixSR가 돌리는 NVIDIA DLSS 신경망. 이 기기에서 빌드해야 합니다: HelixSR Desktop이 빌드한 것이 있으면 그것을, 없으면 이 플러그인이 HelixSR 설정으로 빌드합니다. HelixSR Scaler로 넣고, 게임에서 DLSS를 고르면 동작합니다.",
  },
};

export const UPSCALER_ORDER: Upscaler[] = [
  "fsr4-lite",
  "fsr412l-exact",
  "fsr412l-lossy",
  "hlx-fsr4",
  "hlx-dlss",
];

/**
 * cyboman's builds and HLX FSR 4: one FidelityFX upscaler DLL each, downloaded,
 * as a drop-in or as an OptiScaler custom upscaler.
 */
export function isCustom(upscaler: Upscaler | null | undefined) {
  return upscaler === "fsr412l-exact" || upscaler === "fsr412l-lossy" || upscaler === "hlx-fsr4";
}

/**
 * The custom upscalers an OptiScaler install left out because they could not
 * be downloaded, by name; null when none was. The picked one is never among
 * them: its failure fails the install.
 */
export function customMissed(result: unknown): string | null {
  type Shape = { custom_errors?: { upscaler: Upscaler; error: string }[] };
  const outer = result as Shape & { install?: Shape };
  const errors = outer?.custom_errors ?? outer?.install?.custom_errors ?? [];
  return errors.length
    ? errors.map((e) => `${UPSCALER_INFO[e.upscaler]?.label ?? e.upscaler}: ${e.error}`).join(" · ")
    : null;
}

const METHOD_LABEL: Record<UpscalerMethod, string> = {
  nightly: "OptiScaler",
  scaler: "HelixSR Scaler",
  dropin: "드롭인",
};

export function upscalerLabel(upscaler: Upscaler | null | undefined) {
  return UPSCALER_INFO[upscaler ?? "fsr4-lite"]?.label ?? "FSR 4 Lite";
}

/**
 * The way an upscaler goes into this game. All but HLX DLSS are FidelityFX
 * DLLs of their own, so a game with FSR 3.1 takes them as a drop-in and any
 * other gets them through OptiScaler; HLX DLSS only runs inside HelixSR Scaler.
 */
export function upscalerMethod(upscaler: Upscaler, dropinPossible: boolean): UpscalerMethod {
  if (upscaler === "hlx-dlss") return "scaler";
  return dropinPossible ? "dropin" : "nightly";
}

/**
 * The upscalers this machine may pick. On the BC-250 only HelixSR's two: AMD's
 * FSR 4 and cyboman's builds of it are left to OptiScaler's GPU check, which
 * turns that GPU down. The backend refuses the rest the same way.
 */
export function allowedUpscalers(gpu: GpuInfo | null | undefined): Upscaler[] {
  return gpu?.device === "bc250" ? ["hlx-fsr4", "hlx-dlss"] : UPSCALER_ORDER;
}

/** Why this upscaler cannot go into this game now; null when it can. */
export function upscalerBlocker(
  upscaler: Upscaler,
  helixsr: HelixsrStatus | null,
  gpu?: GpuInfo | null
): string | null {
  if (!allowedUpscalers(gpu).includes(upscaler)) {
    return "BC-250에서는 HLX FSR 4와 HLX DLSS만 쓸 수 있습니다.";
  }
  if (upscaler !== "hlx-dlss") return null;
  return helixsr?.dlss_ready ? null : "HLX DLSS가 아직 빌드되지 않았습니다. 아래에서 빌드하세요.";
}

/**
 * The upscaler to start with on this machine. On the BC-250 OptiScaler does not
 * give AMD's FSR 4 to its GPU, and its int8 is slow; HLX FSR 4 picks its fp16
 * version there and is the faster FSR 4. The backend makes the same choice for
 * an install that names none (service.default_upscaler).
 */
export function recommendedUpscaler(gpu: GpuInfo | null | undefined): Upscaler {
  return gpu?.device === "bc250" ? "hlx-fsr4" : "fsr4-lite";
}

/** The upscaler this game is set up with now, or null when it has none of ours. */
export function currentUpscaler(detail: GameDetail, dropin: DropinStatus | null): Upscaler | null {
  if (dropin?.installed) return dropin.upscaler ?? "fsr412l-lossy";
  if (detail.install.installed && detail.install.managed) return detail.install.upscaler ?? "fsr4-lite";
  return null;
}

/**
 * The first thing to choose for a game: which upscaler. How it goes in —
 * OptiScaler, HelixSR Scaler or a drop-in — follows from that and from the
 * game's own files, and the steps below the list are the ones that way needs.
 */
export function UpscalerPanel({
  selected,
  current,
  dropinPossible,
  optiscalerNeeds = [],
  gpu,
  helixsr,
  checkingHelixsr,
  onSelect,
  onRecheckHelixsr,
}: Readonly<{
  selected: Upscaler;
  current: Upscaler | null;
  dropinPossible: boolean;
  /**
   * What the wiki says this game needs before OptiScaler works in it
   * (REFramework, a Luma mod, ...). The OptiScaler ways need it; a drop-in,
   * which swaps the game's own FSR 3.1, does not — and saying which is the
   * whole difference between the two in a game like Resident Evil Requiem.
   */
  optiscalerNeeds?: string[];
  /** This machine's GPU, which decides the recommended upscaler. */
  gpu?: GpuInfo | null;
  helixsr: HelixsrStatus | null;
  checkingHelixsr?: boolean;
  onSelect: (upscaler: Upscaler) => void;
  onRecheckHelixsr: () => void;
}>) {
  const blocker = upscalerBlocker(selected, helixsr, gpu);
  const hlx = selected === "hlx-dlss";
  const recommended = recommendedUpscaler(gpu);
  // What this machine can pick, and the one a game already has even if not.
  const rows = UPSCALER_ORDER.filter(
    (upscaler) => allowedUpscalers(gpu).includes(upscaler) || upscaler === current
  );
  return (
    <PanelSection title="업스케일러">
      {rows.map((upscaler) => {
        const reason = upscalerBlocker(upscaler, helixsr, gpu);
        const method = upscalerMethod(upscaler, dropinPossible);
        const chosen = upscaler === selected;
        const needs = optiscalerNeeds.length
          ? method === "dropin"
            ? `${optiscalerNeeds.join(", ")} 없이 동작합니다.`
            : `${optiscalerNeeds.join(", ")}도 있어야 합니다(위키).`
          : null;
        // A drop-in that spares the game everything the OptiScaler way needs
        // is the simpler of the two, and worth saying so in the list.
        const simpler = !reason && method === "dropin" && optiscalerNeeds.length > 0;
        return (
          <PanelSectionRow key={upscaler}>
            <Field
              label={
                <span>
                  <span style={{ opacity: chosen ? 1 : 0.45, marginRight: "8px" }}>
                    {chosen ? "●" : "○"}
                  </span>
                  {UPSCALER_INFO[upscaler].label}
                </span>
              }
              description={[UPSCALER_INFO[upscaler].about, reason ?? needs].filter(Boolean).join(" ")}
              onClick={() => onSelect(upscaler)}
              onActivate={() => onSelect(upscaler)}
              focusable
              bottomSeparator="standard"
              childrenLayout="inline"
              childrenContainerWidth="min"
              {...({ "data-upscaler": upscaler } as Record<string, string>)}
            >
              {current === upscaler ? <Pill color="#2f6b3f">적용됨</Pill> : null}
              {upscaler === recommended && gpu?.device ? <Pill color="#3a6ea5">추천</Pill> : null}
              {simpler ? <Pill color="#2b6f6a">간단</Pill> : null}
              {reason ? <Pill>불가</Pill> : <Pill>{METHOD_LABEL[method]}</Pill>}
            </Field>
          </PanelSectionRow>
        );
      })}
      {hlx && (blocker || !helixsr?.found) ? (
        <HelixsrGuide helixsr={helixsr} busy={checkingHelixsr} onRecheck={onRecheckHelixsr} />
      ) : blocker ? (
        <PanelSectionRow>
          <Notice tone="warn" title={`이 게임에는 ${UPSCALER_INFO[selected].label}를 쓸 수 없습니다`}>
            {blocker} 다른 업스케일러를 고르세요.
          </Notice>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}

/** What building HLX DLSS here does, agreed to before it starts. */
export function HlxBuildConsent({
  closeModal,
  onOK,
}: Readonly<{ closeModal?: () => void; onOK: () => void }>) {
  return (
    <ConfirmModal
      strTitle="HLX DLSS를 빌드할까요?"
      strOKButtonText="동의하고 빌드"
      strCancelButtonText="취소"
      closeModal={closeModal}
      onOK={onOK}
    >
      <div style={{ fontSize: "14px", lineHeight: 1.5 }}>
        HelixSR 공식 설정 스크립트로 이 기기에서 HLX DLSS를 빌드합니다. NVIDIA의 DLSS DLL
        (<Mono>nvngx_dlss.dll</Mono>)을 NVIDIA GitHub에서 받아 빌드에 한 번 쓰고 지웁니다. 이 DLL과
        빌드 결과는 NVIDIA의 것으로 NVIDIA 라이선스(<Mono>github.com/NVIDIA/DLSS</Mono>)를 따르며, 이
        기기에서만 쓰고 공유하면 안 됩니다. 처음 한 번은 Python과 Microsoft 셰이더 컴파일러도 받고,
        빌드에 몇 분 이상 걸립니다. Proton이 설치되어 있어야 합니다.
      </div>
    </ConfirmModal>
  );
}

/**
 * Whether HLX DLSS is built on this Deck, and building it when it is not.
 *
 * HLX DLSS is NVIDIA's network rebuilt on the user's own machine, which may
 * not be shared. A build HelixSR Desktop made is used when there is one;
 * otherwise this plugin runs HelixSR's own setup on the release it downloads,
 * once the user agreed to NVIDIA's licence. The build runs in the backend, so
 * it goes on with this closed and is picked up again when it opens.
 */
export function HelixsrGuide({
  helixsr,
  busy,
  onRecheck,
}: Readonly<{ helixsr: HelixsrStatus | null; busy?: boolean; onRecheck: () => void }>) {
  const ready = Boolean(helixsr?.dlss_ready);
  const [build, setBuild] = useState<HlxBuildStatus | null>(null);
  const running = Boolean(build?.running);
  // A build that ends while this is open changes what HelixSR has.
  const wasRunning = useRef(false);
  const recheck = useRef(onRecheck);
  recheck.current = onRecheck;
  const refresh = useCallback(async () => {
    try {
      setBuild(await getHlxDlssBuild());
    } catch {
      // The next tick asks again.
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!running) {
      if (wasRunning.current) recheck.current();
      wasRunning.current = false;
      return undefined;
    }
    wasRunning.current = true;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [running, refresh]);
  const start = () =>
    showModal(
      <HlxBuildConsent
        onOK={() =>
          void buildHlxDlss().then((result) => setBuild(result.build), () => void refresh())
        }
      />
    );
  const source = helixsr?.plugin ? "이 플러그인이 빌드" : "HelixSR Desktop";
  return (
    <>
      <PanelSectionRow>
        {running ? (
          <Notice
            tone="info"
            title={`HLX DLSS 빌드 중${build?.percent != null ? ` ${build.percent}%` : ""}`}
          >
            {build?.step ?? "준비 중"}
            {build?.tag ? ` · HelixSR ${build.tag}` : ""}. 이 화면을 닫아도 빌드는 계속됩니다.
          </Notice>
        ) : helixsr?.found && ready ? (
          <Notice tone="success" title={`HelixSR ${helixsr.version ?? ""} 있음`}>
            HLX DLSS 준비됨({source})
            {helixsr.scaler_version ? ` · HelixSR Scaler ${helixsr.scaler_version}` : ""}.{" "}
            <Mono>{helixsr.root}</Mono>
          </Notice>
        ) : (
          <Notice tone="info" title="HLX DLSS를 빌드해야 합니다">
            HLX DLSS는 NVIDIA 파일로 각자의 기기에서 빌드해야 합니다. HelixSR Desktop으로 빌드해 둔
            것이 있으면 그것을 쓰고, 없으면 아래 버튼으로 이 플러그인이 HelixSR 공식 설정을 실행해
            빌드합니다. 게임에 설치는 여기서 합니다.
          </Notice>
        )}
      </PanelSectionRow>
      {!running && build?.error ? (
        <PanelSectionRow>
          <Notice tone="warn" title="HLX DLSS를 빌드하지 못했습니다">
            {build.error}
          </Notice>
        </PanelSectionRow>
      ) : null}
      {running ? (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => void cancelHlxDlssBuild().then(refresh)}>
            빌드 취소
          </ButtonItem>
        </PanelSectionRow>
      ) : !ready ? (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={start}>
            HLX DLSS 빌드
          </ButtonItem>
        </PanelSectionRow>
      ) : null}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || running} onClick={onRecheck}>
          {busy ? "확인 중…" : "HelixSR 다시 확인"}
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
