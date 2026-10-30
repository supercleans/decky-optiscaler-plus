import { ButtonItem, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { clearLog, getMonitor, setLogging } from "../api";
import type { MonitorReport } from "../types";
import { KeyValue, Mono, Notice, Pill } from "./Common";

const REFRESH_MS = 3000;

/** Pill text for each log level; the level itself stays the backend's key. */
const LEVEL_LABELS: Record<string, string> = {
  error: "오류",
  critical: "치명적",
  warning: "경고",
  info: "정보",
  debug: "디버그",
  trace: "추적",
};

/** Labels for the `configured` keys monitor.py reports. */
const CONFIGURED_LABELS: Record<string, string> = {
  fg_enabled: "프레임 생성 사용",
  fg_input: "프레임 생성 입력",
  fg_output: "프레임 생성 출력",
  dx11_upscaler: "DX11 업스케일러",
  dx12_upscaler: "DX12 업스케일러",
  vulkan_upscaler: "Vulkan 업스케일러",
  framerate_limit: "프레임 제한",
  output_scaling: "출력 스케일링",
  sharpness_override: "선명도 지정",
};

const LEVEL_COLORS: Record<string, string> = {
  error: "#e05c5c",
  critical: "#e05c5c",
  warning: "#e8a33d",
  info: "#9fb4c7",
  debug: "#7d8b99",
  trace: "#6b7681",
};

export function MonitorTab({
  targetDir,
  running,
}: {
  targetDir: string;
  /** Polled only while the game is up: nothing writes the log otherwise. */
  running: boolean;
}) {
  const [report, setReport] = useState<MonitorReport | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      setReport(await getMonitor(targetDir));
    } catch {
      /* the game may be mid-write; the next tick will pick it up */
    }
  }, [targetDir]);

  useEffect(() => {
    void refresh();
    if (!running) return;
    timer.current = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [refresh, running]);

  if (!report) {
    return (
      <PanelSection title="모니터링">
        <PanelSectionRow>
          <Notice tone="info">OptiScaler 로그를 읽는 중…</Notice>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const loggingOn = report.logging_enabled === "true";
  const state = report.state ?? {};
  const problems = report.problems ?? [];

  return (
    <>
      <PanelSection title="모니터링">
        <PanelSectionRow>
          <ToggleField
            label="OptiScaler 로그 기록"
            description="모니터링은 OptiScaler.log를 읽습니다. 켜면 다음 게임 실행부터 적용됩니다."
            checked={loggingOn}
            disabled={busy}
            bottomSeparator="standard"
            onChange={async (checked) => {
              setBusy(true);
              await setLogging(targetDir, checked);
              await refresh();
              setBusy(false);
            }}
          />
        </PanelSectionRow>

        {!report.log_present ? (
          <PanelSectionRow>
            <Notice tone="warn" title="아직 로그가 없습니다">
              {loggingOn
                ? "로그 기록이 켜져 있습니다. 게임을 한 번 실행하면 실행 정보가 여기에 표시됩니다."
                : "위에서 로그 기록을 켠 뒤 게임을 실행하면 OptiScaler가 실제로 불러온 항목을 볼 수 있습니다."}
            </Notice>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      {report.log_present ? (
        <>
          <PanelSection title="실행 중 감지됨">
            <PanelSectionRow>
              <div style={{ padding: "2px 0" }}>
                <KeyValue label="사용 중인 업스케일러" value={state.upscaler ?? "—"} />
                <KeyValue
                  label="프레임 생성"
                  value={
                    report.frame_generation.length > 0
                      ? report.frame_generation.join(", ")
                      : "감지 안 됨"
                  }
                />
                <KeyValue label="불러온 파일" value={state.proxy ? <Mono>{state.proxy}</Mono> : "—"} />
                <KeyValue label="GPU" value={state.gpu ?? "—"} />
                <KeyValue label="게임" value={state.game_name ?? "—"} />
                <KeyValue label="실행 파일" value={state.game_exe ? <Mono>{state.game_exe}</Mono> : "—"} />
                <KeyValue label="게임 버전" value={state.game_version ?? "—"} />
                <KeyValue label="Wine/Proton" value={state.wine ?? "—"} />
                <KeyValue
                  label="로그 갱신"
                  value={
                    report.log_modified
                      ? new Date(report.log_modified * 1000).toLocaleTimeString()
                      : "—"
                  }
                />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="설정값 (다음 실행)">
            <PanelSectionRow>
              <div style={{ padding: "2px 0" }}>
                {Object.entries(report.configured ?? {}).map(([key, value]) => (
                  <KeyValue key={key} label={CONFIGURED_LABELS[key] ?? prettyKey(key)} value={value} />
                ))}
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="로그 상태">
            <PanelSectionRow>
              <div style={{ padding: "4px 0" }}>
                {Object.entries(report.counts ?? {})
                  .filter(([, count]) => count > 0)
                  .map(([level, count]) => (
                    <Pill key={level} color={LEVEL_COLORS[level]}>
                      {LEVEL_LABELS[level] ?? level} {count}
                    </Pill>
                  ))}
                <div style={{ fontSize: "12px", opacity: 0.6, marginTop: "6px" }}>
                  {(report.log_size / 1024).toFixed(0)} KB · {report.total_lines ?? 0}줄 읽음
                </div>
              </div>
            </PanelSectionRow>
          </PanelSection>

          {(report.hints ?? []).length > 0 ? (
            <PanelSection title="로그 진단">
              {report.hints.map((hint, index) => (
                <PanelSectionRow key={index}>
                  <Notice tone="warn">{hint}</Notice>
                </PanelSectionRow>
              ))}
            </PanelSection>
          ) : null}

          {problems.length > 0 ? (
            <PanelSection title="경고 및 오류">
              <PanelSectionRow>
                <LogList entries={problems} />
              </PanelSectionRow>
            </PanelSection>
          ) : null}

          <PanelSection title="최근 로그">
            <PanelSectionRow>
              <LogList entries={(report.recent ?? []).slice(-40)} />
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  await clearLog(targetDir);
                  await refresh();
                  setBusy(false);
                }}
              >
                로그 파일 지우기
              </ButtonItem>
            </PanelSectionRow>
          </PanelSection>
        </>
      ) : null}
    </>
  );
}

function LogList({ entries }: { entries: MonitorReport["recent"] }) {
  return (
    <div
      style={{
        maxHeight: "260px",
        overflowY: "auto",
        background: "rgba(0,0,0,0.25)",
        borderRadius: "3px",
        padding: "6px 8px",
        fontFamily: "monospace",
        fontSize: "11px",
        lineHeight: 1.4,
      }}
    >
      {entries.length === 0 ? (
        <div style={{ opacity: 0.5 }}>기록된 내용이 없습니다.</div>
      ) : (
        entries.map((entry, index) => (
          <div key={index} style={{ color: LEVEL_COLORS[entry.level] ?? "#c8d3dd" }}>
            {entry.time ? <span style={{ opacity: 0.5 }}>{entry.time} </span> : null}
            {entry.message}
          </div>
        ))
      )}
    </div>
  );
}

function prettyKey(key: string) {
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
