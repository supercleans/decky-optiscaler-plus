import { DropdownItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { getChannelVersions, setChannelVersion } from "../api";
import type { Channel, ChannelVersions as Versions } from "../types";
import { Mono, Notice } from "./Common";

const CHANNELS: { channel: Channel; label: string; about: string }[] = [
  {
    channel: "nightly",
    label: "OptiScaler nightly",
    about: "FSR 4 Lite·cyboman 설치와 AMD FSR 4.1.2 드롭인에 쓰는 OptiScaler 빌드.",
  },
  {
    channel: "dropin",
    label: "cyboman FSR 4.1.2 Lite",
    about: "FSR 4.1.2 Lite exact·lossy를 드롭인이나 OptiScaler로 넣을 때 쓰는 빌드.",
  },
  {
    channel: "helixsr",
    label: "HelixSR (HLX FSR 4)",
    about: "HLX FSR 4를 받아 오는 HelixSR 릴리스. 3.2.0부터 미리 빌드된 HLX FSR 4가 들어 있습니다.",
  },
];

/** "" is the dropdown's "newest" entry: no pin. */
const NEWEST = "";

function describeDay(iso: string | null) {
  if (!iso) return "";
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? "" : ` (${when.toLocaleDateString()})`;
}

/**
 * Which build of each downloaded channel installs use: the one set up (and
 * updated from Settings when a newer one is out), by default, or one picked
 * here. The list starts at the build that was newest when this plugin was
 * built and runs to the newest now, so going back to the build the plugin was
 * made against is always one pick away. A pin changes what the next install
 * downloads; games already set up keep their files until then.
 */
export function ChannelVersions({ onChanged }: Readonly<{ onChanged?: () => void }>) {
  const [lists, setLists] = useState<Partial<Record<Channel, Versions>>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const entries = await Promise.all(
      CHANNELS.map(async ({ channel }) => {
        try {
          return [channel, await getChannelVersions(channel)] as const;
        } catch {
          return [channel, undefined] as const;
        }
      })
    );
    setLists(Object.fromEntries(entries.filter(([, list]) => list?.ok)));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const pick = async (channel: Channel, tag: string) => {
    setBusy(true);
    try {
      const result = await setChannelVersion(channel, tag || null);
      if (!result.ok) {
        toaster.toast({ title: "버전을 바꾸지 못했습니다", body: String(result.error) });
        return;
      }
      toaster.toast({
        title: tag ? `${tag}로 고정했습니다` : "설치한 버전을 쓰도록 바꿨습니다",
        body: tag
          ? "다음 설치부터 이 빌드를 받습니다. 이미 설치한 게임은 다시 설치할 때 바뀝니다."
          : "새 빌드가 나오면 알려 주고, 받은 파일에서 업데이트할 수 있습니다.",
      });
      await load();
      onChanged?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection title="다운로드 버전">
      {CHANNELS.map(({ channel, label, about }) => {
        const list = lists[channel];
        const options = [
          { data: NEWEST, label: "설치한 버전 (새 빌드 알림)" },
          ...(list?.versions ?? []).map((version) => ({
            data: version.tag,
            label: `${version.tag}${describeDay(version.published_at)}${
              version.baseline ? " — 플러그인 빌드 기준" : ""
            }${version.downloaded ? " · 받아 둠" : ""}`,
          })),
        ];
        return (
          <PanelSectionRow key={channel}>
            <DropdownItem
              label={label}
              description={
                list?.error
                  ? `${about} 목록을 받지 못해 이 기기에 있는 빌드만 보입니다.`
                  : about
              }
              disabled={busy || !list}
              bottomSeparator="standard"
              rgOptions={options}
              selectedOption={list?.pinned ?? NEWEST}
              onChange={(selected) => void pick(channel, String(selected.data))}
              {...({ "data-channel": channel } as Record<string, string>)}
            />
          </PanelSectionRow>
        );
      })}
      {Object.values(lists).some((list) => list?.pinned) ? (
        <PanelSectionRow>
          <Notice tone="info" title="고정한 버전이 있습니다">
            {Object.values(lists)
              .filter((list) => list?.pinned)
              .map((list) => (
                <span key={list!.channel}>
                  <Mono>{list!.pinned}</Mono>{" "}
                </span>
              ))}
            새 빌드가 나와도 이 버전을 받습니다. 처음 받는 버전이면 설치할 때 인터넷 연결이
            필요합니다.
          </Notice>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}
