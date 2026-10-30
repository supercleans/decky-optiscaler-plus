import {
  ButtonItem,
  Field,
  PanelSection,
  PanelSectionRow,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import {
  getHelixsrStatus,
  getPdPluginStatus,
  getPref,
  getWikiStatus,
  listAllGames,
  refreshWiki,
  updateInstalledGames,
} from "../api";
import { usePluginUpdate } from "../hooks/usePluginUpdate";
import {
  REMEMBERED_QUESTIONS,
  forget,
  isRemembering,
  setRemembering,
} from "../prefs";
import type {
  Game,
  GameUpdateResult,
  HelixsrStatus,
  PayloadStatus,
  PdPluginStatus,
  WikiStatus,
} from "../types";
import { Centered, KeyValue, Mono, Notice, Pill } from "./Common";
import { ChannelVersions } from "./ChannelVersions";
import { PdPluginGuide } from "./PdPluginGuide";
import { HelixsrGuide } from "./UpscalerPanel";
import { ComponentsSection } from "./Components";

/** How old the list is, in the terms someone would actually ask it in. */
function describeAge(age: number | null): string {
  if (age === null) return "알 수 없는 시점";
  const hours = age / 3600;
  if (hours < 1) return "1시간 이내";
  if (hours < 48) return `${Math.round(hours)}시간 전`;
  return `${Math.round(hours / 24)}일 전`;
}

/** A release's ISO date, as a date. */
function describeDate(iso: string | null): string {
  if (!iso) return "—";
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleDateString();
}

/**
 * The plugin's own settings, as opposed to one game's.
 *
 * It exists for one reason: two prompts here offer "Remember my choice", and an
 * answer that can only be given and never taken back is a trap. Whatever is
 * remembered is listed by name with what it will do, each with a way to forget
 * it, plus the switch that stops answers being kept at all.
 *
 * Deliberately not in the Quick Access panel. That panel drives the game that
 * is running; this changes how the plugin behaves for every game, which is not
 * something to be reached for mid-session by accident.
 */
export function SettingsTab({ status }: Readonly<{ status: PayloadStatus | null }>) {
  const [remembering, setRememberingState] = useState<boolean | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [wiki, setWiki] = useState<WikiStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const plugin = usePluginUpdate();
  /** Games this plugin set up, for counting the ones on an older nightly. */
  const [managed, setManaged] = useState<Game[] | null>(null);
  const [updatingGames, setUpdatingGames] = useState(false);
  const [updated, setUpdated] = useState<GameUpdateResult[] | null>(null);
  /** PDPerfPlugin.dll, which the user supplies for the pd-upscaler games. */
  const [pdPlugin, setPdPlugin] = useState<PdPluginStatus | null>(null);
  const [checkingPd, setCheckingPd] = useState(false);
  const recheckPd = useCallback(async () => {
    setCheckingPd(true);
    try {
      setPdPlugin(await getPdPluginStatus());
    } catch {
      setPdPlugin(null);
    } finally {
      setCheckingPd(false);
    }
  }, []);
  useEffect(() => {
    void recheckPd();
  }, [recheckPd]);
  /** HelixSR Desktop's build, which HLX DLSS and HLX FSR 4 are installed from. */
  const [helixsr, setHelixsr] = useState<HelixsrStatus | null>(null);
  const [checkingHelixsr, setCheckingHelixsr] = useState(false);
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
    void recheckHelixsr();
  }, [recheckHelixsr]);

  const load = useCallback(async () => {
    const enabled = await isRemembering();
    const stored: Record<string, unknown> = {};
    for (const question of REMEMBERED_QUESTIONS) {
      try {
        const { value } = await getPref(question.key);
        if (value !== null && value !== undefined) stored[question.key] = value;
      } catch {
        /* an unreadable preference is one that is not remembered */
      }
    }
    setRememberingState(enabled);
    setAnswers(stored);
    try {
      const games = await listAllGames();
      setManaged((Array.isArray(games) ? games : []).filter((g) => g.installed && g.managed));
    } catch {
      setManaged([]);
    }
    try {
      setWiki(await getWikiStatus(false));
    } catch (exc) {
      setWiki({
        url: "", entry_count: 0, available: false, source: null, fetched_at: null,
        age: null, stale: true, revision: "", revalidating: false, last_attempt: null,
        error: String(exc), tls: null, cache_path: "",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const changeRemembering = async (enabled: boolean) => {
    setBusy(true);
    try {
      await setRemembering(enabled);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    setRefreshing(true);
    try {
      const result = await refreshWiki();
      setWiki(await getWikiStatus(false));
      toaster.toast({
        title: result.count > 0 ? "호환성 목록을 다운로드했습니다" : "여전히 다운로드할 수 없습니다",
        body: result.count > 0
          ? `항목 ${result.count}개.`
          : String(result.meta?.error ?? "위키에 연결할 수 없습니다."),
      });
    } catch (exc) {
      toaster.toast({ title: "여전히 다운로드할 수 없습니다", body: String(exc) });
    } finally {
      setRefreshing(false);
    }
  };

  /**
   * Install the downloaded nightly again in every game on an older one, the
   * way each game's own page would. Running games are skipped.
   */
  const updateGames = async () => {
    setUpdatingGames(true);
    setUpdated(null);
    try {
      const result = await updateInstalledGames();
      if (!result.ok) {
        toaster.toast({ title: "게임을 업데이트할 수 없습니다", body: String(result.error) });
        return;
      }
      setUpdated(result.results);
      const done = result.results.filter((r) => r.ok).length;
      toaster.toast({
        title: done === result.results.length ? "게임을 업데이트했습니다" : "일부 게임을 업데이트하지 못했습니다",
        body: `${result.results.length}개 중 ${done}개 게임을 업데이트했습니다.`,
      });
      await load();
    } catch (exc) {
      toaster.toast({ title: "게임을 업데이트할 수 없습니다", body: String(exc) });
    } finally {
      setUpdatingGames(false);
    }
  };

  const forgetOne = async (key: string) => {
    setBusy(true);
    try {
      await forget(key);
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (remembering === null) return <Centered>설정을 읽는 중…</Centered>;

  const stored = REMEMBERED_QUESTIONS.filter((question) => question.key in answers);
  // Judged by the backend against the build each game's upscaler uses: the
  // nightly for FSR 4 Lite, HelixSR Desktop's build for HLX. A game with no tag
  // was set up before tags were recorded, which is older still.
  const outdated = (managed ?? []).filter(
    (game) => game.outdated || game.optipatcher_outdated
  );
  const patcher = status?.optipatcher;
  const update = plugin.update;

  return (
    <>
      <PanelSection title="플러그인">
        <PanelSectionRow>
          {update?.update_available ? (
            <Notice tone="info" title={`${update.latest} 버전이 나왔습니다`}>
              현재 버전은 {update.current}입니다. Decky가 다운로드해 릴리스의 SHA-256으로
              검증하고, 설치 전에 확인을 요청한 뒤 플러그인을 다시 불러옵니다.
            </Notice>
          ) : (
            <Notice tone={update?.error ? "warn" : "success"} title={`버전 ${update?.current ?? "…"}`}>
              {update === null
                ? "새 릴리스를 확인하는 중…"
                : update.error
                  ? <>새 릴리스를 확인할 수 없습니다: <Mono>{update.error}</Mono></>
                  : "최신 릴리스입니다."}
            </Notice>
          )}
        </PanelSectionRow>
        {update?.update_available ? (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={plugin.installing} onClick={() => void plugin.install()}>
              {plugin.installing ? "업데이트를 시작하는 중…" : `${update.latest} 버전으로 업데이트`}
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={plugin.checking} onClick={() => void plugin.check(true)}>
            {plugin.checking ? "확인 중…" : "업데이트 확인"}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field bottomSeparator="none" focusable>
            <div style={{ width: "100%" }}>
              <KeyValue
                label="마지막 확인"
                value={update ? new Date(update.checked_at * 1000).toLocaleString() : "아직 없음"}
              />
              <KeyValue label="릴리스" value={<Mono>{update?.page ?? "—"}</Mono>} />
            </div>
          </Field>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="기억한 선택">
        <PanelSectionRow>
          <ToggleField
            label="선택 기억"
            description={
              remembering
                ? "“이 선택 기억”이 있는 질문은 선택을 저장하고 더 이상 묻지 않습니다."
                : "매번 다시 묻고 아무것도 저장하지 않습니다."
            }
            checked={remembering}
            disabled={busy}
            bottomSeparator="standard"
            onChange={(checked) => void changeRemembering(checked)}
          />
        </PanelSectionRow>

        {stored.length === 0 ? (
          <PanelSectionRow>
            <Notice tone="info">
              {remembering
                ? "아직 기억한 선택이 없습니다. 실행 옵션 질문에서 이 선택을 기억할 수 있습니다."
                : "이 기능을 끄면서 저장된 선택도 지웠습니다."}
            </Notice>
          </PanelSectionRow>
        ) : (
          stored.map((question) => (
            <PanelSectionRow key={question.key}>
              <Field
                label={question.title}
                description={question.describe(answers[question.key])}
                onClick={() => void forgetOne(question.key)}
                onActivate={() => void forgetOne(question.key)}
                focusable={!busy}
                bottomSeparator="standard"
                childrenLayout="inline"
                childrenContainerWidth="min"
                {...({ "data-forget": question.key } as Record<string, string>)}
              >
                <Pill>다시 묻기</Pill>
              </Field>
            </PanelSectionRow>
          ))
        )}
      </PanelSection>

      <PanelSection title="호환성 목록">
        <PanelSectionRow>
          {wiki === null ? (
            <Notice tone="info">OptiScaler 위키 확인 중…</Notice>
          ) : wiki.available ? (
            // Available and *current* are different questions now that answers
            // come from cache: a list can be perfectly usable and months old,
            // and a refresh can be failing behind it without anything breaking.
            <Notice
              tone={wiki.error ? "warn" : "success"}
              title={`목록의 게임 ${wiki.entry_count}개`}
            >
              {wiki.source === "bundled"
                ? "플러그인에 포함된 사본입니다. 이 Deck에서는 아직 다운로드하지 않았습니다."
                : `${describeAge(wiki.age)}에 다운로드했습니다.`}
              {wiki.error ? (
                <>
                  {" "}
                  마지막 새로 고침이 실패해 그동안 이 목록을 사용합니다.{" "}
                  <Mono>{wiki.error}</Mono>
                </>
              ) : wiki.revalidating ? (
                " 지금 새 목록을 확인하는 중입니다."
              ) : (
                ""
              )}
            </Notice>
          ) : (
            // The sentence the rest of the plugin could never show: when the
            // list will not download, every game reads as "not in the list",
            // and without the actual error there is nothing to act on.
            <Notice tone="error" title="호환성 목록을 다운로드할 수 없습니다">
              자동 설치에는 이 목록이 필요합니다. 목록이 없으면 모든 게임에 위키 항목이 없는
              것처럼 보입니다. {wiki.error ? <Mono>{wiki.error}</Mono> : null}
            </Notice>
          )}
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={refreshing}
            onClick={() => void refresh()}
          >
            {refreshing ? "다운로드 중…" : "다시 다운로드"}
          </ButtonItem>
        </PanelSectionRow>
        {wiki && (!wiki.available || wiki.error) ? (
          <PanelSectionRow>
            <Field bottomSeparator="none" focusable>
              <div style={{ width: "100%" }}>
                <KeyValue label="주소" value={<Mono>{wiki.url}</Mono>} />
                <KeyValue label="인증서" value={wiki.tls ?? "모두 실패"} />
                <KeyValue
                  label="마지막 시도"
                  value={
                    wiki.last_attempt
                      ? new Date(wiki.last_attempt * 1000).toLocaleString()
                      : "아직 없음"
                  }
                />
              </div>
            </Field>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <PanelSection title="OptiScaler">
        <PanelSectionRow>
          {status?.archive_present ? (
            <Notice tone={status.error ? "warn" : "success"} title={`OptiScaler ${status.version}`}>
              Nightly <Mono>{status.tag}</Mono>, {describeDate(status.published_at)} 출시.
              새로 설치할 때 이 빌드를 사용하며, 이미 설치한 게임은 다시 설치할 때까지 기존
              빌드를 유지합니다. 새 빌드는 아래 <b>받은 파일</b>에서 업데이트합니다.
            </Notice>
          ) : (
            <Notice tone="warn" title="OptiScaler가 없습니다">
              아래 <b>받은 파일</b>에서 OptiScaler nightly를 받으세요.
            </Notice>
          )}
        </PanelSectionRow>
        {outdated.length > 0 ? (
          <>
            <PanelSectionRow>
              <Notice tone="info" title={`이전 빌드를 쓰는 게임 ${outdated.length}개`}>
                {outdated.map((game) => game.name).join(", ")}. 업데이트하면 FSR 4 Lite 게임에는{" "}
                <Mono>{status?.tag ?? "받아 둔 nightly"}</Mono> 빌드와 최신 OptiPatcher를, HLX DLSS
                게임에는 지금 쓰는 HelixSR 빌드를 설치하고 파일 이름, 설정, 업스케일러, OptiPatcher
                사용 여부는 유지합니다. 실행 중인 게임은 건너뜁니다.
              </Notice>
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={updatingGames} onClick={() => void updateGames()}>
                {updatingGames
                  ? "업데이트 중…"
                  : `게임 ${outdated.length}개 업데이트`}
              </ButtonItem>
            </PanelSectionRow>
          </>
        ) : null}
        {updated && updated.some((r) => !r.ok) ? (
          <PanelSectionRow>
            <Notice tone="warn" title="업데이트하지 못했습니다">
              {updated
                .filter((r) => !r.ok)
                .map((r) => `${r.name}: ${r.error ?? "실패"}`)
                .join(" · ")}
            </Notice>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <Field bottomSeparator="none" focusable>
            <div style={{ width: "100%" }}>
              <KeyValue
                label="마지막 확인"
                value={
                  status?.checked_at
                    ? new Date(status.checked_at * 1000).toLocaleString()
                    : "아직 없음"
                }
              />
              <KeyValue label="릴리스" value={<Mono>{status?.release_page ?? "—"}</Mono>} />
              <KeyValue
                label="OptiPatcher"
                value={
                  patcher?.label ?? "아직 다운로드하지 않음 (켜는 게임의 첫 설치 때 받음)"
                }
              />
              <KeyValue label="기본 프록시" value={status?.default_proxy ?? "—"} />
            </div>
          </Field>
        </PanelSectionRow>
      </PanelSection>

      {/* What the plugin downloaded, its updates, and removing it all. */}
      <ComponentsSection />

      {/* Which OptiScaler nightly and cyboman build installs download. A
          changed nightly pin changes which games count as on an older build. */}
      <ChannelVersions onChanged={() => void load()} />

      {/* HLX DLSS comes from HelixSR Desktop's build, else the one built here. */}
      <PanelSection title="HelixSR (HLX DLSS)">
        <HelixsrGuide
          helixsr={helixsr}
          busy={checkingHelixsr}
          onRecheck={() => void recheckHelixsr()}
        />
      </PanelSection>

      {/* Resident Evil 2/3/4/7/8 and Devil May Cry 5 through REFramework's
          pd-upscaler branch: they need this file, and the user has to bring it. */}
      {pdPlugin ? (
        <PanelSection title="PDPerfPlugin (pd-upscaler 게임용)">
          <PdPluginGuide
            name={pdPlugin.name}
            build={pdPlugin.build}
            url={pdPlugin.url}
            folder={pdPlugin.folder}
            present={pdPlugin.present}
            verified={pdPlugin.verified}
            busy={checkingPd}
            onRecheck={() => void recheckPd()}
          />
        </PanelSection>
      ) : null}
    </>
  );
}
