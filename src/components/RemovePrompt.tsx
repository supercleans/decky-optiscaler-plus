import { ConfirmModal, DropdownItem, ToggleField } from "@decky/ui";
import { useState } from "react";
import { launchChoices, resolveChoice } from "../launchOptions";
import type { LaunchAction, LaunchState } from "../launchOptions";
import { Mono, Notice } from "./Common";

/**
 * The question removing OptiScaler has always had and never asked.
 *
 * Installing writes a `WINEDLLOVERRIDES` entry into Steam; removing used to
 * clear it, but only when the plugin could still read the field, and never
 * considered that the game might have had launch options of its own first —
 * which it then destroyed. Both halves are now decisions rather than side
 * effects, and the choice is made from what was actually recorded at install
 * time: "put back what was there" is only offered when there was something.
 *
 * The answer can be remembered, because most people set every game up the same
 * way and being asked each time is the same nag twice. A remembered answer is
 * shown here rather than applied invisibly, and the Settings tab is where it is
 * taken back.
 */
export function RemovePrompt({
  gameName,
  filename,
  backedUp,
  launch,
  remembered,
  canRemember,
  closeModal,
  onConfirm,
}: Readonly<{
  gameName: string;
  filename: string | null;
  backedUp: number;
  /** Null when this game has no launch options to decide about at all. */
  launch: LaunchState | null;
  remembered: LaunchAction | null;
  canRemember: boolean;
  closeModal?: () => void;
  onConfirm: (action: LaunchAction, remember: boolean) => void;
}>) {
  const choices = launch ? launchChoices(launch) : [];
  const asked = choices.filter((choice) => choice.action !== "keep").length > 0;
  const initial = resolveChoice(choices, remembered);
  const [action, setAction] = useState<LaunchAction>(initial?.action ?? "keep");
  const [remember, setRemember] = useState(false);
  const chosen = choices.find((choice) => choice.action === action) ?? initial;

  return (
    <ConfirmModal
      strTitle="OptiScaler를 제거할까요?"
      strOKButtonText="제거"
      strCancelButtonText="유지"
      closeModal={closeModal}
      onOK={() => onConfirm(action, remember)}
    >
      <div style={{ fontSize: "14px", lineHeight: 1.5 }}>
        {backedUp > 0
          ? `${gameName}에서 따로 보관한 파일 ${backedUp}개를 복원하고 설정을 제거합니다.`
          : `${gameName} 폴더에서 OptiScaler 파일과 설정을 제거합니다.`}
        {filename ? (
          <>
            {" "}
            <Mono>{filename}</Mono>도 함께 제거됩니다.
          </>
        ) : null}
      </div>

      {asked && remembered ? (
        <Notice tone="info" title="Steam 실행 옵션">
          {chosen?.label}. 기억하도록 한 선택입니다. 메인 페이지의 설정에서 바꿀 수
          있습니다.
        </Notice>
      ) : null}

      {asked && !remembered ? (
        <>
          <DropdownItem
            label="Steam 실행 옵션"
            description={chosen?.description}
            rgOptions={choices.map((choice) => ({ data: choice.action, label: choice.label }))}
            selectedOption={action}
            bottomSeparator="none"
            onChange={(option: { data: LaunchAction }) => setAction(option.data)}
          />
          {canRemember ? (
            <ToggleField
              label="이 선택 기억"
              description="이후 제거할 때는 묻지 않고 이대로 처리합니다."
              checked={remember}
              bottomSeparator="none"
              onChange={setRemember}
            />
          ) : null}
        </>
      ) : null}

      {!asked ? (
        <div style={{ fontSize: "13px", opacity: 0.7, marginTop: "6px" }}>
          Steam에 이 게임의 복원할 실행 옵션이 없습니다.
        </div>
      ) : null}
    </ConfirmModal>
  );
}
