import { DialogButton, Focusable, PanelSection, PanelSectionRow } from "@decky/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { assessGames, listAllGames } from "../api";
import { lastPlayed } from "../hooks/useRunningGame";
import type { CompatStatus, Game, GameCompat } from "../types";
import { Centered, Notice, Pill, RowButton } from "./Common";
import { TabStrip } from "./TabStrip";
import { upscalerLabel } from "./UpscalerPanel";

/** Rows per page on the full page; the Quick Access panel asks for fewer. */
const PAGE_SIZE = 20;
/** Games per compatibility request: small enough that badges arrive steadily. */
const COMPAT_BATCH = 12;

const COMPAT_BADGES: Record<CompatStatus, { label: string; color?: string } | null> = {
  listed: { label: "위키 ✓", color: "#1a6aa8" },
  likely: { label: "유력", color: "#3d5a80" },
  partial: { label: "부분", color: "#8a6d1f" },
  risky: { label: "안티치트", color: "#8a6d1f" },
  broken: { label: "불가", color: "#8b2f2f" },
  unsupported: { label: "미지원", color: "#5a5a5a" },
  unknown: { label: "?" },
  error: null,
};

interface Props {
  onOpenGame: (game: Game) => void;
  /** Rows per page. The Quick Access panel asks for four. */
  pageSize?: number;
  /**
   * One line per game - its name and badge - for the narrow Quick Access panel.
   * The reasons behind a badge are on the full page and the game's own page.
   */
  compact?: boolean;
}

/**
 * Every detected game, across every library, as one list.
 *
 * A Deck library can run to hundreds of entries, and a single list that long is
 * miserable to walk with a D-pad, so it is paged. A page replaces the one before
 * rather than being added under it, so the list never grows past one page and
 * there is nothing to scroll back up through. The pager wraps around: a Next
 * that went nowhere on the last page would be a dead button with the focus
 * stuck on it.
 *
 * Paging alone still means walking, though, and the game somebody wants is
 * nearly always one they have just played or one they have already set up. Both
 * are a filter away. It opens on the games already set up, when there are any,
 * and otherwise on "recently played" when Steam will say.
 *
 * Each row also says whether OptiScaler is worth trying there, from the game's
 * own files and the wiki. That walks every install folder, so it arrives after
 * the list, a batch at a time, recently played first.
 */
export function GamesList({ onOpenGame, pageSize = PAGE_SIZE, compact = false }: Props) {
  const [games, setGames] = useState<Game[] | null>(null);
  const [compat, setCompat] = useState<Record<string, GameCompat>>({});
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    setError(null);
    try {
      const found = await listAllGames();
      // Never trust the shape: a backend that failed mid-scan must not take the
      // whole page down with it.
      const list = Array.isArray(found) ? found : [];
      setGames(list);
      // Open on the games already set up, which is what this is mostly opened
      // to look at. With none yet, Recent - but only when there is a recency
      // to show: games added as custom folders have no Steam overview to read
      // a last-played time from.
      if (list.some((game) => game.installed)) setFilter("setup");
      else if (list.some((game) => lastPlayed(game.appid) !== null)) setFilter("recent");
    } catch (exc) {
      setError(String(exc));
      setGames([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Steam is asked once per list, not once per row: this is an in-memory read
  // of the client's own app overviews, but the list can run to hundreds.
  const played = useMemo(() => {
    const map = new Map<string, number | null>();
    for (const game of games ?? []) map.set(game.path, lastPlayed(game.appid));
    return map;
  }, [games]);

  useEffect(() => {
    if (!games?.length) return;
    let cancelled = false;
    // Recently played first: the games most likely to be opened next. (The
    // set-up games it opens on show "적용" rather than a badge.)
    const order = games
      .slice()
      .sort((a, b) => (played.get(b.path) ?? 0) - (played.get(a.path) ?? 0));
    setChecking(true);
    void (async () => {
      for (let i = 0; i < order.length && !cancelled; i += COMPAT_BATCH) {
        const batch = order
          .slice(i, i + COMPAT_BATCH)
          .map(({ path, name, size_on_disk }) => ({ path, name, size_on_disk }));
        try {
          const found = await assessGames(batch);
          if (!cancelled && found && typeof found === "object") {
            setCompat((previous) => ({ ...previous, ...found }));
          }
        } catch {
          // The badges are a hint. A batch that failed leaves its rows without
          // one rather than taking the list down.
        }
      }
      if (!cancelled) setChecking(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [games, played]);

  if (error) {
    return (
      <PanelSection title="게임">
        <PanelSectionRow>
          <Notice tone="error" title="라이브러리를 읽을 수 없습니다">
            {error}
          </Notice>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  if (games === null) return <Centered>라이브러리를 검색하는 중…</Centered>;

  const filtered = filterGames(games, filter, played, compat);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  // Compatible grows and shrinks as badges arrive, so a page that was there a
  // moment ago may not be any more.
  const current = Math.min(page, pages - 1);
  const first = current * pageSize;
  const visible = filtered.slice(first, first + pageSize);
  const setUpCount = games.filter((game) => game.installed).length;
  const compatibleCount = games.filter((game) => compat[game.path]?.compatible).length;
  const anyPlayed = Array.from(played.values()).some((value) => value !== null);
  const tabs = [
    ...(anyPlayed ? [{ id: "recent", title: "최근" }] : []),
    { id: "setup", title: "설치됨", badge: setUpCount },
    {
      id: "compatible",
      title: "호환",
      badge: checking ? `${compatibleCount}…` : compatibleCount,
    },
    { id: "all", title: "전체", badge: games.length },
  ];
  const turn = (step: number) => setPage((current + step + pages) % pages);

  return (
    <>
      <TabStrip
        tabs={tabs}
        marker="filter"
        active={filter}
        onChange={(id) => {
          setFilter(id);
          setPage(0);
        }}
      />

      <PanelSection>
        {visible.length === 0 ? (
          <PanelSectionRow>
            <EmptyNotice filter={filter} checking={checking} />
          </PanelSectionRow>
        ) : (
          visible.map((game) => {
            const verdict = compat[game.path];
            const badge = verdict ? COMPAT_BADGES[verdict.status] : null;
            return (
              <RowButton
                key={game.path}
                label={game.name}
                description={compact ? undefined : describe(game, verdict, played)}
                right={
                  game.installed ? (
                    <Pill color="#2f6b3f">적용</Pill>
                  ) : (
                    <>
                      {badge ? <Pill color={badge.color}>{badge.label}</Pill> : null}
                      {/* How FSR 4 gets in: the game's own FSR 3.1 swapped, or
                          OptiScaler with REFramework, which it cannot go without. */}
                      {verdict?.dropin ? <Pill color="#2b6f6a">드롭인</Pill> : null}
                      {verdict?.reframework_only ? (
                        <Pill color="#8a5a1f">REF 필수</Pill>
                      ) : verdict?.dropin && verdict.reframework ? (
                        // The drop-in needs nothing, but the OptiScaler way does.
                        <Pill>REF</Pill>
                      ) : null}
                      {verdict?.optipatcher ? <Pill color="#5b4a85">OP</Pill> : null}
                      {/* Something else has to be in place first: a mod, a file,
                          Engine.ini lines. The game page says what. */}
                      {verdict?.requires?.length ? (
                        <Pill color="#8a3f6a">
                          {verdict.requires.some((name) => name.endsWith("모드")) ? "모드 필요" : "추가 작업"}
                        </Pill>
                      ) : null}
                    </>
                  )
                }
                onClick={() => onOpenGame(game)}
              />
            );
          })
        )}

        {pages > 1 ? (
          <PanelSectionRow>
            <Pager
              first={first + 1}
              last={first + visible.length}
              total={filtered.length}
              onPrevious={() => turn(-1)}
              onNext={() => turn(1)}
            />
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    </>
  );
}

/** ‹ 9–16 of 87 › : the range shown, between the two ways out of it. */
function Pager({
  first,
  last,
  total,
  onPrevious,
  onNext,
}: {
  first: number;
  last: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const button = { minWidth: "0", width: "auto", flex: "0 0 auto", padding: "6px 14px" };
  return (
    <Focusable
      flow-children="horizontal"
      style={{ display: "flex", alignItems: "center", gap: "8px", padding: "6px 0" }}
    >
      <DialogButton style={button} onClick={onPrevious} data-page="previous">
        ‹ 이전
      </DialogButton>
      <div style={{ flexGrow: 1, textAlign: "center", fontSize: "12px", opacity: 0.8 }}>
        {first}–{last} / {total}
      </div>
      <DialogButton style={button} onClick={onNext} data-page="next">
        다음 ›
      </DialogButton>
    </Focusable>
  );
}

/** The second line of a full-size row: where the game is, and why its badge. */
function describe(
  game: Game,
  verdict: GameCompat | undefined,
  played: Map<string, number | null>
) {
  if (game.installed) {
    const engine = game.engine === "helixsr" ? "HelixSR Scaler" : "OptiScaler";
    return game.managed
      ? `${upscalerLabel(game.upscaler)} · ${engine} · ${game.filename}`
      : `${engine} · ${game.filename}`;
  }
  return (
    [
      describePlayed(played.get(game.path)) ?? game.library,
      verdict?.summary,
      verdict?.dropin
        ? verdict.reframework
          ? "FSR 드롭인 가능 · OptiScaler는 REFramework 필요"
          : "FSR 드롭인 가능"
        : verdict?.reframework_only
          ? "REFramework 필수"
          : null,
      verdict?.optipatcher ? "OptiPatcher 권장" : null,
      verdict?.requires?.length ? `${verdict.requires.join(", ")} 필요` : null,
    ]
      .filter(Boolean)
      .join(" · ") || undefined
  );
}

function EmptyNotice({ filter, checking }: { filter: string; checking: boolean }) {
  if (filter === "setup") {
    return (
      <Notice tone="info" title="아직 설치한 게임이 없습니다">
        아직 OptiScaler가 설치된 게임이 없습니다. 전체에서 게임을 골라 설치하세요.
      </Notice>
    );
  }
  if (filter === "compatible") {
    return (
      <Notice tone="info" title={checking ? "게임을 확인하는 중…" : "추천할 게임이 없습니다"}>
        DLSS, XeSS, FSR 라이브러리가 들어 있거나 OptiScaler 위키에 작동한다고 등재된 게임이
        없습니다. 참고일 뿐 판정은 아닙니다. FSR을 실행 파일에 직접 넣은 게임도 작동합니다.
        전체에서 게임을 열어 위키와 대조해 보세요.
      </Notice>
    );
  }
  return (
    <Notice tone="info" title="게임을 찾지 못했습니다">
      Steam 라이브러리에서 게임을 찾지 못했습니다. 게임이 다른 곳에 있으면 라이브러리에서
      폴더를 추가하세요.
    </Notice>
  );
}

/**
 * Newest first for Recent, and only the games that have a last-played time.
 * Compatible is whatever the badges have said so far, so it fills in as they
 * arrive.
 */
function filterGames(
  games: Game[],
  filter: string,
  played: Map<string, number | null>,
  compat: Record<string, GameCompat>
) {
  if (filter === "setup") return games.filter((game) => game.installed);
  if (filter === "compatible") return games.filter((game) => compat[game.path]?.compatible);
  if (filter !== "recent") return games;
  return games
    .filter((game) => played.get(game.path) != null)
    .slice()
    .sort((a, b) => (played.get(b.path) ?? 0) - (played.get(a.path) ?? 0));
}

/** "3 days ago" for the row's second line, when Steam knows. */
function describePlayed(when: number | null | undefined) {
  if (!when) return undefined;
  const days = Math.floor((Date.now() / 1000 - when) / 86400);
  if (days <= 0) return "오늘 플레이";
  if (days === 1) return "어제 플레이";
  if (days < 30) return `${days}일 전 플레이`;
  const months = Math.floor(days / 30);
  return months === 1 ? "한 달 전 플레이" : `${months}개월 전 플레이`;
}
