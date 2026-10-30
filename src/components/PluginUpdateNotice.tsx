import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { usePluginUpdate } from "../hooks/usePluginUpdate";
import { Notice } from "./Common";

/**
 * "A newer version is out", with the button that installs it. Renders nothing
 * until there is one, so it can sit at the top of any page.
 */
export function PluginUpdateNotice() {
  const { update, installing, install } = usePluginUpdate();
  if (!update?.update_available) return null;
  return (
    <PanelSection>
      <PanelSectionRow>
        <Notice tone="info" title={`Decky Upscaler Manager ${update.latest} 버전이 나왔습니다`}>
          현재 버전은 {update.current}입니다. Decky가 설치 전에 확인을 요청합니다.
        </Notice>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={installing} onClick={() => void install()}>
          {installing ? "업데이트를 시작하는 중…" : `${update.latest} 버전으로 업데이트`}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
