/**
 * The launch options lsfg-vk takes, kept as plain variables in Steam's field
 * rather than in a wrapper script.
 *
 * decky-lsfg-vk puts `~/.lsfg %command%` in a game's launch options and keeps
 * its workarounds in a script; here they are the variables themselves, read
 * back from the field to know which are on, so there is no file for the game
 * to fail without. Turning lsfg-vk off for a game takes out the ones it put in
 * (a fixed value only where it has the value set here) and nothing else.
 */
import { withEnv, withoutEnv } from "./launchOptions";

/** A game's lsfg-vk workarounds, decky-lsfg-vk's set. */
export interface LsfgWorkarounds {
  /** ENABLE_GAMESCOPE_WSI=0: lsfg-vk's vsync pacing in Gamescope (Game Mode) needs it. */
  disableGamescopeWsi: boolean;
  /** DXVK_HDR=0. */
  disableHdr: boolean;
  /** SteamDeck=0: the game's own Steam Deck mode off. */
  disableSteamDeck: boolean;
  /** DISABLE_VKBASALT=1. */
  disableVkBasalt: boolean;
  /** OpenGL games through Zink, so the Vulkan layer reaches them. */
  zink: boolean;
  /** DXVK_FRAME_RATE: the base frame rate to generate from; 0 is none. */
  fpsCap: number;
}

/** What a game starts with: decky-lsfg-vk's defaults. */
export const DEFAULT_WORKAROUNDS: LsfgWorkarounds = {
  disableGamescopeWsi: true,
  disableHdr: true,
  disableSteamDeck: false,
  disableVkBasalt: false,
  zink: false,
  fpsCap: 0,
};

const FLAGS: [keyof Omit<LsfgWorkarounds, "fpsCap">, [string, string][]][] = [
  ["disableGamescopeWsi", [["ENABLE_GAMESCOPE_WSI", "0"]]],
  ["disableHdr", [["DXVK_HDR", "0"]]],
  ["disableSteamDeck", [["SteamDeck", "0"]]],
  ["disableVkBasalt", [["DISABLE_VKBASALT", "1"]]],
  ["zink", [["__GLX_VENDOR_LIBRARY_NAME", "mesa"], ["MESA_LOADER_DRIVER_OVERRIDE", "zink"], ["GALLIUM_DRIVER", "zink"]]],
];
const FPS_KEY = "DXVK_FRAME_RATE";
/** The profile to use, named outright: a non-Steam shortcut's process may not carry the app id. */
export const PROFILE_KEY = "LSFGVK_PROFILE";
/** decky-lsfg-vk's wrapper, as a word in the launch options. */
const WRAPPER_RE = /(^|\s)(?:~|\/home\/[^/\s]+)\/\.lsfg(?=\s|$)/g;

function value(options: string, key: string): string | null {
  const match = new RegExp(`(?:^|\\s)${key}=(?:"((?:[^"\\\\]|\\\\.)*)"|'([^']*)'|(\\S*))`).exec(options);
  return match ? match[1] ?? match[2] ?? match[3] ?? "" : null;
}

/** Whether decky-lsfg-vk's wrapper runs this game. */
export function hasLsfgWrapper(options: string): boolean {
  return new RegExp(WRAPPER_RE.source).test(options);
}

/** The workarounds these launch options turn on. */
export function readWorkarounds(options: string): LsfgWorkarounds {
  const read = { ...DEFAULT_WORKAROUNDS, fpsCap: Number(value(options, FPS_KEY)) || 0 };
  for (const [flag, pairs] of FLAGS) read[flag] = pairs.every(([key, v]) => value(options, key) === v);
  return read;
}

/** Whether lsfg-vk's own variable is set: the game was turned on here. */
export function hasLsfgLaunch(options: string): boolean {
  return value(options, PROFILE_KEY) !== null;
}

/** decky-lsfg-vk's workaround state for a game, as these. */
export function fromWrapperState(state: Record<string, unknown> | null | undefined): Partial<LsfgWorkarounds> {
  if (!state) return {};
  return {
    disableGamescopeWsi: Boolean(state.disableGamescopeWsi),
    disableHdr: Boolean(state.disableHdr),
    disableSteamDeck: Boolean(state.disableSteamdeckMode),
    disableVkBasalt: Boolean(state.disableVkbasalt),
    zink: Boolean(state.enableZink),
    fpsCap: Number(state.dxvkFrameRate) || 0,
  };
}

/** A value for a launch option, quoted for the shell Steam runs it with. */
function quoted(text: string) {
  return `"${text.replace(/(["\\$`])/g, "\\$1")}"`;
}

/** The launch options without anything lsfg-vk put in, decky-lsfg-vk's wrapper included. */
export function withoutLsfg(options: string): string {
  let out = withoutEnv(options, PROFILE_KEY);
  out = withoutEnv(out, FPS_KEY);
  for (const [, pairs] of FLAGS) {
    for (const [key, v] of pairs) if (value(out, key) === v) out = withoutEnv(out, key);
  }
  out = out.replace(WRAPPER_RE, " ").replace(/\s+/g, " ").trim();
  return out === "%command%" ? "" : out;
}

/** The launch options for lsfg-vk on with this profile and these workarounds, everything else kept. */
export function lsfgLaunchOptions(current: string, profileName: string, workarounds: LsfgWorkarounds): string {
  let out = withEnv(withoutLsfg(current), PROFILE_KEY, quoted(profileName));
  if (workarounds.fpsCap > 0) out = withEnv(out, FPS_KEY, String(Math.round(workarounds.fpsCap)));
  for (const [flag, pairs] of [...FLAGS].reverse()) {
    if (workarounds[flag]) for (const [key, v] of [...pairs].reverse()) out = withEnv(out, key, v);
  }
  return out;
}
