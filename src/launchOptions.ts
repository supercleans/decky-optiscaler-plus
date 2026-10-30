/**
 * The Steam launch options this plugin writes, and how to take them back out.
 *
 * Installing OptiScaler is two changes, not one: a folder full of files, and a
 * `WINEDLLOVERRIDES` entry in Steam. Removing it used to undo only the first,
 * so a game that had been "removed" still carried an override for a DLL that
 * was no longer there — harmless, but it is litter this plugin left behind and
 * nothing on screen admitted to it.
 *
 * Undoing the second half properly needs to know what was there first, which
 * only Steam can say and only while the plugin is running. `record_launch_options`
 * is therefore called at install time with whatever Steam currently passes, and
 * the answer is kept next to the install. Three things then become tellable
 * apart, which is the whole point:
 *
 * - **recorded and empty** — the game had no launch options at all, so removing
 *   OptiScaler can clear the field outright.
 * - **recorded and not empty** — there is something to put back, verbatim.
 * - **not recorded** — the install predates this, or Steam would not say. Only
 *   the override this plugin recognises is removed; anything else is left, on
 *   the grounds that it is not ours to guess about.
 */
import { getLaunchOptions, recordLaunchOptions } from "./api";
import { readLaunchOptions } from "./hooks/useRunningGame";
import type { LaunchRecord } from "./types";

/** What to do with the launch options when OptiScaler is removed. */
export type LaunchAction = "restore" | "clear" | "keep";

export interface LaunchState {
  /** Steam's current launch options, or null when the client will not say. */
  current: string | null;
  /** What was there before the install, or null when nothing was recorded. */
  recorded: string | null;
  /** The proxy filename OptiScaler is installed as, e.g. `dxgi.dll`. */
  filename: string;
  /** Other overrides that go with it, e.g. `dinput8` for our REFramework. */
  extraStems?: string[];
}

export interface LaunchChoice {
  action: LaunchAction;
  label: string;
  description: string;
  /** What Steam would be set to, or null to leave the field untouched. */
  value: string | null;
}

/** The `WINEDLLOVERRIDES` entry an install under this filename adds. */
export function overrideStem(filename: string): string {
  return filename.replace(/\.(dll|asi)$/i, "");
}

export function launchOptionFor(filename: string): string {
  if (filename.toLowerCase().endsWith(".asi")) return "%command%";
  return `WINEDLLOVERRIDES="${overrideStem(filename)}=n,b" %command%`;
}

/** Arguments that pick a game's graphics API: a game takes one of them at a time. */
const API_FLAGS = [
  "-dx11", "-dx12", "-d3d11", "-d3d12", "-vulkan",
  "-force-d3d11", "-force-d3d12", "-force-vulkan", "-force-glcore",
];

const OVERRIDES_RE = /WINEDLLOVERRIDES=(?:"([^"]*)"|'([^']*)'|(\S+))/gi;

/** A dll's name the way Wine's overrides compare it: no `.dll`, any case. */
function dllName(name: string): string {
  return name.trim().toLowerCase().replace(/\.dll$/, "");
}

/**
 * The clauses of every `WINEDLLOVERRIDES` assignment in a launch options
 * string (`dxgi=n,b`, `d3d11,dxgi=n`...), and the string without them.
 *
 * Every assignment, not just the first: two of them would have the shell keep
 * the last and drop the other, so they are put back together as one.
 */
function splitOverrides(options: string): { clauses: string[]; rest: string } {
  const clauses: string[] = [];
  const rest = options.replace(OVERRIDES_RE, (_match, quoted, single, bare) => {
    for (const clause of String(quoted ?? single ?? bare ?? "").split(";")) {
      if (clause.trim()) clauses.push(clause.trim());
    }
    return "";
  });
  return { clauses, rest: rest.replace(/\s+/g, " ").trim() };
}

/** The clauses with these dlls taken out of each; one left naming none goes. */
function withoutDlls(clauses: string[], stems: string[]): string[] {
  const drop = new Set(stems.map(dllName));
  return clauses.flatMap((clause) => {
    const eq = clause.indexOf("=");
    const names = (eq < 0 ? clause : clause.slice(0, eq)).split(",");
    const kept = names.filter((name) => !drop.has(dllName(name)));
    if (kept.length === names.length) return [clause];
    return kept.length ? [kept.join(",") + (eq < 0 ? "" : clause.slice(eq))] : [];
  });
}

/** A launch argument as a whole word: `-dx12`, but not the `-d3d12` in `-force-d3d12`. */
function argument(flag: string, global = false): RegExp {
  return new RegExp(`(^|\\s)${flag.replace(/-/g, "\\-")}(?=\\s|$)`, global ? "gi" : "i");
}

function overridesAssignment(clauses: string[]): string {
  return clauses.length ? `WINEDLLOVERRIDES="${clauses.join(";")}"` : "";
}

export function hasOverride(options: string | null, filename: string): boolean {
  if (!options) return false;
  const stem = dllName(overrideStem(filename));
  return splitOverrides(options).clauses.some((clause) => {
    const eq = clause.indexOf("=");
    return eq > 0 && /^(n,b|native,builtin)$/i.test(clause.slice(eq + 1).trim()) &&
      clause.slice(0, eq).split(",").some((name) => dllName(name) === stem);
  });
}

/**
 * Steam's launch options with our overrides and the wiki's arguments put in,
 * everything else kept.
 *
 * The overrides go into the game's own `WINEDLLOVERRIDES` when it has one (one
 * assignment, ours replacing any clause for the same dll, so a second install
 * or a `dxgi=b` of the user's does not leave two answers), placed before
 * everything else so a wrapper like `mangohud` or `gamescope -- ` runs with it.
 * Options without `%command%` are arguments Steam appends to the game, so they
 * go after one. An argument already there is not added twice, and one picking
 * the graphics API replaces another that picks a different one: the entry
 * asked for that API, and a game given both takes whichever it reads last.
 */
export function mergeLaunchOptions(
  current: string | null,
  stems: string[],
  flags: string[] = [],
): string {
  const { clauses, rest } = splitOverrides(current ?? "");
  const ours = stems.filter(Boolean);
  const merged = [...withoutDlls(clauses, ours), ...ours.map((stem) => `${stem}=n,b`)];
  let command = /%command%/i.test(rest) ? rest : rest ? `%command% ${rest}` : "%command%";
  const at = command.search(/%command%/i) + "%command%".length;
  let args = command.slice(at);
  for (const flag of flags) {
    if (API_FLAGS.includes(flag.toLowerCase())) {
      for (const other of API_FLAGS) {
        if (other !== flag.toLowerCase()) args = args.replace(argument(other, true), "");
      }
    }
    if (!argument(flag).test(args)) args = `${args} ${flag}`;
  }
  command = `${command.slice(0, at)} ${args}`;
  return `${overridesAssignment(merged)} ${command}`.replace(/\s+/g, " ").trim();
}

/** A `KEY=value` assignment as a whole word, whatever its quoting. */
function assignment(key: string): RegExp {
  return new RegExp(`(^|\\s)${key}=(?:"(?:[^"\\\\]|\\\\.)*"|'[^']*'|\\S*)(?=\\s|$)`, "g");
}

/**
 * Launch options with `KEY=value` set before the command, replacing any value
 * the key had and keeping everything else (overrides, wrappers, arguments).
 */
export function withEnv(current: string | null, key: string, value: string): string {
  const rest = withoutEnv(current ?? "", key);
  const command = /%command%/i.test(rest) ? rest : rest ? `%command% ${rest}` : "%command%";
  return `${key}=${value} ${command}`.replace(/\s+/g, " ").trim();
}

/** Launch options with every `KEY=...` taken out; a bare `%command%` left collapses to none. */
export function withoutEnv(options: string, key: string): string {
  const out = options.replace(assignment(key), " ").replace(/\s+/g, " ").trim();
  return out === "%command%" ? "" : out;
}

/**
 * The same launch options with our overrides taken out and nothing else.
 *
 * Conservative on purpose: a user may have added `-dx12`, a gamescope wrapper
 * or overrides of their own alongside ours, and those are not this plugin's to
 * delete. Only the clauses naming the proxy we installed (and ``extraStems``)
 * come out of `WINEDLLOVERRIDES`; the assignment goes once nothing is left in
 * it. A leftover bare `%command%` is Steam's own default written out longhand,
 * so that collapses to an empty field.
 */
export function stripOverride(options: string, filename: string, extraStems: string[] = []): string {
  const { clauses, rest } = splitOverrides(options);
  const kept = withoutDlls(clauses, [overrideStem(filename), ...extraStems]);
  const collapsed = `${overridesAssignment(kept)} ${rest}`.replace(/\s+/g, " ").trim();
  return collapsed === "%command%" ? "" : collapsed;
}

/**
 * What the user can be offered when OptiScaler is removed, best answer first.
 *
 * "Put back what was there" is only offered when there was something — which is
 * exactly the condition the question is worth asking under. Clearing is offered
 * whenever the result is known: the record says the game had no launch options
 * at all, or the override we installed is visibly in what Steam reports.
 *
 * When neither is true, nothing here is known to be ours — and the honest
 * answer used to be to offer nothing, which is how a client build with no way
 * to read launch options turned this whole feature into a dialog that did
 * nothing. Clearing is offered even then, last and never as the default, and
 * says plainly that it empties the field rather than pruning it. Doing nothing
 * has to be a choice the user makes, not one made for them by a missing API.
 *
 * Two choices that would produce the same launch options are collapsed into
 * one, because a dialog offering the same outcome twice is one nobody can
 * answer.
 */
export function launchChoices(state: LaunchState): LaunchChoice[] {
  const { current, recorded, filename, extraStems = [] } = state;
  const restore: LaunchChoice[] =
    recorded !== null && recorded.trim() !== "" && recorded !== current
      ? [{
          action: "restore",
          label: "이전 값으로 복원",
          description: recorded,
          value: recorded,
        }]
      : [];

  const keep: LaunchChoice = {
    action: "keep",
    label: "그대로 두기",
    description: current
      ? `그대로 유지: ${current}`
      : "Steam에서 아무것도 바꾸지 않습니다.",
    value: null,
  };

  // What removing our half would leave behind, when that is knowable.
  const known =
    recorded === ""
      ? ""
      : current !== null && hasOverride(current, filename)
        ? stripOverride(current, filename, extraStems)
        : null;
  const blind = known === null && current === null;

  if (known === null && !blind) return [...restore, keep];

  const cleared = known ?? "";
  const clear: LaunchChoice = {
    action: "clear",
    label:
      blind
        ? "실행 옵션 비우기"
        : cleared === ""
          ? "실행 옵션 비우기"
          : "OptiScaler 오버라이드만 제거",
    description: blind
      ? "Steam이 이 게임의 실행 옵션을 알려 주지 않아, 직접 추가한 내용까지 모두 비웁니다."
      : cleared === ""
        ? recorded === ""
          ? "OptiScaler 설치 전에는 실행 옵션이 없었습니다."
          : "실행 옵션을 비웁니다."
        : `남는 값: ${cleared}`,
    value: cleared,
  };

  // A choice that would write back what Steam already has, or that lands on
  // the same string as one already on offer, is not a choice.
  const duplicate =
    cleared === current || restore.some((choice) => choice.value === cleared);
  if (duplicate) return [...restore, keep];
  // Blind clearing is a guess, so it never leads — the safe answer does.
  return blind ? [...restore, keep, clear] : [...restore, clear, keep];
}

/**
 * The choice to act on, honouring a remembered answer only if it still applies.
 *
 * Undefined when there is nothing to choose between — a game Steam does not
 * own, which has no launch options to decide about at all.
 */
export function resolveChoice(
  choices: LaunchChoice[],
  remembered: LaunchAction | null,
): LaunchChoice | undefined {
  const match = remembered && choices.find((choice) => choice.action === remembered);
  return match || choices[0];
}

/** Whether the removal dialog has anything to ask about at all. */
export function hasLaunchQuestion(appid: string | null, state: LaunchState): boolean {
  if (!appid) return false;
  return launchChoices(state).some((choice) => choice.action !== "keep");
}

/** The record as the backend reports it, as the nullable string the UI reasons in. */
export function recordedValue(record: LaunchRecord | undefined): string | null {
  return record?.recorded ? record.value : null;
}

/**
 * What Steam passes this game right now, from whichever source can say.
 *
 * The client is asked first because it is live; Steam only flushes its config
 * file periodically, so a value written seconds ago may not be in it yet. But
 * the client getter is missing from some builds entirely, and on those this
 * was the single point of failure that made the whole feature inert — the
 * plugin could see neither its own override nor anything it had replaced.
 */
export async function currentLaunchOptions(appid: string | null): Promise<string | null> {
  if (!appid) return null;
  const fromClient = await readLaunchOptions(Number(appid));
  if (fromClient !== null) return fromClient;
  try {
    const found = await getLaunchOptions(appid);
    return found.found ? found.value : null;
  } catch {
    return null;
  }
}

/**
 * Keep this game's launch options as they were, before we write our own.
 *
 * Called after a successful install and before the override is set, which is
 * the only moment Steam still holds the answer. Write-once in the backend, so
 * calling it again — a reinstall, or the checklist's launch-options toggle
 * being switched back on — cannot overwrite the original with our own override.
 *
 * What the client reads is passed along rather than looked up again in the
 * backend, because it is the fresher of the two; `null` tells the backend to
 * fall back to Steam's config file instead of recording a value nobody read.
 */
export async function recordPreviousLaunchOptions(
  appid: string | null,
  targetDir: string,
): Promise<void> {
  if (!appid) return;
  const current = await readLaunchOptions(Number(appid));
  try {
    await recordLaunchOptions(targetDir, current, appid);
  } catch {
    /* the record is a convenience; failing to write it must not fail an install */
  }
}
