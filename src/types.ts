/**
 * The OptiScaler build installs are made from: the newest nightly, downloaded
 * on the first install and shared by every game after it.
 */
export interface PayloadStatus {
  /** e.g. "10.0.0-pre1"; null until a nightly has been downloaded. */
  version: string | null;
  /** The release tag, e.g. "nightly-20261027". */
  tag: string | null;
  published_at: string | null;
  /** When the nightly channel was last asked, in seconds since the epoch. */
  checked_at: number | null;
  release_page: string;
  /** Whether a nightly is downloaded at all. */
  archive_present: boolean;
  extracted: boolean;
  extract_path: string | null;
  extractor: string | null;
  /** Why the last check failed, verbatim. */
  error: string | null;
  /** "10.0.0-pre1 (nightly-20261027)", or null before the first download. */
  optiscaler_version: string | null;
  /** The downloaded OptiPatcher rolling build installs use; label null before the first. */
  optipatcher?: {
    label: string | null;
    checked_at: number | null;
    error: string | null;
    page: string;
  };
  proxy_filenames: string[];
  default_proxy: string;
}

export interface Library {
  path: string;
  name: string;
  source: "steam" | "custom";
  game_count: number;
  available: boolean;
}

export interface Game {
  appid: string | null;
  name: string;
  path: string;
  source: "steam" | "custom";
  size_on_disk: number;
  installed?: boolean;
  filename?: string | null;
  install_path?: string | null;
  /** Which library it was found in; only set by the flat all-games list. */
  library?: string;
  /** Installed by this plugin (it has a manifest), rather than by hand. */
  managed?: boolean;
  /** The OptiScaler version and nightly tag it was installed from. */
  optiscaler_version?: string | null;
  optiscaler_tag?: string | null;
  /** Has OptiPatcher, an older build than installs use now. */
  optipatcher_outdated?: boolean;
  /** Which OptiScaler build and upscaler it was set up with. */
  engine?: Engine | null;
  upscaler?: Upscaler | null;
  /** Installed from an older nightly, or an older HelixSR build, than installs use now. */
  outdated?: boolean;
}

/**
 * The upscaler a game is set up for, picked before anything else. FSR 4 Lite
 * is OptiScaler's nightly; cyboman's two FSR 4.1.2 Lite builds are a drop-in
 * where the game ships FSR 3.1 and go into OptiScaler where it does not; HLX
 * FSR 4 likewise, with HelixSR Scaler; HLX DLSS needs HelixSR Scaler.
 */
export type Upscaler =
  | "fsr4-lite"
  | "fsr412l-exact"
  | "fsr412l-lossy"
  | "hlx-fsr4"
  | "hlx-dlss";
/** The OptiScaler build an install came from. */
export type Engine = "nightly" | "helixsr";

/**
 * The HelixSR build HLX DLSS comes from, as found on disk: HelixSR Desktop's,
 * or else the one this plugin had HelixSR's setup make.
 */
export interface HelixsrStatus {
  found: boolean;
  /** HelixSR's releases page, where HelixSR Desktop is downloaded. */
  page: string;
  root?: string;
  version?: string | null;
  scaler_version?: string | null;
  /** HLX DLSS is built and HelixSR Scaler is there to run it. */
  dlss_ready?: boolean;
  /** Built by this plugin, in a HelixSR release it downloaded. */
  plugin?: boolean;
}

/** One step of the plugin's set-up or of an update. */
export interface JobStep {
  key: "nightly" | "dropin" | "helixsr" | "hlx_dlss";
  label: string;
  state: "pending" | "running" | "done" | "failed" | "skipped";
  /** The build it got, why it failed, or why it was skipped. */
  detail: string | null;
}

/** The plugin's set-up or an update of one of its downloads, under way or the last one. */
export interface JobStatus {
  running: boolean;
  kind: "setup" | "update" | null;
  channel: Channel | null;
  steps: JobStep[];
  error: string | null;
  ok: boolean | null;
  started_at: number | null;
  finished_at: number | null;
}

/** One of the plugin's downloads: what is on the Deck and what is newer. */
export interface ComponentChannel {
  /** The build set up (or last updated to), if still on disk. */
  installed: string | null;
  /** False where this machine cannot pick it (cyboman's on a BC-250). */
  used: boolean;
  pinned: string | null;
  /** The newest build, when the channels have been asked. */
  latest: string | null;
  update: boolean;
  /** OptiScaler's own version, for the nightly. */
  version?: string | null;
  /** HelixSR: HelixSR Desktop's, the plugin's, or none yet. */
  source?: "desktop" | "plugin" | null;
  desktop_version?: string | null;
  desktop_root?: string | null;
  dlss_ready?: boolean;
  /** HLX DLSS is wanted with the plugin's HelixSR: a HelixSR update builds it again. */
  dlss_enabled?: boolean;
  /** HelixSR Desktop's HelixSR was used here and is gone. */
  desktop_missing?: boolean;
}

/** Everything the plugin has downloaded, and whether it is set up. */
export interface ComponentsStatus {
  setup_done: boolean;
  job: JobStatus;
  build: HlxBuildStatus;
  channels: Record<Channel, ComponentChannel>;
  /** The channels with a newer build to update to. */
  updates: Channel[];
  checked_at: number | null;
  update_error: string | null;
}

/** HLX DLSS being built, or last built, by HelixSR's setup on this Deck. */
export interface HlxBuildStatus {
  running: boolean;
  /** What the setup is doing, in its own words. */
  step: string | null;
  /** How far the network build is, once it is under way. */
  percent: number | null;
  /** The setup's last lines. */
  log: string[];
  error: string | null;
  ok: boolean | null;
  /** The HelixSR release being built. */
  tag: string | null;
  started_at: number | null;
  finished_at: number | null;
  helixsr?: HelixsrStatus;
}

/** A downloaded channel whose build can be pinned in Settings. */
export type Channel = "nightly" | "dropin" | "helixsr";

export interface ChannelVersion {
  tag: string;
  published_at: string | null;
  /** The newest build when this plugin was built: where the list starts. */
  baseline: boolean;
  /** Already on this Deck, so picking it needs no download. */
  downloaded: boolean;
}

/** The builds a channel can be pinned to, newest first, and the one it is. */
export interface ChannelVersions {
  ok: boolean;
  channel: Channel;
  /** The pinned tag, or null for the newest. */
  pinned: string | null;
  baseline: string | null;
  versions: ChannelVersion[];
  /** Why the list is only what is on this Deck (offline), or null. */
  error?: string | null;
}

/** Whether a newer release of this plugin is out, and what Decky needs for it. */
export interface PluginUpdate {
  current: string;
  /** plugin.json's name: the folder Decky installed it under. */
  name: string;
  latest: string | null;
  update_available: boolean;
  url: string | null;
  sha256: string | null;
  size: number | null;
  page: string;
  published_at: string | null;
  checked_at: number;
  error: string | null;
}

/** One game in a batch update to the downloaded nightly. */
export interface GameUpdateResult {
  name: string;
  path: string;
  from: string | null;
  to: string | null;
  ok: boolean;
  skipped: boolean;
  error: string | null;
}

/**
 * How likely OptiScaler is to work in a game, from its files and the wiki.
 * `listed`/`partial`/`broken` are the wiki's word; `likely`/`risky`/`unknown`
 * come from the folder alone; `unsupported` is what the folder rules out
 * whatever the wiki says.
 */
export type CompatStatus =
  | "listed"
  | "likely"
  | "partial"
  | "risky"
  | "unknown"
  | "broken"
  | "unsupported"
  | "error";

export interface GameCompat {
  status: CompatStatus;
  /** Whether the "Compatible" filter shows it. */
  compatible: boolean;
  /** The game ships FSR 3.1 as a DX12 DLL, so the FSR drop-in can replace it. */
  dropin?: boolean;
  /** The wiki says OptiScaler needs REFramework here. */
  reframework?: boolean;
  /** ...and there is no drop-in to reach FSR 4 without it. */
  reframework_only?: boolean;
  /** The wiki's OptiPatcher column: its patterns cover this game. */
  optipatcher?: boolean;
  /** What the list row says the game cannot go without besides OptiScaler, by name. */
  requires?: string[];
  summary: string;
  wiki?: {
    name: string;
    compatibility: string;
    inputs: string;
    status: "works" | "partial" | "broken" | null;
    manual: boolean;
  } | null;
  /** Upscaler inputs whose libraries the game ships: DLSS, XeSS, FSR2, FSR3.1. */
  inputs?: string[];
  input_files?: string[];
  exe?: string | null;
  arch?: string | null;
  anti_cheat?: string[];
  /** False when the folder was too large to walk in full. */
  complete?: boolean;
}

export interface ExeCandidate {
  path: string;
  relative: string;
  score: number;
  executables: string[];
}

export interface GpuInfo {
  names: string[];
  name: string | null;
  gfx: string | null;
  vendor: string | null;
  generation: string | null;
  fsr4: "native" | "int8" | "experimental" | "unsupported" | "unknown";
  /** The machines the upscaler recommendation differs on; null for any other. */
  device?: "steamdeck" | "bc250" | null;
}

export interface FfxUpscalerInfo {
  present: boolean;
  name: string;
  /** The FidelityFX version OptiScaler's overlay prints in its FFX box. */
  version: string | null;
  fsr4_capable: boolean;
  /** HLX FSR 4 sits in its place, and the version is AMD's beside it. */
  hlx?: boolean;
}

/** One FSR 4 Lite preset key: what the plugin writes against what the ini says. */
export interface PresetKey {
  section: string;
  key: string;
  wanted: string;
  actual: string | null;
  ok: boolean;
}

/**
 * Whether a game folder is set up for its upscaler: the preset in the ini.
 * Read back from the folder, so an overlay that saved other values over the
 * preset shows here.
 */
export interface Fsr4Status {
  /** The upscaler whose preset this is judged against. */
  upscaler?: Upscaler;
  preset: { applied: boolean; keys: PresetKey[] };
  ready: boolean;
  ffx: FfxUpscalerInfo;
}

/** The Steam launch options a game had before OptiScaler was installed. */
export interface LaunchRecord {
  /** False when nothing was kept — Steam would not say. */
  recorded: boolean;
  /** Recorded and empty means the game genuinely had none. */
  value: string;
}

export interface InstallInfo {
  path: string;
  installed: boolean;
  filename: string | null;
  managed: boolean;
  /** The OptiScaler version it was installed from, e.g. "10.0.0-pre1". */
  version: string | null;
  /** The nightly it was installed from, e.g. "nightly-20261027"; helixsr-<version> for HelixSR. */
  tag?: string | null;
  engine?: Engine | null;
  upscaler?: Upscaler | null;
  installed_at: number | null;
  ini_present: boolean;
  ini_path: string;
  log_present: boolean;
  log_path: string;
  candidates: string[];
  extra_proxies: string[];
  backup_dir: string;
  backed_up: string[];
  launch_record: LaunchRecord;
  fsr4: Fsr4Status;
  /**
   * Whether REFramework's dll is next to the executable, and whether this
   * plugin is the one that put it there. Read from the folder rather than the
   * manifest: the step is "is REF present", not "did we install REF", and
   * somebody's own working copy counts.
   */
  reframework: { installed: boolean; revision: string | null; managed: boolean };
}

export interface IniInfo {
  present: boolean;
  keys: number;
}

export interface GameDetail {
  path: string;
  name: string;
  ini_info: IniInfo;
  wiki_entry: string | null;
  gpu: GpuInfo;
  /** The nightly a reinstall would use now; null before the first download. */
  current_tag?: string | null;
  target: string;
  target_is_saved: boolean;
  candidates: ExeCandidate[];
  install: InstallInfo;
  launch_option: string;
  reframework: ReframeworkStatus;
  writable: boolean;
}

export interface VerifyResult {
  ok: boolean;
  error?: string;
  path: string;
  files: {
    name: string;
    present: boolean;
    matches_payload: boolean;
    size: number;
    expected_size: number;
  }[];
  problems: string[];
  complete: boolean;
  /** Installed from an older nightly than the one downloaded now. */
  outdated: boolean;
  installed_tag: string | null;
  current_tag: string | null;
  ffx_upscaler: FfxUpscalerInfo;
  fsr4: Fsr4Status;
}

/** Why the compatibility list is or is not answering. */
export interface WikiStatus {
  url: string;
  entry_count: number;
  available: boolean;
  /** "cache" (last good fetch), "bundled" (shipped with the plugin), or "none". */
  source: string | null;
  fetched_at: number | null;
  /** Seconds since it was fetched, or null when there is no list at all. */
  age: number | null;
  stale: boolean;
  /** Content fingerprint; changes when a background refresh brought something new. */
  revision: string;
  /** True while a refresh is running behind the answer already given. */
  revalidating: boolean;
  last_attempt: number | null;
  /** The failure verbatim — the sentence that says which problem this is. */
  error: string | null;
  /** Which CA source the last successful fetch used. */
  tls: string | null;
  cache_path: string;
}

export interface WikiSearchResult {
  name: string;
  page: string | null;
  compatibility: string;
  inputs: string;
  score: number;
}

export interface Recommendation {
  matched: boolean;
  searched: string[];
  entry_count: number;
  list_available: boolean;
  near_misses: { name: string; page: string | null; score: number }[];
  manual?: boolean;
  game: string | null;
  /** The wiki detail page behind this answer, when there is one. */
  page?: string | null;
  /**
   * True when this game has a wiki page that is not cached yet. The answer is
   * the compatibility-list row; a fuller one is being fetched behind it.
   */
  detail_pending?: boolean;
  filename: string;
  filename_source: string;
  alternatives: string[];
  compatibility: string | null;
  inputs: string | null;
  notes: string | null;
  optipatcher: boolean;
  wiki_url: string | null;
  detail: Record<string, string>;
  match_score: number | null;
  list_meta: {
    source: string;
    fetched_at: number | null;
    error: string | null;
    /** Whether a background refresh is worth waiting a moment for. */
    stale?: boolean;
    /** Content fingerprint: when this changes, the list behind the answer did. */
    revision?: string;
  };
}

/** One INI key the wiki asked for, with where in the entry it was stated. */
export interface PlannedSetting {
  section: string;
  key: string;
  value: string;
  label: string;
  source: string;
}

/**
 * REFramework, for the RE Engine games that cannot host OptiScaler without it.
 *
 * `automatic` is the whole question: when it is true this plugin can fetch the
 * right build itself, and when it is false `reason` says why not and `page` is
 * where to get it by hand. `plugin` is the one file that is never automatic —
 * PureDark's UpscalerBasePlugin lives behind a Nexus Mods login — so the pd
 * entries name it and link it instead of pretending it has been handled.
 */
export interface PlannedReframework {
  required: boolean;
  /** "nightly" (praydog's unified build) or "pd-upscaler" (per game). */
  variant: string;
  dll: string;
  /** The WINEDLLOVERRIDES stem REFramework needs from Proton. */
  override: string;
  source: string;
  detail: string;
  asset: string | null;
  url: string | null;
  page: string;
  plugin: string | null;
  plugin_name: string | null;
  plugin_url: string | null;
  /** The user has supplied PDPerfPlugin.dll, so it goes in with REFramework. */
  plugin_ready?: boolean;
  /** ...and it is the 1.1.2 build the wiki names. */
  plugin_verified?: boolean;
  /** Where the user leaves the downloaded file (their Downloads folder). */
  plugin_folder?: string;
  automatic: boolean;
  reason: string | null;
}

/**
 * PDPerfPlugin.dll, which the pd-upscaler games need and this plugin may not
 * redistribute: the user downloads it and leaves it in `folder`.
 */
export interface PdPluginStatus {
  present: boolean;
  /** The 1.1.2 build the wiki names (1.2.0 does not load the back-end). */
  verified: boolean;
  name: string;
  build: string;
  url: string;
  folder: string;
  /** Where the file picker opens: the SD card and USB drives, else home. */
  picker_start?: string;
}

/** The phone-to-Deck upload page for PDPerfPlugin.dll. */
export interface PdUploadStatus {
  active: boolean;
  /** http://<deck address>:<port>/<token>, while the page is open. */
  url: string | null;
  expires_at: number | null;
  /** What the last upload came to, as the phone was told. */
  result: { ok: boolean; verified?: boolean; message: string } | null;
}

/** What is actually next to the executable, against what the entry asked for. */
export interface ReframeworkStatus {
  required: boolean;
  installed: boolean;
  dll: string;
  path: string;
  revision: string | null;
  plugin: string | null;
  plugin_installed: boolean;
  plugin_url: string | null;
  plugin_name: string | null;
  /**
   * Whether everything this game needs is actually present. REFramework in and
   * OptiScaler in is not the same as "this game will do anything": the
   * pd-upscaler games do not upscale at all until PDPerfPlugin.dll is there,
   * and without this the panel reports a loaded, entirely inert install as
   * working.
   */
  complete: boolean;
}

/** The frame-generation pairing a wiki entry recommends. */
export interface PlannedFrameGen {
  input: string;
  output: string;
  input_label: string;
  output_label: string;
  source: string;
  detail: string;
}

/**
 * Everything the wiki says about setting one game up, as instructions.
 *
 * `available` is false when no compatibility entry matched, which is what the
 * whole automatic path is gated on: with no entry there is nothing to be
 * automatic about, and the UI offers manual setup alone.
 */
export interface AutoPlan {
  available: boolean;
  /** Whether this game's settings are currently driven by the wiki. */
  enabled?: boolean;
  game: string | null;
  /** "wiki entry" (a page written for this game) or "compatibility list". */
  source: string | null;
  wiki_url: string | null;
  filename: string;
  filename_source: string;
  optipatcher: boolean;
  /** Game arguments to append after %command%, e.g. -dx12. */
  launch_flags: string[];
  /** The complete Steam launch options string, override and arguments. */
  launch_options: string;
  settings: PlannedSetting[];
  framegen: PlannedFrameGen | null;
  /**
   * The overlay shortcut this plan changes, when an entry asks for one. Several
   * REFramework games do, because REF's overlay uses Insert too — and applying
   * that without saying so is how "Insert does nothing" gets reported as the
   * overlay being broken, when it had simply moved.
   */
  hotkey: { value: string; name: string | null; source: string } | null;
  /** Set only for the games whose entry says OptiScaler needs REFramework. */
  reframework: PlannedReframework | null;
  /** What else the game needs that this plugin cannot put in: mods, files, Engine.ini. */
  requirements?: PlannedRequirement[];
  /** Things the wiki named that could not be turned into a setting. */
  unresolved: { text: string; source: string }[];
  warnings: string[];
}

/**
 * Something a game needs besides OptiScaler, read out of its wiki entry: a mod
 * OptiScaler hooks into, a file to copy, Engine.ini lines, an anti-cheat to
 * switch off. Said, never installed.
 */
export interface PlannedRequirement {
  key: string;
  kind: "mod" | "file" | "config" | "game";
  /** What the checklist calls it, e.g. "Luma 모드". */
  name: string;
  /** False where the entry only suggests it ("might", "for less crashing"). */
  required: boolean;
  /** The wiki's own sentence (or, for a whole table, what the table says). */
  detail: string;
  source: string;
  link: string | null;
}

export interface AutoPlanResult {
  recommendation: Recommendation;
  plan: AutoPlan;
}

export interface LogEntry {
  time: string | null;
  level: string;
  message: string;
}

export interface MonitorReport {
  path: string;
  log_path: string;
  log_present: boolean;
  log_size: number;
  log_modified: number | null;
  logging_enabled: string | null;
  state: Record<string, string | null>;
  counts: Record<string, number>;
  frame_generation: string[];
  problems: LogEntry[];
  recent: LogEntry[];
  hints: string[];
  configured: Record<string, string>;
  total_lines?: number;
  error?: string;
}

export interface RunningGame {
  appid: number;
  name: string;
  gameid: string;
}

/** Whether OptiPatcher is downloaded here and installed for one game. */
export interface OptipatcherStatus {
  available: boolean;
  installed: boolean;
  /** "rolling (2026-10-27)"; null when there is no build to install. */
  version: string | null;
  /** Installed, but not the build installs use now. */
  outdated: boolean;
  /** HelixSR Scaler's own copy, used as it comes with the Scaler. */
  bundled?: boolean;
}

/** The FSR drop-in for one game: possible, and whether it is in place. */
export interface DropinStatus {
  possible: boolean;
  installed: boolean;
  dir?: string;
  layout?: "split" | "monolithic";
  /** False when a game update has put the game's own DLL back. */
  intact?: boolean;
  tag?: string | null;
  variant?: string | null;
  installed_at?: number | null;
  releases?: string;
  optiscaler_installed?: boolean;
  /** Which upscaler the drop-in in place is. */
  upscaler?: Upscaler;
}
