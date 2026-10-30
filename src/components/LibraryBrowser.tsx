import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { addCustomLibrary, listLibraries, removeCustomLibrary } from "../api";
import type { Library } from "../types";
import { Centered, Mono, Notice, Pill, RowButton } from "./Common";

/**
 * `FileSelectionType.FOLDER`. Spelled out rather than imported: it is a
 * `const enum`, which the bundler cannot inline across module boundaries.
 */
const SELECT_FOLDER = 1;

/**
 * Where games are looked for.
 *
 * Steam's own library folders are found automatically; this is for the rest —
 * games on a drive Steam does not know about, or non-Steam installs. Browsing
 * the games themselves lives in the games list, not here.
 */
export function LibraryBrowser() {
  const [libraries, setLibraries] = useState<Library[] | null>(null);
  const [busy, setBusy] = useState(false);

  const loadLibraries = useCallback(async () => {
    try {
      setLibraries(await listLibraries());
    } catch {
      setLibraries([]);
    }
  }, []);

  useEffect(() => {
    void loadLibraries();
  }, [loadLibraries]);

  const addFolder = async () => {
    setBusy(true);
    try {
      // Decky's own picker: it knows about the Deck's mount points and reads
      // the filesystem from the plugin host, so the SD card is reachable.
      const picked = await openFilePicker(SELECT_FOLDER, "/home/deck", false, true);
      if (!picked?.path) return;
      const result = await addCustomLibrary(picked.path);
      if (result.ok) {
        toaster.toast({ title: "라이브러리를 추가했습니다", body: picked.path });
        await loadLibraries();
      } else {
        toaster.toast({ title: "추가할 수 없습니다", body: String(result.error) });
      }
    } catch {
      /* the picker was dismissed */
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PanelSection title="게임 라이브러리">
        {libraries === null ? (
          <Centered>Steam 라이브러리를 찾는 중…</Centered>
        ) : libraries.length === 0 ? (
          <PanelSectionRow>
            <Notice tone="warn" title="라이브러리를 찾지 못했습니다">
              Steam 라이브러리 폴더를 찾지 못했습니다. 아래에서 폴더를 직접 추가하세요.
            </Notice>
          </PanelSectionRow>
        ) : (
          libraries.map((library) => (
            <RowButton
              key={library.path}
              label={library.name}
              description={
                library.available ? <Mono>{library.path}</Mono> : "현재 폴더가 없습니다"
              }
              right={
                <span>
                  {library.source === "custom" ? <Pill>사용자 지정</Pill> : null}
                  <Pill>{library.game_count}</Pill>
                </span>
              }
              disabled
              onClick={() => {}}
            />
          ))
        )}
      </PanelSection>

      <PanelSection title="사용자 지정 폴더">
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void addFolder()}>
            게임 폴더 추가
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <Notice tone="info">
            선택한 폴더의 하위 폴더 하나하나를 게임 하나로 취급합니다.
          </Notice>
        </PanelSectionRow>
        {(libraries ?? [])
          .filter((library) => library.source === "custom")
          .map((library) => (
            <PanelSectionRow key={library.path}>
              <ButtonItem
                layout="below"
                onClick={async () => {
                  await removeCustomLibrary(library.path);
                  await loadLibraries();
                }}
              >
                “{library.name}” 제거
              </ButtonItem>
            </PanelSectionRow>
          ))}
      </PanelSection>
    </>
  );
}
