import { ButtonItem, ConfirmModal, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { removeDownloads, startSetup, updateComponent } from "../api";
import { publishComponents, useComponents } from "../hooks/useComponents";
import type { Channel, ComponentChannel, HlxBuildStatus, JobStatus, JobStep } from "../types";
import { Centered, KeyValue, Mono, Notice, Pill } from "./Common";
import { HlxBuildConsent } from "./UpscalerPanel";

const CHANNEL_LABEL: Record<Channel, string> = {
  nightly: "OptiScaler nightly",
  dropin: "cyboman FSR 4.1.2 Lite",
  helixsr: "HelixSR",
};

const STEP_LABEL: Record<JobStep["state"], string> = {
  pending: "대기",
  running: "진행 중",
  done: "완료",
  failed: "실패",
  skipped: "건너뜀",
};

/** What the set-up downloads and builds, agreed to before it starts. */
function SetupConsent({
  desktop,
  closeModal,
  onOK,
}: Readonly<{ desktop: boolean; closeModal?: () => void; onOK: () => void }>) {
  return (
    <ConfirmModal
      strTitle="필요한 파일을 설치할까요?"
      strOKButtonText={desktop ? "설치" : "동의하고 설치"}
      strCancelButtonText="취소"
      closeModal={closeModal}
      onOK={onOK}
    >
      <div style={{ fontSize: "14px", lineHeight: 1.5 }}>
        OptiScaler nightly, cyboman의 FSR 4.1.2 Lite 빌드
        {desktop
          ? "를 받습니다. HelixSR는 HelixSR Desktop이 설정해 둔 것을 씁니다."
          : <>
              , HelixSR 공식 릴리스를 받고, HelixSR 공식 설정 스크립트로 이 기기에서 HLX DLSS를
              빌드합니다. 빌드에는 NVIDIA의 DLSS DLL(<Mono>nvngx_dlss.dll</Mono>)을 NVIDIA GitHub에서
              받아 한 번 쓰고 지웁니다. 이 DLL과 빌드 결과는 NVIDIA의 것으로 NVIDIA
              라이선스(<Mono>github.com/NVIDIA/DLSS</Mono>)를 따르며, 이 기기에서만 쓰고 공유하면 안
              됩니다. 수백 MB를 받고 몇 분 이상 걸리며, HLX DLSS 빌드에는 Proton이 필요합니다.
            </>}{" "}
        이 화면을 닫아도 설치는 계속됩니다.
      </div>
    </ConfirmModal>
  );
}

/** The steps of the set-up or an update, each with how it went. */
export function JobSteps({ job, build }: Readonly<{ job: JobStatus; build: HlxBuildStatus }>) {
  return (
    <>
      {job.steps.map((step) => {
        const building = step.key === "hlx_dlss" && step.state === "running" && build.running;
        const detail = building
          ? `${build.step ?? "준비 중"}${build.percent != null ? ` · ${build.percent}%` : ""}`
          : step.detail;
        return (
          <PanelSectionRow key={step.key}>
            <Field
              label={step.label}
              description={detail ?? undefined}
              focusable
              bottomSeparator="standard"
              childrenLayout="inline"
              childrenContainerWidth="min"
              {...({ "data-step": step.key, "data-state": step.state } as Record<string, string>)}
            >
              <Pill color={step.state === "failed" ? "#8a3a3a" : step.state === "done" ? "#2f6b3f" : undefined}>
                {STEP_LABEL[step.state]}
              </Pill>
            </Field>
          </PanelSectionRow>
        );
      })}
    </>
  );
}

/**
 * The plugin before it is set up: what it needs, and the button that gets it.
 * Nothing else is offered until the downloads are there, so no install waits
 * on a download in front of a game.
 */
export function SetupPanel() {
  const { components } = useComponents();
  const [starting, setStarting] = useState(false);
  if (!components) return <Centered>확인 중…</Centered>;
  const job = components.job;
  const settingUp = job.running && job.kind === "setup";
  const failed = !job.running && job.kind === "setup" && Boolean(job.error);
  const desktop = components.channels.helixsr.source === "desktop";

  const begin = async () => {
    setStarting(true);
    try {
      const result = await startSetup();
      if (!result.ok) toaster.toast({ title: "설치를 시작하지 못했습니다", body: String(result.error) });
      publishComponents(result.components);
    } catch (exc) {
      toaster.toast({ title: "설치를 시작하지 못했습니다", body: String(exc) });
    } finally {
      setStarting(false);
    }
  };

  return (
    <PanelSection title="처음 설치">
      <PanelSectionRow>
        <Notice tone="info" title="먼저 필요한 파일을 설치하세요">
          게임에 넣을 파일을 모두 받아 둡니다: OptiScaler nightly, cyboman의 FSR 4.1.2 Lite 빌드,
          HelixSR(HLX FSR 4). HLX DLSS는 HelixSR 공식 설정으로 이 기기에서 빌드합니다. HelixSR
          Desktop으로 설정해 둔 HelixSR가 있으면 그것을 씁니다. 설치가 끝나면 게임을 설정할 수
          있습니다.
        </Notice>
      </PanelSectionRow>
      {job.kind === "setup" ? <JobSteps job={job} build={components.build} /> : null}
      {failed ? (
        <PanelSectionRow>
          <Notice tone="warn" title="설치하지 못했습니다">
            {job.error}
          </Notice>
        </PanelSectionRow>
      ) : null}
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={settingUp || starting}
          onClick={() => showModal(<SetupConsent desktop={desktop} onOK={() => void begin()} />)}
        >
          {settingUp ? "설치 중…" : failed ? "다시 시도" : "설치"}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

/** "HelixSR 3.2.1 (HelixSR Desktop에서 업데이트)", for the notice. */
function describeUpdate(channel: Channel, entry: ComponentChannel) {
  const desktop = channel === "helixsr" && entry.source === "desktop";
  return `${CHANNEL_LABEL[channel]} ${entry.latest ?? ""}${desktop ? " (HelixSR Desktop에서 업데이트)" : ""}`;
}

/**
 * Newer builds of the plugin's downloads, and a HelixSR Desktop set-up that
 * has gone, said at the top of the main page. Renders nothing otherwise.
 */
export function ComponentNotice() {
  const { components } = useComponents();
  if (!components?.setup_done) return null;
  const channels = components.channels;
  const updates = components.updates;
  const missing = Boolean(channels.helixsr.desktop_missing);
  if (updates.length === 0 && !missing) return null;
  const inSettings = updates.some((c) => !(c === "helixsr" && channels.helixsr.source === "desktop"));
  return (
    <PanelSection>
      {updates.length > 0 ? (
        <PanelSectionRow>
          <Notice tone="info" title="새 빌드가 있습니다">
            {updates.map((c) => describeUpdate(c, channels[c])).join(", ")}.
            {inSettings ? " 설정 탭에서 업데이트하세요." : ""}
          </Notice>
        </PanelSectionRow>
      ) : null}
      {missing ? (
        <PanelSectionRow>
          <Notice tone="warn" title="HelixSR Desktop의 HelixSR가 없어졌습니다">
            HLX FSR 4와 HLX DLSS를 쓰려면 설정 탭에서 플러그인으로 HelixSR를 설치하세요.
          </Notice>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}

/** What is on the Deck for one channel, in a sentence. */
function describeChannel(channel: Channel, entry: ComponentChannel) {
  if (!entry.used) return "이 기기에서는 쓰지 않습니다.";
  const parts: string[] = [];
  if (channel === "helixsr" && entry.source === "desktop") {
    parts.push(`HelixSR Desktop의 HelixSR ${entry.desktop_version ?? ""}`.trim());
  } else if (entry.installed) {
    parts.push(channel === "nightly" && entry.version ? `${entry.installed} (OptiScaler ${entry.version})` : entry.installed);
  } else {
    parts.push("받지 않음");
  }
  if (channel === "helixsr") parts.push(entry.dlss_ready ? "HLX DLSS 준비됨" : "HLX DLSS 빌드 안 됨");
  if (entry.pinned) parts.push(`${entry.pinned}로 고정`);
  if (entry.update) parts.push(`새 빌드 ${entry.latest}`);
  return parts.join(" · ");
}

/**
 * The plugin's downloads in Settings: what each is, updating one when a newer
 * build is out (or getting one that is missing), checking now, and removing
 * them all. HelixSR Desktop's HelixSR is that app's to update.
 */
export function ComponentsSection() {
  const { components, check, checking, busy } = useComponents();
  const [working, setWorking] = useState(false);
  if (!components) return null;
  const { channels, job } = components;

  const run = async (channel: Channel) => {
    setWorking(true);
    try {
      const result = await updateComponent(channel);
      if (!result.ok) toaster.toast({ title: "업데이트를 시작하지 못했습니다", body: String(result.error) });
      publishComponents(result.components);
    } catch (exc) {
      toaster.toast({ title: "업데이트를 시작하지 못했습니다", body: String(exc) });
    } finally {
      setWorking(false);
    }
  };
  // HelixSR is built again in the new release, which hands NVIDIA's DLL over.
  const update = (channel: Channel) =>
    channel === "helixsr"
      ? showModal(<HlxBuildConsent onOK={() => void run(channel)} />)
      : void run(channel);

  const remove = () =>
    showModal(
      <ConfirmModal
        strTitle="받은 파일을 모두 지울까요?"
        strOKButtonText="모두 지우기"
        strCancelButtonText="취소"
        onOK={() =>
          void (async () => {
            setWorking(true);
            try {
              const result = await removeDownloads();
              if (!result.ok) toaster.toast({ title: "지우지 못했습니다", body: String(result.error) });
              else toaster.toast({ title: "받은 파일을 지웠습니다", body: "다시 쓰려면 처음 설치를 하세요." });
              publishComponents(result.components);
            } finally {
              setWorking(false);
            }
          })()
        }
      >
        <div style={{ fontSize: "14px", lineHeight: 1.5 }}>
          OptiScaler, cyboman 빌드, HelixSR(빌드한 HLX DLSS 포함), OptiPatcher, REFramework 등 이
          플러그인이 받은 파일을 모두 지웁니다. 게임에 설치한 파일은 그대로 둡니다. HelixSR Desktop이
          없으면 HelixSR 설정 도구(<Mono>~/.local/share/HelixSR</Mono>)도 지웁니다. 지운 뒤에는 처음
          설치부터 다시 해야 합니다.
        </div>
      </ConfirmModal>
    );

  const updating = job.kind === "update" && (job.running || job.error);
  return (
    <PanelSection title="받은 파일">
      {(Object.keys(CHANNEL_LABEL) as Channel[]).map((channel) => {
        const entry = channels[channel];
        const desktop = channel === "helixsr" && entry.source === "desktop";
        const wanted = entry.used && !desktop && (entry.update || !entry.installed);
        return (
          <div key={channel}>
            <PanelSectionRow>
              <Field
                label={CHANNEL_LABEL[channel]}
                description={describeChannel(channel, entry)}
                focusable
                bottomSeparator="standard"
                childrenLayout="inline"
                childrenContainerWidth="min"
                {...({ "data-component": channel } as Record<string, string>)}
              >
                {entry.update ? <Pill color="#3a6ea5">새 빌드</Pill> : null}
              </Field>
            </PanelSectionRow>
            {desktop && entry.update ? (
              <PanelSectionRow>
                <Notice tone="info" title={`HelixSR ${entry.latest}이 나왔습니다`}>
                  HelixSR Desktop의 HelixSR를 쓰고 있습니다. 데스크톱 모드에서 HelixSR Desktop으로
                  업데이트하세요.
                </Notice>
              </PanelSectionRow>
            ) : null}
            {channel === "helixsr" && entry.desktop_missing ? (
              <PanelSectionRow>
                <Notice tone="warn" title="HelixSR Desktop의 HelixSR가 없어졌습니다">
                  쓰고 있던 HelixSR Desktop의 HelixSR를 찾을 수 없습니다. 플러그인으로 HelixSR를 받고
                  HLX DLSS를 빌드할 수 있습니다.
                </Notice>
              </PanelSectionRow>
            ) : null}
            {wanted ? (
              <PanelSectionRow>
                <ButtonItem layout="below" disabled={busy || working} onClick={() => update(channel)}>
                  {entry.installed
                    ? `${CHANNEL_LABEL[channel]} 업데이트${entry.latest ? ` (${entry.latest})` : ""}`
                    : channel === "helixsr"
                      ? "플러그인으로 HelixSR 설치"
                      : `${CHANNEL_LABEL[channel]} 받기`}
                </ButtonItem>
              </PanelSectionRow>
            ) : null}
          </div>
        );
      })}
      {updating ? <JobSteps job={job} build={components.build} /> : null}
      {job.kind === "update" && !job.running && job.error ? (
        <PanelSectionRow>
          <Notice tone="warn" title="업데이트하지 못했습니다">
            {job.error}
          </Notice>
        </PanelSectionRow>
      ) : null}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={checking || busy} onClick={() => void check(true)}>
          {checking ? "확인 중…" : "새 빌드 확인"}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field bottomSeparator="none" focusable>
          <div style={{ width: "100%" }}>
            <KeyValue
              label="마지막 확인"
              value={components.checked_at ? new Date(components.checked_at * 1000).toLocaleString() : "아직 없음"}
            />
            {components.update_error ? (
              <KeyValue label="확인 실패" value={<Mono>{components.update_error}</Mono>} />
            ) : null}
          </div>
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || working} onClick={remove}>
          받은 파일 모두 지우기
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
