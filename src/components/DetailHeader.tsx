import { DialogButton, Focusable } from "@decky/ui";
import type { ReactNode } from "react";

/**
 * One compact row instead of a stack of PanelSections.
 *
 * On a handheld every row of chrome is a row of settings you cannot see, so the
 * back action, title and status all share ~32px.
 */
export function DetailHeader({
  title,
  badges,
  onBack,
  action,
}: {
  title: string;
  badges?: ReactNode;
  onBack?: () => void;
  action?: ReactNode;
}) {
  return (
    <Focusable
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "2px 12px 4px",
        flexShrink: 0,
        minHeight: "30px",
      }}
    >
      {/* A DialogButton, not a bare <button>: only Steam's own buttons are
          reachable with the D-pad, and a back action nothing can focus is a
          back action a controller does not have. */}
      {onBack ? (
        <DialogButton
          onClick={onBack}
          onOKActionDescription="게임 목록으로 돌아가기"
          {...({ "data-back": "games" } as Record<string, string>)}
          style={{
            width: "auto",
            minWidth: 0,
            flexShrink: 0,
            fontSize: "12px",
            padding: "3px 9px",
          }}
        >
          ‹ 뒤로
        </DialogButton>
      ) : null}
      <span
        style={{
          fontSize: "15px",
          fontWeight: 600,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          flexShrink: 1,
          minWidth: 0,
        }}
      >
        {title}
      </span>
      <span style={{ flexShrink: 0 }}>{badges}</span>
      <span style={{ marginLeft: "auto", flexShrink: 0 }}>{action}</span>
    </Focusable>
  );
}
