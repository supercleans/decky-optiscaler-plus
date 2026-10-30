import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import {
  getPdPluginStatus,
  getPdUploadStatus,
  importPdPlugin,
  startPdUpload,
  stopPdUpload,
} from "../api";
import type { PdUploadStatus } from "../types";
import { Mono, Notice } from "./Common";
import { QrCode } from "./QrCode";

/** How often the open upload page is asked whether the file has arrived. */
const UPLOAD_POLL_MS = 2000;
/** FileSelectionType.FILE: a const enum in @decky/api, so not importable as a value. */
const PICK_FILE = 0;

/**
 * Where to get PDPerfPlugin.dll and how to get it onto the Deck, with whether
 * it is here.
 *
 * The pd-upscaler games do not upscale without it, and this plugin may not
 * redistribute it, so the user brings it, by whichever of three ways suits:
 *
 * - from a phone, without leaving Game Mode: one QR code opens the Nexus Mods
 *   page to download it on the phone, and a second opens a page on the Deck's
 *   own address to send it over the same Wi-Fi;
 * - from an SD card or USB drive, picked with Decky's file picker;
 * - by leaving it in the Downloads folder, which "check again" looks through.
 */
export function PdPluginGuide({
  name,
  build,
  url,
  folder,
  present,
  verified,
  busy,
  onRecheck,
}: Readonly<{
  name: string;
  build: string;
  url: string;
  folder: string;
  present: boolean;
  verified: boolean;
  busy?: boolean;
  onRecheck: () => void;
}>) {
  const [phoneStep, setPhoneStep] = useState<0 | 1 | 2>(0);
  const [picking, setPicking] = useState(false);

  const pick = async () => {
    setPicking(true);
    try {
      const status = await getPdPluginStatus();
      const chosen = await openFilePicker(PICK_FILE as never, status.picker_start ?? "/", true, true);
      if (!chosen?.realpath && !chosen?.path) return;
      const result = await importPdPlugin(chosen.realpath || chosen.path);
      toaster.toast(
        result.ok
          ? { title: `${name}을(를) 가져왔습니다`, body: result.message ?? "" }
          : { title: `${name}을(를) 가져올 수 없습니다`, body: String(result.error) }
      );
      if (result.ok) onRecheck();
    } catch (exc) {
      // Cancelling the picker lands here too; that is not worth a toast.
      if (String(exc).toLowerCase().includes("cancel")) return;
      toaster.toast({ title: `${name}을(를) 가져올 수 없습니다`, body: String(exc) });
    } finally {
      setPicking(false);
    }
  };

  return (
    <>
      <PanelSectionRow>
        {present && verified ? (
          <Notice tone="success" title={`${name} 있음`}>
            {build} 파일을 찾았습니다. pd-upscaler 게임에 REFramework와 함께 설치합니다.
          </Notice>
        ) : present ? (
          <Notice tone="warn" title={`${name} 있음 — 다른 버전`}>
            찾은 파일이 위키가 지정한 {build}와 다릅니다. 그대로 설치하지만, 1.2.0은 백엔드를
            불러오지 못해 업스케일이 되지 않습니다. 아래 방법으로 {build}를 다시 가져와 주세요.
          </Notice>
        ) : (
          <Notice tone="warn" title={`${name} 없음 — 직접 받아야 합니다`}>
            저작권 때문에 이 플러그인에 포함할 수 없는 파일입니다. <Mono>{url}</Mono>의 Files
            탭에서 {build}를 받아(Nexus Mods 로그인 필요, 1.2.0은 동작하지 않음) 아래 방법 중
            하나로 스팀덱에 가져오세요. zip·7z 파일 그대로 가져와도 됩니다.
          </Notice>
        )}
      </PanelSectionRow>

      {phoneStep === 0 ? (
        <>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={busy}
              description="데스크톱 모드 없이, 같은 Wi-Fi의 휴대폰으로 받아 바로 보냅니다."
              onClick={() => setPhoneStep(1)}
            >
              휴대폰으로 받아서 보내기
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={busy || picking}
              description="PC에서 받아 SD 카드나 USB 메모리에 넣었다면 여기서 고르세요."
              onClick={() => void pick()}
            >
              {picking ? "가져오는 중…" : "파일 선택 (SD 카드·USB)"}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={busy}
              description={`${folder}에 넣어 두었다면(하위 폴더도 됨) 찾아서 가져옵니다.`}
              onClick={onRecheck}
            >
              {busy ? "확인 중…" : "다시 확인"}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : phoneStep === 1 ? (
        <NexusStep
          url={url}
          build={build}
          onNext={() => setPhoneStep(2)}
          onClose={() => setPhoneStep(0)}
        />
      ) : (
        <SendStep
          name={name}
          onBack={() => setPhoneStep(1)}
          onDone={() => {
            setPhoneStep(0);
            onRecheck();
          }}
          onClose={() => setPhoneStep(0)}
        />
      )}
    </>
  );
}

/** Step 1 of 2: the Nexus Mods page, on the phone. */
function NexusStep({
  url,
  build,
  onNext,
  onClose,
}: Readonly<{ url: string; build: string; onNext: () => void; onClose: () => void }>) {
  const filesTab = `${url}?tab=files`;
  return (
    <>
      <PanelSectionRow>
        <Notice tone="info" title="1/2 · 휴대폰으로 Nexus Mods 열기">
          휴대폰 카메라로 아래 QR 코드를 찍어 Nexus Mods 페이지를 엽니다. 로그인한 뒤 Files
          탭에서 <b>{build}</b>를 휴대폰에 받으세요(1.2.0은 동작하지 않습니다). 받았으면 “다음”을
          누르세요.
        </Notice>
      </PanelSectionRow>
      <PanelSectionRow>
        <QrCode text={filesTab} />
        <div style={{ textAlign: "center", fontSize: "11px", opacity: 0.7 }}>
          <Mono>{filesTab}</Mono>
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onNext}>
          다음: 스팀덱으로 보내기
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onClose}>
          닫기
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}

/**
 * Step 2 of 2: a page on the Deck that the phone sends the file to.
 *
 * Opened when this step is shown and closed when it is left, so the page is
 * never up longer than someone is looking at its QR code.
 */
function SendStep({
  name,
  onBack,
  onDone,
  onClose,
}: Readonly<{ name: string; onBack: () => void; onDone: () => void; onClose: () => void }>) {
  const [upload, setUpload] = useState<PdUploadStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const done = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const now = await getPdUploadStatus();
        if (cancelled) return;
        setUpload(now);
        if (now.result?.ok) {
          done.current = true;
          toaster.toast({ title: `${name}을(를) 받았습니다`, body: now.result.message });
          onDone();
          return;
        }
        if (now.active) timer = setTimeout(() => void poll(), UPLOAD_POLL_MS);
      } catch (exc) {
        if (!cancelled) setError(String(exc));
      }
    };
    void (async () => {
      try {
        const opened = await startPdUpload();
        if (cancelled) return;
        if (!opened.ok) {
          setError(String(opened.error));
          return;
        }
        setUpload(opened);
        timer = setTimeout(() => void poll(), UPLOAD_POLL_MS);
      } catch (exc) {
        if (!cancelled) setError(String(exc));
      }
    })();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      if (!done.current) void stopPdUpload();
    };
    // Opened once per visit to this step, whatever the callbacks do meanwhile.
  }, []);

  const expired = upload !== null && !upload.active && !upload.result?.ok;
  return (
    <>
      <PanelSectionRow>
        <Notice tone="info" title="2/2 · 휴대폰에서 스팀덱으로 보내기">
          휴대폰이 스팀덱과 <b>같은 Wi-Fi</b>에 연결된 상태에서 아래 QR 코드를 찍으세요. 열린
          페이지에서 방금 받은 파일(zip·7z 그대로 또는 {name})을 골라 보내면 됩니다. 10분이
          지나거나 파일을 받으면 페이지는 닫힙니다.
        </Notice>
      </PanelSectionRow>
      {error ? (
        <PanelSectionRow>
          <Notice tone="error" title="전송 페이지를 열 수 없습니다">
            {error}
          </Notice>
        </PanelSectionRow>
      ) : expired ? (
        <PanelSectionRow>
          <Notice tone="warn" title="전송 페이지가 닫혔습니다">
            시간이 지나 닫혔습니다. “이전”을 눌렀다가 다시 “다음”을 누르면 새로 열립니다.
          </Notice>
        </PanelSectionRow>
      ) : upload?.url ? (
        <PanelSectionRow>
          <QrCode text={upload.url} />
          <div style={{ textAlign: "center", fontSize: "11px", opacity: 0.7 }}>
            <Mono>{upload.url}</Mono>
          </div>
          {upload.result && !upload.result.ok ? (
            <Notice tone="warn" title="받지 못했습니다">
              {upload.result.message}
            </Notice>
          ) : null}
        </PanelSectionRow>
      ) : (
        <PanelSectionRow>
          <Notice tone="info">전송 페이지를 여는 중…</Notice>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onBack}>
          이전: Nexus Mods QR
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onClose}>
          닫기
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
