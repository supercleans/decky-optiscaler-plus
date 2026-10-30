import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  Focusable,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  showModal,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { install, setGameTarget, setWikiEntry } from "../api";
import { setLaunchOptions } from "../hooks/useRunningGame";
import {
  currentLaunchOptions,
  mergeLaunchOptions,
  overrideStem,
  recordPreviousLaunchOptions,
} from "../launchOptions";
import { PREF_INSTALL_LAUNCH, isRemembering, recall, remember } from "../prefs";
import { useAutoPlan } from "../hooks/useAutoPlan";
import type { GameDetail, PayloadStatus, Upscaler } from "../types";
import { KeyValue, Mono, Notice, Pill } from "./Common";
import {
  OPTIPATCHER_UNLISTED,
  OPTIPATCHER_WHY,
  OptipatcherPanel,
  optipatcherMissed,
} from "./OptipatcherPanel";
import { customMissed, upscalerLabel } from "./UpscalerPanel";
import { WikiSearch } from "./WikiSearch";

interface Props {
  detail: GameDetail;
  status: PayloadStatus | null;
  appid: string | null;
  /** The upscaler picked on the setup page, which decides the OptiScaler build. */
  upscaler: Upscaler;
  /** Why that upscaler cannot be installed now, or null. */
  blocked?: string | null;
  onChanged: () => Promise<void> | void;
}

/**
 * Asked once, right after an install that needs it.
 *
 * Without the override Proton loads its own copy of the DLL and OptiScaler
 * never runs at all, so this is the difference between an install that works
 * and one that silently does nothing — worth interrupting for, but not worth
 * asking twice, hence "Remember my choice".
 */
function LaunchOptionsPrompt({
  filename,
  launchOption,
  canRemember,
  closeModal,
  onDecide,
}: Readonly<{
  filename: string;
  launchOption: string;
  /** False once the user has turned remembering off under Settings. */
  canRemember: boolean;
  closeModal?: () => void;
  onDecide: (apply: boolean, remember: boolean) => void;
}>) {
  const [rememberIt, setRememberIt] = useState(false);
  return (
    <ConfirmModal
      strTitle="Steam 실행 옵션을 설정할까요?"
      strOKButtonText="자동 설정"
      strCancelButtonText="나중에"
      closeModal={closeModal}
      onOK={() => onDecide(true, rememberIt)}
      onCancel={() => onDecide(false, rememberIt)}
    >
      <div style={{ fontSize: "14px", lineHeight: 1.5 }}>
        이 오버라이드를 설정하지 않으면 Proton이 자체 <Mono>{filename}</Mono> 파일을 불러와
        OptiScaler가 실행되지 않습니다:
        <div style={{ margin: "8px 0" }}>
          <Mono>{launchOption}</Mono>
        </div>
      </div>
      {canRemember ? (
        <ToggleField
          label="이 선택 기억"
          checked={rememberIt}
          bottomSeparator="none"
          onChange={setRememberIt}
        />
      ) : null}
    </ConfirmModal>
  );
}

/**
 * Everything about one install that is not the three steps: which file name,
 * which folder, OptiPatcher, the wiki entry to follow and the launch options. Reached from "Manual setup" on the setup checklist,
 * which is where the majority of games never have to come.
 */
export function InstallPanel({ detail, status, appid, upscaler, blocked, onChanged }: Props) {
  /** HelixSR Scaler rather than the nightly; it brings its own OptiPatcher. */
  const hlx = upscaler === "hlx-dlss";
  const [filename, setFilename] = useState(detail.install.filename ?? "dxgi.dll");
  const [target, setTarget] = useState(detail.target);
  const [preserveIni, setPreserveIni] = useState(false);
  const [optipatcher, setOptipatcher] = useState(false);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  /**
   * What Steam is passing right now, or null when no source could say.
   *
   * Stated on the page rather than only used: when the launch options are the
   * half of an install that is not working, "the plugin cannot read them" and
   * "they are empty" look identical from the outside, and telling them apart
   * took a source-code read the last time it mattered.
   */
  const [launchNow, setLaunchNow] = useState<string | null>(null);
  const [launchRead, setLaunchRead] = useState(false);
  const proxies = status?.proxy_filenames ?? ["dxgi.dll"];
  const {
    plan,
    recommendation,
    loading: loadingWiki,
    reload: lookup,
  } = useAutoPlan(detail.path, detail.name);

  useEffect(() => {
    setTarget(detail.target);
    if (detail.install.filename) setFilename(detail.install.filename);
  }, [detail.target, detail.install.filename]);

  useEffect(() => {
    if (recommendation && !detail.install.installed) setFilename(recommendation.filename);
  }, [recommendation, detail.install.installed]);

  // OptiPatcher starts the way the wiki's OptiPatcher column says.
  const patcherRecommended = recommendation?.matched ? recommendation.optipatcher : undefined;
  useEffect(() => {
    if (!detail.install.installed) setOptipatcher(Boolean(patcherRecommended));
  }, [patcherRecommended, detail.install.installed]);

  useEffect(() => {
    void (async () => {
      const value = await currentLaunchOptions(appid);
      setLaunchNow(value);
      setLaunchRead(true);
    })();
  }, [appid, detail.install.installed]);

  // An .asi build is loaded by an ASI loader, so Proton has nothing to shadow.
  const needsNoOverride = filename.toLowerCase().endsWith(".asi");
  // What Steam passes now, with the override for this file name and the
  // entry's arguments (-dx12...) put in, the same as the checklist's install.
  const launchOption = mergeLaunchOptions(
    launchNow,
    needsNoOverride ? [] : [overrideStem(filename)],
    plan?.available ? plan.launch_flags : [],
  );

  const doInstall = async () => {
    setBusy(true);
    try {
      const result = await install(target, filename, preserveIni, optipatcher && !hlx, upscaler);
      if (result.ok) {
        toaster.toast({
          title: hlx ? `HelixSR Scaler(${upscalerLabel(upscaler)})를 설치했습니다` : "OptiScaler를 설치했습니다",
          body: `${target.split("/").slice(-2).join("/")}에 ${filename}`,
        });
        await setGameTarget(detail.path, target);
        // Before anything of ours reaches Steam: what the game was launched
        // with until now is what removing OptiScaler will offer to put back.
        await recordPreviousLaunchOptions(appid, target);
        const missed = optipatcherMissed(result);
        if (missed) {
          toaster.toast({ title: "OptiPatcher는 설치하지 못했습니다", body: missed });
        }
        const left = customMissed(result);
        if (left) {
          toaster.toast({ title: "일부 custom 업스케일러는 받지 못했습니다", body: left });
        }
        await onChanged();
        await offerLaunchOptions();
      } else {
        toaster.toast({ title: "설치하지 못했습니다", body: String(result.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  /**
   * The one thing an install cannot do for itself without being asked.
   * Answered already? Honour that answer and say nothing.
   */
  const offerLaunchOptions = async () => {
    if (!appid || needsNoOverride) return;
    const remembered = await recall(PREF_INSTALL_LAUNCH);
    if (remembered === "never") return;
    if (remembered === "always") {
      applyLaunchOptions();
      return;
    }
    const canRemember = await isRemembering();
    showModal(
      <LaunchOptionsPrompt
        filename={filename}
        launchOption={launchOption}
        canRemember={canRemember}
        onDecide={(apply, rememberIt) => {
          if (rememberIt) void remember(PREF_INSTALL_LAUNCH, apply ? "always" : "never");
          if (apply) applyLaunchOptions();
        }}
      />
    );
  };

  const applyLaunchOptions = () => {
    if (!appid) return;
    if (setLaunchOptions(Number(appid), launchOption)) {
      setLaunchNow(launchOption);
      setLaunchRead(true);
      toaster.toast({ title: "실행 옵션을 설정했습니다", body: launchOption });
    } else {
      toaster.toast({ title: "실행 옵션을 설정할 수 없습니다", body: "Steam에서 직접 설정해야 합니다." });
    }
  };

  return (
    <>
      <PanelSection title="호환성">
        <PanelSectionRow>
          {loadingWiki ? (
            <Notice tone="info">OptiScaler 위키 확인 중…</Notice>
          ) : recommendation?.matched ? (
            <div style={{ padding: "2px 0" }}>
              <div style={{ marginBottom: "6px" }}>
                <Pill color="#3a6ea5">{recommendation.compatibility ?? "?"}</Pill>
                <Pill>{recommendation.game}</Pill>
                {recommendation.optipatcher ? <Pill color="#5b4a85">OptiPatcher</Pill> : null}
              </div>
              <KeyValue
                label="권장 파일"
                value={<Mono>{recommendation.filename}</Mono>}
              />
              <KeyValue label="출처" value={recommendation.filename_source} />
              {recommendation.alternatives.length > 0 ? (
                <KeyValue
                  label="다른 보고"
                  value={recommendation.alternatives.join(", ")}
                />
              ) : null}
              {recommendation.inputs ? (
                <KeyValue label="업스케일러 입력" value={recommendation.inputs} />
              ) : null}
              {recommendation.detail?.["FG Inputs"] ? (
                <KeyValue label="프레임 생성 입력" value={recommendation.detail["FG Inputs"]} />
              ) : null}
              {recommendation.notes ? (
                <Notice tone="info" title="참고">
                  {stripMarkdown(recommendation.notes)}
                </Notice>
              ) : null}
              {recommendation.detail?.["Known Issues"] &&
              recommendation.detail["Known Issues"] !== "-" ? (
                <Notice tone="warn" title="알려진 문제">
                  {stripMarkdown(recommendation.detail["Known Issues"])}
                </Notice>
              ) : null}
            </div>
          ) : recommendation && !recommendation.list_available ? (
            <Notice tone="error" title="호환성 목록을 불러올 수 없습니다">
              {recommendation.list_meta?.error ?? "위키에 연결할 수 없습니다."} 네트워크를
              확인하고 “위키에서 새로 고침”을 누르십시오.
            </Notice>
          ) : (
            <Notice tone="warn" title="자동으로 일치하는 항목이 없습니다">
              {(recommendation?.searched ?? []).map((n) => `“${n}”`).join(", ")} 이름으로 항목{" "}
              {recommendation?.entry_count ?? 0}개를 검색했습니다. 아래에서 게임을 직접
              고르십시오. OptiScaler는 대부분의 DLSS/FSR2+/XeSS 게임에서 작동하며, 보통{" "}
              <Mono>dxgi.dll</Mono> 파일을 고릅니다.
            </Notice>
          )}
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={loadingWiki} onClick={() => void lookup(true)}>
            위키에서 새로 고침
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setSearching((value) => !value)}>
            {searching ? "검색 숨기기" : "목록에서 직접 찾기"}
          </ButtonItem>
        </PanelSectionRow>
        {searching ? (
          <WikiSearch
            initialQuery={detail.name}
            current={detail.wiki_entry}
            onPick={async (entryName) => {
              await setWikiEntry(detail.path, entryName);
              setSearching(false);
              await onChanged();
              await lookup(false);
              toaster.toast({ title: "호환성 항목을 설정했습니다", body: entryName });
            }}
          />
        ) : null}
      </PanelSection>

      <PanelSection title={detail.install.installed ? "설치 정보" : "OptiScaler 설치"}>
        {detail.install.installed ? (
          <PanelSectionRow>
            <div style={{ padding: "2px 0" }}>
              <KeyValue label="설치 파일명" value={<Mono>{detail.install.filename}</Mono>} />
              <KeyValue
                label="OptiScaler"
                value={detail.install.version ?? "알 수 없는 빌드"}
              />
              <KeyValue
                label="관리"
                value={detail.install.managed ? "이 플러그인" : "외부에서 설치됨"}
              />
              <KeyValue label="폴더" value={<Mono>{shorten(detail.install.path)}</Mono>} />
              {detail.install.backed_up.length > 0 ? (
                <KeyValue
                  label="따로 보관한 파일"
                  value={`${detail.install.backup_dir
                    .split("/")
                    .pop()}/에 ${detail.install.backed_up.length}개`}
                />
              ) : null}
              {detail.install.extra_proxies.length > 0 ? (
                <Notice tone="warn" title="중복된 OptiScaler 사본">
                  이 폴더에 {detail.install.extra_proxies.join(", ")}도 있습니다. OptiScaler를
                  두 번 불러오면 게임이 충돌할 수 있습니다. 다시 설치하면 정리됩니다.
                </Notice>
              ) : null}
            </div>
          </PanelSectionRow>
        ) : null}

        {detail.candidates.length > 1 ? (
          <PanelSectionRow>
            <DropdownItem
              label="설치 위치"
              description="OptiScaler는 게임을 렌더링하는 실행 파일과 같은 폴더에 있어야 합니다."
              disabled={busy || detail.install.installed}
              bottomSeparator="standard"
              rgOptions={detail.candidates.map((candidate) => ({
                data: candidate.path,
                label: `${candidate.relative === "." ? "게임 루트" : candidate.relative} (${
                  candidate.executables[0] ?? "실행 파일 없음"
                })`,
              }))}
              selectedOption={target}
              onChange={(selected) => setTarget(String(selected.data))}
            />
          </PanelSectionRow>
        ) : null}

        <PanelSectionRow>
          <DropdownItem
            label="파일 이름 지정"
            description="게임이 불러올 수 있도록 OptiScaler를 이 이름으로 설치합니다."
            disabled={busy}
            bottomSeparator="standard"
            rgOptions={proxies.map((name) => ({
              data: name,
              label:
                recommendation?.matched && name === recommendation.filename
                  ? `${name} — 권장`
                  : name,
            }))}
            selectedOption={filename}
            onChange={(selected) => setFilename(String(selected.data))}
          />
        </PanelSectionRow>

        {detail.install.installed || hlx ? null : (
          <PanelSectionRow>
            <ToggleField
              label={patcherRecommended ? "OptiPatcher도 설치 — 위키 권장" : "OptiPatcher도 설치"}
              description={
                patcherRecommended === false
                  ? `${OPTIPATCHER_UNLISTED} ${OPTIPATCHER_WHY}`
                  : OPTIPATCHER_WHY
              }
              checked={optipatcher}
              disabled={busy}
              bottomSeparator="standard"
              onChange={setOptipatcher}
            />
          </PanelSectionRow>
        )}

        {detail.install.installed ? null : (
          <PanelSectionRow>
            <ToggleField
              label="기존 OptiScaler.ini 유지"
              description="새 설정 파일을 쓰지 않고 이전 설치의 설정을 유지합니다."
              checked={preserveIni}
              disabled={busy}
              bottomSeparator="standard"
              onChange={setPreserveIni}
            />
          </PanelSectionRow>
        )}

        {!detail.install.installed ? (
          <PanelSectionRow>
            <Notice tone="info" title="잃는 파일은 없습니다">
              OptiScaler가 덮어쓸 파일은 게임 자체 DLL을 포함해 모두{" "}
              <Mono>decky_optiscaler_backup_files/</Mono>에 옮겨 두었다가 제거할 때 복원합니다.
            </Notice>
          </PanelSectionRow>
        ) : null}

        {!detail.writable ? (
          <PanelSectionRow>
            <Notice tone="error" title="폴더에 쓸 수 없습니다">
              <Mono>{shorten(target)}</Mono>
            </Notice>
          </PanelSectionRow>
        ) : null}

        <PanelSectionRow>
          {/* Which build an install or a reinstall puts in. A game keeps the
              one it was installed from until it is installed again. */}
          <KeyValue
            label="설치 버전"
            value={
              hlx
                ? `HelixSR Scaler — ${upscalerLabel(upscaler)} (HelixSR Desktop 빌드)`
                : status?.optiscaler_version
                  ? `OptiScaler ${status.optiscaler_version}`
                  : "최신 OptiScaler nightly (지금 다운로드)"
            }
          />
        </PanelSectionRow>

        {blocked ? (
          <PanelSectionRow>
            <Notice tone="warn" title={`${upscalerLabel(upscaler)}를 지금은 설치할 수 없습니다`}>
              {blocked}
            </Notice>
          </PanelSectionRow>
        ) : null}

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || !detail.writable || Boolean(blocked)}
            onClick={doInstall}
          >
            {busy
              ? "작업 중…"
              : detail.install.installed
                ? detail.install.filename === filename
                  ? `${filename}로 다시 설치`
                  : `${filename}로 전환`
                : `${filename}로 설치`}
          </ButtonItem>
        </PanelSectionRow>

      </PanelSection>

      {detail.install.installed && detail.install.engine !== "helixsr" ? (
        <OptipatcherPanel targetDir={detail.install.path} recommended={patcherRecommended} />
      ) : detail.install.installed ? (
        <PanelSection title="OptiPatcher">
          <PanelSectionRow>
            <Notice tone="info" title="HelixSR Scaler에 들어 있는 OptiPatcher 사용">
              HelixSR Scaler는 자체 OptiPatcher를 함께 싣고 켭니다. 이 게임에는 그 사본을 그대로
              쓰며, HelixSR를 업데이트하면 함께 바뀝니다.
            </Notice>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      <PanelSection title="Steam 실행 옵션">
        <PanelSectionRow>
          <Notice tone={needsNoOverride ? "info" : "warn"}>
            {needsNoOverride ? (
              <><Mono>.asi</Mono> 빌드는 ASI 로더가 불러오므로 오버라이드가 필요 없습니다.</>
            ) : (
              <>
                이 오버라이드를 추가하지 않으면 Proton이 자체 <Mono>{filename}</Mono> 파일을
                불러옵니다:
                <div style={{ marginTop: "6px" }}>
                  <Mono>{launchOption}</Mono>
                </div>
              </>
            )}
          </Notice>
        </PanelSectionRow>
        {appid ? (
          <PanelSectionRow>
            <Focusable
              focusWithinClassName="gpfocuswithin"
              style={{ padding: "2px 0", width: "100%" }}
            >
              <KeyValue
                label="현재 Steam 설정"
                value={
                  !launchRead ? (
                    "읽는 중…"
                  ) : launchNow === null ? (
                    "Steam에서 읽을 수 없음"
                  ) : launchNow === "" ? (
                    "없음"
                  ) : (
                    <Mono>{launchNow}</Mono>
                  )
                }
              />
              {/* What removing OptiScaler would be able to put back. Absent on
                  installs made before this was recorded, and on games where no
                  source could read the field at the time. */}
              <KeyValue
                label="설치 전"
                value={
                  !detail.install.installed
                    ? "—"
                    : detail.install.launch_record?.recorded
                      ? detail.install.launch_record.value
                        ? <Mono>{detail.install.launch_record.value}</Mono>
                        : "없음"
                      : "기록 없음"
                }
              />
            </Focusable>
          </PanelSectionRow>
        ) : null}
        {appid && !needsNoOverride ? (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={applyLaunchOptions}>
              실행 옵션 자동 설정
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
        {!appid ? (
          <PanelSectionRow>
            <Focusable style={{ fontSize: "12px", opacity: 0.7, padding: "4px 0" }}>
              사용자 지정 폴더에서 찾은 게임이므로, 게임을 실행하는 런처에서 오버라이드를 직접
              추가해야 합니다.
            </Focusable>
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    </>
  );
}

function shorten(path: string, keep = 3) {
  const parts = path.split("/").filter(Boolean);
  return parts.length <= keep ? path : `…/${parts.slice(-keep).join("/")}`;
}

/** The wiki cells contain markdown links and AsciiDoc markup. */
function stripMarkdown(text: string) {
  return text
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\+\+\+<\/?s>\+\+\+/g, "")
    .replace(/[`*_]/g, "")
    .replace(/<br\s*\/?>/gi, " ")
    .trim();
}
