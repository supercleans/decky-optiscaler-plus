import { callable } from "@decky/api";
import type {
  AutoPlanResult,
  Channel,
  ChannelVersions,
  Component,
  ComponentsStatus,
  FrameGeneration,
  DropinStatus,
  Fsr4Status,
  Game,
  GameCompat,
  GameDetail,
  GameUpdateResult,
  HelixsrStatus,
  HlxBuildStatus,
  Library,
  OptipatcherStatus,
  PdPluginStatus,
  PdUploadStatus,
  ReframeworkStatus,
  MonitorReport,
  PayloadStatus,
  PluginUpdate,
  Recommendation,
  Upscaler,
  VerifyResult,
  WikiSearchResult,
  WikiStatus,
} from "./types";

export interface BrowseResult {
  path: string | null;
  parent: string | null;
  entries: { path: string; name: string }[];
}

export interface ActionResult {
  ok: boolean;
  error?: string;
  [key: string]: unknown;
}

export const getStatus = callable<[], PayloadStatus>("get_status");

export const listLibraries = callable<[], Library[]>("list_libraries");
export const addCustomLibrary = callable<[path: string, name?: string], ActionResult>(
  "add_custom_library"
);
export const removeCustomLibrary = callable<[path: string], ActionResult>(
  "remove_custom_library"
);

export const listGames = callable<[libraryPath: string, source: string], Game[]>("list_games");
/** Compatibility badges for a batch of games, keyed by path. Walks each folder
    the first time, so ask a page at a time rather than for the whole list. */
export const assessGames = callable<
  [games: Pick<Game, "path" | "name" | "size_on_disk">[], force?: boolean],
  Record<string, GameCompat>
>("assess_games");
export const getGame = callable<[gamePath: string, name?: string], GameDetail>("get_game");
/* `shortcut` carries what the Steam client said about a non-Steam entry, which
   is the only place a shortcut's install folder can come from. Call it through
   `resolveGame` in shortcuts.ts rather than directly. */
export const findRunningGame = callable<
  [appid: string, shortcut?: { exe?: string; start_dir?: string; name?: string }],
  { found: boolean; appid?: string; name?: string; path?: string; detail?: GameDetail }
>("find_running_game");
/**
 * Write the upscaler's preset into a game's ini again — for when OptiScaler's
 * overlay saved different values over it.
 */
export const applyFsr4Preset = callable<
  [targetDir: string],
  ActionResult & { fsr4?: Fsr4Status }
>("apply_fsr4_preset");
export const setGameTarget = callable<[gamePath: string, targetDir: string], ActionResult>(
  "set_game_target"
);

/**
 * Keep this game's Steam launch options as they were before the install, so
 * removing OptiScaler can put them back. Written once per install.
 */
export const recordLaunchOptions = callable<
  [targetDir: string, options: string | null, appid?: string | null],
  ActionResult & { recorded: boolean; value: string; written: boolean }
>("record_launch_options");

/**
 * What Steam passes a game, read out of its own config file. The fallback for
 * client builds with no `GetAppLaunchOptions`, where nothing else can tell.
 */
export const getLaunchOptions = callable<
  [appid: string],
  { found: boolean; value: string; source: string | null }
>("get_launch_options");

/** Small UI answers the user asked to be remembered, e.g. launch options. */
export const getPref = callable<[key: string, fallback?: unknown], { key: string; value: unknown }>(
  "get_pref"
);
export const setPref = callable<[key: string, value: unknown], ActionResult>("set_pref");

export const getRecommendation = callable<
  [name: string, extraNames?: string[], force?: boolean, gamePath?: string],
  Recommendation
>("get_recommendation");
export const searchWiki = callable<
  [query: string, limit?: number],
  { results: WikiSearchResult[]; entry_count: number; meta: { error: string | null } }
>("search_wiki");
export const setWikiEntry = callable<[gamePath: string, entryName: string], ActionResult>(
  "set_wiki_entry"
);
export const verifyInstall = callable<[targetDir: string], VerifyResult>("verify_install");
export const refreshWiki = callable<
  [],
  { count: number; meta: { source: string; fetched_at: number | null; error: string | null } }
>("refresh_wiki");

/** Whether the compatibility list is reachable at all, and what failed if not. */
export const getWikiStatus = callable<[force?: boolean], WikiStatus>("wiki_status");

export const getAutoPlan = callable<
  [name: string, extraNames?: string[], force?: boolean, gamePath?: string],
  AutoPlanResult
>("get_auto_plan");
export const setAutoMode = callable<[gamePath: string, enabled: boolean], ActionResult>(
  "set_auto_mode"
);
export const autoInstall = callable<
  [
    targetDir: string,
    gamePath?: string,
    name?: string,
    extraNames?: string[],
    /** Overrides the entry's OptiPatcher column; left out, the entry decides. */
    optipatcher?: boolean,
    /** The upscaler picked; left out, a reinstall keeps the one the game has. */
    upscaler?: Upscaler,
  ],
  ActionResult & Partial<AutoPlanResult>
>("auto_install");
export const applyAutoSettings = callable<
  [targetDir: string, gamePath?: string, name?: string, extraNames?: string[]],
  ActionResult & Partial<AutoPlanResult>
>("apply_auto_settings");

export const listAllGames = callable<[], Game[]>("list_all_games");

export const install = callable<
  [
    targetDir: string,
    filename: string,
    preserveIni: boolean,
    optipatcher: boolean,
    upscaler?: Upscaler,
  ],
  ActionResult
>("install");
/** The HelixSR build HLX DLSS comes from: HelixSR Desktop's, else the plugin's. */
export const getHelixsrStatus = callable<[], HelixsrStatus>("get_helixsr_status");
/** Start HelixSR's setup building HLX DLSS here, once the user agreed to NVIDIA's licence. */
export const buildHlxDlss = callable<[], { ok: boolean; error?: string; build: HlxBuildStatus }>(
  "build_hlx_dlss"
);
export const getHlxDlssBuild = callable<[], HlxBuildStatus>("get_hlx_dlss_build");
export const cancelHlxDlssBuild = callable<[], { ok: boolean }>("cancel_hlx_dlss_build");
/** What the plugin has downloaded and whether it is set up; no network. */
export const getComponents = callable<[], ComponentsStatus>("get_components");
/** The same, after asking the channels for newer builds (every few hours, or now with force). */
export const checkUpdates = callable<[force?: boolean], ComponentsStatus>("check_updates");
type JobStart = { ok: boolean; error?: string; components?: ComponentsStatus };
/** Download everything; build HLX DLSS and install lsfg-vk too when asked. */
export const startSetup = callable<[buildHlxDlss?: boolean, installLsfgvk?: boolean], JobStart>(
  "start_setup"
);
export const updateComponent = callable<[component: Component], JobStart>("update_component");
/** lsfg-vk for one game: installed, Lossless Scaling's state, its profile. */
export const getFrameGeneration = callable<[appid: string], FrameGeneration>("get_frame_generation");
/** Turn lsfg-vk on for a game with these settings, or off with null. */
export const setFrameGeneration = callable<
  [appid: string, name: string, settings: Partial<LsfgSettings> | null],
  FrameGeneration
>("set_frame_generation");
export type LsfgSettings = {
  multiplier: number;
  flow_scale: number;
  performance_mode: boolean;
  override_present_mode: boolean;
  preserve_swapchain_image_count: boolean;
};
/** A game leaves decky-lsfg-vk's ~/.lsfg: its workarounds there, and whether the wrapper itself went. */
export const releaseLsfgWrapper = callable<
  [appid: string],
  { workarounds: Record<string, unknown> | null; removed: boolean }
>("release_lsfg_wrapper");
/** Remove everything downloaded; games keep what is installed in them. */
export const removeDownloads = callable<[], JobStart>("remove_downloads");
export const getChannelVersions = callable<[channel: Channel], ChannelVersions>(
  "get_channel_versions"
);
export const setChannelVersion = callable<[channel: Channel, tag: string | null], ActionResult>(
  "set_channel_version"
);
export const uninstall = callable<[targetDir: string, removeIni: boolean], ActionResult>(
  "uninstall"
);

/** Put the release's stock ini back, with the FSR 4 Lite preset written into it. */
export const resetConfig = callable<[targetDir: string], ActionResult>("reset_config");

export const getReframeworkStatus = callable<
  [targetDir: string, gamePath?: string, name?: string, extraNames?: string[]],
  ReframeworkStatus
>("get_reframework_status");
export const installReframework = callable<
  [targetDir: string, gamePath?: string, name?: string, extraNames?: string[]],
  ActionResult & { installed?: boolean; files?: string[]; page?: string }
>("install_reframework");

export const removeReframework = callable<[targetDir: string], ActionResult>(
  "remove_reframework"
);

/** Whether the user has supplied PDPerfPlugin.dll, which this plugin may not ship. */
export const getPdPluginStatus = callable<[], PdPluginStatus>("get_pd_plugin_status");
/** Take PDPerfPlugin.dll (or the zip/7z it came in) from a path the file picker chose. */
export const importPdPlugin = callable<
  [path: string],
  ActionResult & { verified?: boolean; message?: string; status?: PdPluginStatus }
>("import_pd_plugin");
/** Open the one-file upload page a phone on the same Wi-Fi sends PDPerfPlugin.dll to. */
export const startPdUpload = callable<[], ActionResult & PdUploadStatus>("start_pd_upload");
export const getPdUploadStatus = callable<[], ActionResult & PdUploadStatus>(
  "get_pd_upload_status"
);
export const stopPdUpload = callable<[], ActionResult>("stop_pd_upload");
/** Put the user's PDPerfPlugin.dll (and libxess.dll at the root) into a set-up game. */
export const installPdPlugin = callable<
  [targetDir: string],
  ActionResult & { files?: string[] }
>("install_pd_plugin");

export const getOptipatcherStatus = callable<[targetDir: string], OptipatcherStatus>(
  "get_optipatcher_status"
);
export const installOptipatcher = callable<
  [targetDir: string, enabled: boolean],
  ActionResult
>("install_optipatcher");

export const getMonitor = callable<[targetDir: string], MonitorReport>("get_monitor");
export const clearLog = callable<[targetDir: string], ActionResult>("clear_log");
export const setLogging = callable<[targetDir: string, enabled: boolean], ActionResult>(
  "set_logging"
);

/** This plugin's latest release against the running version; `force` asks now. */
export const checkPluginUpdate = callable<[force?: boolean], PluginUpdate>(
  "check_plugin_update"
);
/** Install the downloaded nightly again in every game set up from an older one. */
export const updateInstalledGames = callable<
  [],
  { ok: boolean; error?: string; tag: string | null; results: GameUpdateResult[] }
>("update_installed_games");

/** Whether a game can take the FSR drop-in (FSR 4 in its own FSR 3.1), and its state. */
export const getDropin = callable<[gamePath: string], DropinStatus>("get_dropin");
export const installDropin = callable<[gamePath: string, upscaler?: Upscaler], ActionResult>(
  "install_dropin"
);
export const removeDropin = callable<[gamePath: string], ActionResult>("remove_dropin");
