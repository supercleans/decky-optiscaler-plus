import React from "react";
import { createRoot } from "react-dom/client";
// React 18.3 exports act itself; the react-dom/test-utils re-export logs a
// deprecation warning on every run, which the pass condition below counts.
import { act } from "react";
import { fixtures, calls } from "@decky/api";
import { ManagerPage } from "../src/components/ManagerPage";
import { QuickPanel } from "../src/components/QuickPanel";
import { optipatcherMissed } from "../src/components/OptipatcherPanel";
import { HelixsrGuide, HlxBuildConsent } from "../src/components/UpscalerPanel";
import { ComponentNotice, ComponentsSection } from "../src/components/Components";
import { publishComponents } from "../src/hooks/useComponents";

// ---- fixtures mirroring what the Python backend returns --------------------
// The FSR 4 Lite preset as installer.preset_state reads it back from the ini.
const presetKeys = (ok: boolean) => [
  { section: "Upscalers", key: "Dx12Upscaler", wanted: "ffx", actual: "ffx", ok: true },
  { section: "Upscalers", key: "Dx12Upscaler", wanted: "ffx", actual: "ffx", ok: true },
  { section: "Upscalers", key: "Dx11Upscaler", wanted: "ffx_12", actual: ok ? "ffx_12" : "fsr22", ok },
];
const fsr4 = (ready: boolean) => ({
  preset: { applied: ready, keys: presetKeys(ready) },
  ready,
  // The version OptiScaler's overlay prints in its FFX Settings box.
  ffx: { present: true, name: "amd_fidelityfx_upscaler_dx12.dll",
         version: "4.1.1.2740", fsr4_capable: true },
});

const detail = {
  path: "/games/Cyberpunk 2077",
  name: "Cyberpunk 2077",
  target: "/games/Cyberpunk 2077/bin/x64",
  target_is_saved: false,
  candidates: [
    { path: "/games/Cyberpunk 2077/bin/x64", relative: "bin/x64", score: 53, executables: ["Cyberpunk2077.exe"] },
    { path: "/games/Cyberpunk 2077", relative: ".", score: -40, executables: ["REDprelauncher.exe"] },
  ],
  install: {
    path: "/games/Cyberpunk 2077/bin/x64",
    installed: true, filename: "dxgi.dll", managed: true, version: "10.0.0-pre1",
    installed_at: 1700000000, ini_present: true, ini_path: "/x/OptiScaler.ini",
    log_present: true, log_path: "/x/OptiScaler.log",
    candidates: ["dxgi.dll"], extra_proxies: [],
    backup_dir: "/games/Cyberpunk 2077/bin/x64/decky_optiscaler_backup_files",
    backed_up: ["dxgi.dll", "amd_fidelityfx_upscaler_dx12.dll"],
    // What Steam was passing before OptiScaler went in, kept so removing it
    // can put it back rather than clearing a field it never owned.
    launch_record: { recorded: true, value: "gamemoderun %command%" },
    fsr4: fsr4(true),
    reframework: { installed: false, revision: null, managed: false },
  },
  reframework: { required: false, installed: false, dll: "dinput8.dll",
                 path: "/games/Cyberpunk 2077/bin/x64/dinput8.dll", revision: null,
                 plugin: null, plugin_installed: false, plugin_url: null,
                 plugin_name: null, complete: true },
  ini_info: { present: true, keys: 288 },
  wiki_entry: null,
  gpu: { names: ["Van Gogh (Steam Deck)"], name: "Van Gogh (Steam Deck)", gfx: "gfx1033",
         vendor: "amd", generation: "RDNA2", fsr4: "experimental" },
  launch_option: 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
  writable: true,
};

// The plugin set up: everything downloaded, HelixSR the plugin's own.
const idleJob = { running: false, kind: null, channel: null, steps: [], error: null, ok: null,
                  started_at: null, finished_at: null };
const idleBuild = { running: false, step: null, percent: null, log: [], error: null, ok: null,
                    tag: null, started_at: null, finished_at: null };
const setUp = {
  setup_done: true, job: idleJob, build: idleBuild,
  channels: {
    nightly: { installed: "nightly-20261027", version: "10.0.0-pre1", used: true, pinned: null,
               latest: "nightly-20261027", update: false },
    dropin: { installed: "dll-2026-10-29", used: true, pinned: "dll-2026-10-29",
              latest: "dll-2026-10-29", update: false },
    helixsr: { installed: "v3.2.0", used: true, pinned: null, latest: "v3.2.0", update: false,
               source: "plugin", desktop_version: null, desktop_root: null, dlss_ready: false,
               desktop_missing: false },
  },
  updates: [], checked_at: 1787000000, update_error: null,
};

Object.assign(fixtures, {
  get_components: setUp,
  check_updates: () => fixtures.get_components,
  start_setup: () => ({ ok: true, components: fixtures.get_components }),
  update_component: () => ({ ok: true, components: fixtures.get_components }),
  remove_downloads: () => ({ ok: true, components: fixtures.get_components }),
  get_status: {
    version: "10.0.0-pre1", tag: "nightly-20261027", published_at: "2026-10-27T09:40:46Z",
    checked_at: 1787000000,
    release_page: "https://github.com/optiscaler/OptiScaler-nightly/releases",
    archive_present: true, extracted: true, extract_path: "/runtime/payload/nightly-20261027",
    extractor: "7z", error: null,
    optiscaler_version: "10.0.0-pre1 (nightly-20261027)",
    optipatcher: { label: "rolling (2026-10-27)", checked_at: 1787000000, error: null,
                   page: "https://github.com/optiscaler/OptiPatcher/releases/tag/rolling" },
    proxy_filenames: ["dxgi.dll","winmm.dll","version.dll","dbghelp.dll","d3d12.dll","wininet.dll","winhttp.dll","OptiScaler.asi"],
    default_proxy: "dxgi.dll",
  },
  // Two of the listed games: one ships FSR 3.1 itself, one has to have REFramework.
  assess_games: (games: { path: string }[]) => Object.fromEntries(games.map((g) => [g.path,
    g.path === "/games/test-0"
      ? { status: "listed", compatible: true, summary: "위키 ✅ · FSR3.1", dropin: true,
          reframework: true, reframework_only: false }
      : g.path === "/games/test-1"
        ? { status: "listed", compatible: true, summary: "위키 ✅ · DLSS", dropin: false,
            reframework: true, reframework_only: true, optipatcher: true, requires: ["Luma 모드"] }
        : { status: "unknown", compatible: false, summary: "DLSS/XeSS/FSR 라이브러리 없음" }])),
  get_dropin: { possible: false, installed: false },
  install_dropin: { ok: true },
  // No HelixSR build on this Deck until a test says otherwise.
  get_helixsr_status: { found: false, page: "https://github.com/lonewolf0622/HelixSR/releases/latest" },
  // No HLX DLSS build has run.
  get_hlx_dlss_build: { running: false, step: null, percent: null, log: [], error: null, ok: null,
                        tag: null, started_at: null, finished_at: null },
  get_channel_versions: (channel: string) => channel === "nightly"
    ? { ok: true, channel, pinned: null, baseline: "nightly-20261027", error: null, versions: [
        { tag: "nightly-20261028", published_at: "2026-10-28T10:00:00Z", baseline: false, downloaded: false },
        { tag: "nightly-20261027", published_at: "2026-10-27T10:00:00Z", baseline: true, downloaded: true },
      ] }
    : { ok: true, channel, pinned: "dll-2026-10-29", baseline: "dll-2026-10-29", error: null, versions: [
        { tag: "dll-2026-10-29", published_at: "2026-10-29T17:00:00Z", baseline: true, downloaded: true },
      ] },
  set_channel_version: (channel: string, tag: string | null) => ({ ok: true, channel, pinned: tag }),
  remove_dropin: { ok: true },
  // A newer plugin release is out.
  check_plugin_update: {
    current: "0.1.1", name: "Decky Upscaler Manager", latest: "0.1.2", update_available: true,
    url: "https://github.com/supercleans/decky-upscaler-manager/releases/download/v0.1.2/Decky-Upscaler-Manager-v0.1.2.zip",
    sha256: "ab".repeat(32), size: 1, page: "https://github.com/supercleans/decky-upscaler-manager/releases",
    published_at: "2026-10-29T00:00:00Z", checked_at: 1787000000, error: null,
  },
  update_installed_games: {
    ok: true, tag: "nightly-20261027",
    results: [{ name: "Cyberpunk 2077", path: "/games/Cyberpunk 2077", from: "nightly-20261026",
                to: "nightly-20261027", ok: true, skipped: false, error: null }],
  },
  list_libraries: [
    { path: "/home/deck/.local/share/Steam", name: "Internal Storage", source: "steam", game_count: 2, available: true },
    { path: "/run/media/SD", name: "SD Card (SD)", source: "custom", game_count: 1, available: true },
  ],
  list_games: [
    { appid: "1091500", name: "Cyberpunk 2077", path: "/games/Cyberpunk 2077", source: "steam", size_on_disk: 1, installed: true, filename: "dxgi.dll", install_path: "/games/Cyberpunk 2077/bin/x64" },
    { appid: "2358720", name: "Black Myth Wukong", path: "/games/BMW", source: "steam", size_on_disk: 1, installed: false, filename: null, install_path: null },
  ],
  // The flat list the main page leads with: enough entries to page through.
  list_all_games: [
    // Set up from an older nightly than the one downloaded: the batch update's case.
    { appid: "1091500", name: "Cyberpunk 2077", path: "/games/Cyberpunk 2077", source: "steam", library: "Internal Storage", size_on_disk: 1, installed: true, filename: "dxgi.dll", install_path: "/games/Cyberpunk 2077/bin/x64", managed: true, optiscaler_version: "10.0.0-pre1", optiscaler_tag: "nightly-20261026", engine: "nightly", upscaler: "fsr4-lite", outdated: true },
    ...Array.from({ length: 27 }, (_, i) => ({
      appid: String(3000000 + i), name: `Test Game ${String(i + 1).padStart(2, "0")}`,
      path: `/games/test-${i}`, source: "steam", library: "Internal Storage",
      size_on_disk: 1, installed: false, filename: null, install_path: null,
    })),
  ],
  get_game: detail,
  find_running_game: { found: true, appid: "1091500", name: "Cyberpunk 2077", path: "/games/Cyberpunk 2077", detail },
  get_recommendation: {
    matched: true, searched: ["Cyberpunk 2077"], entry_count: 685,
    list_available: true, near_misses: [], game: "Cyberpunk 2077", filename: "dxgi.dll",
    filename_source: "wiki entry", alternatives: ["wininet.dll"],
    compatibility: "✅", inputs: "DLSS, FSR3, FSR3.1/4, XeSS",
    notes: "Use [this mod](http://x) to fix it.", optipatcher: false,
    wiki_url: "https://x", detail: { "FG Inputs": "DLSSG via Streamline", "Known Issues": "Avoid FSR-FG inputs!" },
    match_score: 1.0, list_meta: { source: "network", fetched_at: 1, error: null },
  },
  // What the wiki lookup and the plan built from it look like together. The
  // settings and the FG pair are the shape autoplan.py produces from a real
  // entry: keys it resolved against the schema, each citing the field it was
  // read out of, plus the things it could not place.
  get_auto_plan: {
    recommendation: {
      matched: true, searched: ["Cyberpunk 2077"], entry_count: 685,
      list_available: true, near_misses: [], game: "Cyberpunk 2077", filename: "dxgi.dll",
      filename_source: "wiki entry", alternatives: ["wininet.dll"],
      compatibility: "✅", inputs: "DLSS, FSR3, FSR3.1/4, XeSS",
      notes: "Use [this mod](http://x) to fix it.", optipatcher: false,
      wiki_url: "https://x", detail: { "FG Inputs": "DLSSG via Streamline", "Known Issues": "Avoid FSR-FG inputs!" },
      match_score: 1.0,
      list_meta: { source: "cache", fetched_at: 1, error: null, stale: false,
                   revision: "aaaaaaaaaaaa" },
    },
    plan: {
      available: true, enabled: false, game: "Cyberpunk 2077", source: "wiki entry",
      wiki_url: "https://x", filename: "dxgi.dll", filename_source: "wiki entry",
      optipatcher: false,
      launch_flags: ["-dx12"],
      launch_options: 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12',
      settings: [
        { section: "Spoofing", key: "Dxgi", value: "false", label: "Dxgi",
          source: "wiki entry, “Settings”" },
        { section: "Hotfix", key: "RestoreComputeSignature", value: "true",
          label: "RestoreComputeSignature", source: "wiki entry, “Known Issues”" },
      ],
      framegen: {
        input: "dlssg", output: "fsrfg", input_label: "DLSSG via Streamline",
        output_label: "FSR FG", source: "wiki entry, “FG Inputs”",
        detail: "DLSSG via Streamline",
      },
      hotkey: null,
      reframework: null,
      unresolved: [{ text: "DontCreateD3D12DeviceForLuma=true (not an OptiScaler setting)",
                     source: "wiki entry, “Notes”" }],
      warnings: [],
    },
  },
  install_reframework: { ok: true, installed: true, files: ["dinput8.dll"] },
  remove_reframework: { ok: true, removed: ["dinput8.dll"], restored: ["dinput8.dll"] },
  set_auto_mode: { ok: true, enabled: true },
  auto_install: { ok: true, applied: [], rejected: [] },
  apply_auto_settings: { ok: true, applied: [] },
  reset_config: { ok: true },
  get_monitor: {
    path: "/x", log_path: "/x/OptiScaler.log", log_present: true, log_size: 2048,
    log_modified: Date.now() / 1000, logging_enabled: "true",
    state: { upscaler: "FSR 4.0.2", proxy: "dxgi.dll", gpu: "AMD Custom GPU 0405", game_name: "Cyberpunk 2077", wine: "9.0", game_exe: "Cyberpunk2077.exe", game_version: "2.2", optiscaler_version: null },
    counts: { info: 40, warning: 2, error: 1 },
    frame_generation: ["XeFG"],
    problems: [{ time: "12:00:00.0", level: "error", message: "Failed to create FG context" }],
    recent: [{ time: "12:00:00.0", level: "info", message: "OptiScaler working as dxgi.dll" }],
    configured: { fg_enabled: "true", fg_input: "fsrfg" },
    total_lines: 43,
  },
  clear_log: { ok: true },
  // Answered per key: the Settings tab reads each remembered question in turn,
  // and a single fixture would make every one of them look answered.
  get_pref: (key: string, fallback?: unknown) =>
    key === "remove_launch_options"
      ? { key, value: "restore" }
      : { key, value: fallback ?? null },
  set_pref: { ok: true },
  record_launch_options: { ok: true, recorded: true, value: "gamemoderun %command%" },
  apply_fsr4_preset: { ok: true },
  get_pd_plugin_status: { present: false, verified: false, name: "PDPerfPlugin.dll",
                          build: "UpscalerBasePlugin 1.1.2",
                          url: "https://www.nexusmods.com/site/mods/502",
                          folder: "/home/deck/Downloads" },
  get_optipatcher_status: { available: true, installed: false,
                            version: "rolling (2026-10-27)", outdated: false },
  verify_install: {
    ok: true, path: "/x", complete: true, problems: [], outdated: false,
    installed_tag: "nightly-20261027", current_tag: "nightly-20261027",
    files: [{ name: "dxgi.dll", present: true, matches_payload: true, size: 1, expected_size: 1 }],
    ffx_upscaler: { present: true, name: "amd_fidelityfx_upscaler_dx12.dll",
                    version: "4.1.1.2740", fsr4_capable: true },
    fsr4: fsr4(true),
  },
  search_wiki: { results: [
    { name: "Forza Horizon 5", page: "Forza-Horizon-5", compatibility: "OK", inputs: "DLSS", score: 1 },
  ], entry_count: 685, meta: { error: null } },
  set_wiki_entry: { ok: true },
  wiki_status: {
    url: "https://raw.githubusercontent.com/wiki/optiscaler/OptiScaler/Compatibility-List.md",
    entry_count: 685, available: true, source: "cache", fetched_at: 1787000000,
    age: 3600, stale: false, revision: "aaaaaaaaaaaa", revalidating: false,
    last_attempt: 1787000000, error: null, tls: "default",
    cache_path: "/runtime/wiki-cache/compat-list.json",
  },
  refresh_wiki: { count: 685, meta: { source: "network", fetched_at: 1, error: null } },
  set_logging: { ok: true },
  browse: { path: "/home/deck", parent: "/home", entries: [{ path: "/home/deck/Games", name: "Games" }] },
  add_custom_library: { ok: true },
  remove_custom_library: { ok: true },
  set_game_target: { ok: true },
  install: { ok: true },
});

// ---- harness ---------------------------------------------------------------
const errors: string[] = [];
const originalError = console.error;
console.error = (...args: any[]) => {
  errors.push(args.map(String).join(" "));
  originalError(...args);
};

async function settle() {
  for (let i = 0; i < 8; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5));
    });
  }
}

function findAll(node: Element, selector: string) {
  return Array.from(node.querySelectorAll(selector));
}

async function render(name: string, element: React.ReactElement) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(element);
  });
  await settle();
  return { name, host, root };
}

(async () => {
  console.log("=== rendering QuickPanel (game running, installed) ===");
  const qp = await render(
    "QuickPanel",
    <QuickPanel
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onOpenManager={() => {}}
    />
  );
  console.log(`  text includes game name: ${qp.host.textContent!.includes("Cyberpunk 2077")}`);
  console.log(`  a newer plugin release is announced in the panel: ${
    qp.host.textContent!.includes("Decky Upscaler Manager 0.1.2 버전이 나왔습니다")}`);

  // The sidebar panel is the plugin's front door, so the tabs and the games
  // list have to be here and not only on the full page.
  const qpTabs = findAll(qp.host, "[data-tab]").map((n) => n.getAttribute("data-tab"));
  console.log(`  sidebar tabs: ${qpTabs.join(", ")}`);
  const activeTab = findAll(qp.host, '[data-tab][data-active="true"]')[0];
  console.log(`  opens on the running game: ${activeTab?.getAttribute("data-tab") === "now"}`);
  // Settings are OptiScaler's own overlay's now: the panel says whether the
  // game is set up and where to change things, and offers no controls.
  console.log(`  says the game is set up, and with FSR 4 Lite: ${
    qp.host.textContent!.includes("dxgi.dll") && qp.host.textContent!.includes("FSR 4 Lite")}`);
  console.log(`  points at the overlay for settings: ${
    qp.host.textContent!.includes("OptiScaler 오버레이(Insert 키)")}`);
  console.log(`  no settings controls of its own: ${
    findAll(qp.host, '[data-mock="DropdownItem"]').length === 0 &&
    findAll(qp.host, '[data-mock="ToggleField"]').length === 0}`);
  console.log(`  no live readout left behind: ${!/\bfps\b/i.test(qp.host.textContent!)}`);

  const gamesTab = findAll(qp.host, '[data-tab="games"]')[0] as HTMLElement;
  await act(async () => {
    gamesTab.click();
  });
  await settle();
  const qpGames = qp.host.textContent!;
  // "Now Playing" is the tab's own label, so the body is what has to change.
  console.log(`  switching to Games swaps the body: ${!qpGames.includes("설치 및 로그")}`);
  // Filters, not tabs: they narrow the same list rather than swapping the view.
  // Recent is absent here because the harness has no Steam client to ask for a
  // last-played time, which is exactly when it must not be offered.
  const filters = findAll(qp.host, "[data-filter]").map((n) => n.getAttribute("data-filter"));
  console.log(`  sidebar filters: ${filters.join(", ")}`);
  // It opens on the games already set up: the ones being come back to.
  const openFilter = findAll(qp.host, '[data-filter][data-active="true"]')[0];
  console.log(`  sidebar opens on the set-up games: ${
    openFilter?.getAttribute("data-filter") === "setup"
    && qpGames.includes("Cyberpunk 2077") && !qpGames.includes("Test Game 01")}`);
  console.log(`  sidebar links to the full page: ${qpGames.includes("라이브러리 및 설정")}`);
  await act(async () => {
    (findAll(qp.host, '[data-filter="all"]')[0] as HTMLElement).click();
  });
  await settle();
  const allGames = qp.host.textContent!;
  console.log(`  sidebar lists games: ${allGames.includes("Test Game 01")}`);
  // The panel is narrow and short: four rows a page, one line each.
  console.log(`  sidebar pages at 4: ${allGames.includes("Test Game 03") && !allGames.includes("Test Game 04")}`);
  console.log(`  sidebar rows are one line, no reasons: ${!allGames.includes("Internal Storage")}`);
  console.log(`  sidebar says which range it shows: ${allGames.includes("1–4 / 28")}`);
  await act(async () => {
    (findAll(qp.host, '[data-page="next"]')[0] as HTMLElement).click();
  });
  await settle();
  const nextPage = qp.host.textContent!;
  // A page replaces the one before rather than growing the list under it.
  console.log(`  Next replaces the page: ${
    nextPage.includes("Test Game 04") && nextPage.includes("Test Game 07")
    && !nextPage.includes("Test Game 03") && nextPage.includes("5–8 / 28")}`);
  await act(async () => {
    (findAll(qp.host, '[data-page="previous"]')[0] as HTMLElement).click();
  });
  await settle();
  await act(async () => {
    (findAll(qp.host, '[data-page="previous"]')[0] as HTMLElement).click();
  });
  await settle();
  // Wrapping, so the pager never ends in a dead button with the focus on it.
  console.log(`  Prev on the first page wraps to the last: ${qp.host.textContent!.includes("25–28 / 28")}`);
  await act(async () => {
    (findAll(qp.host, '[data-page="next"]')[0] as HTMLElement).click();
  });
  await settle();
  console.log(`  and Next on the last wraps to the first: ${qp.host.textContent!.includes("1–4 / 28")}`);
  await act(async () => {
    (findAll(qp.host, '[data-filter="setup"]')[0] as HTMLElement).click();
  });
  await settle();
  const setUpOnly = qp.host.textContent!;
  console.log(`  filtering to the ones set up drops the rest: ${
    setUpOnly.includes("Cyberpunk 2077") && !setUpOnly.includes("Test Game 01")}`);
  await act(async () => {
    (findAll(qp.host, '[data-filter="all"]')[0] as HTMLElement).click();
  });
  await settle();

  // And back, without losing the running game.
  const nowTab = findAll(qp.host, '[data-tab="now"]')[0] as HTMLElement;
  await act(async () => {
    nowTab.click();
  });
  await settle();
  console.log(`  switching back restores Now Playing: ${
    qp.host.textContent!.includes("설치 및 로그")}`);

  console.log("\n=== rendering ManagerPage (main page) ===");
  const mp = await render("ManagerPage", <ManagerPage />);
  const mpTabs = findAll(mp.host, "[data-tab]").map((n) => n.getAttribute("data-tab"));
  console.log(`  main tabs: ${mpTabs.join(", ")}`);
  console.log(`  the games list opens on the set-up games: ${
    findAll(mp.host, '[data-filter][data-active="true"]')[0]?.getAttribute("data-filter") === "setup"}`);
  await act(async () => {
    (findAll(mp.host, '[data-filter="all"]')[0] as HTMLElement).click();
  });
  await settle();
  const mpText = mp.host.textContent!;
  // Every tab's content is rendered by the mock, so all three are visible here.
  console.log(`  games listed by name: ${mpText.includes("Cyberpunk 2077")}`);
  console.log(`  library shown for each game: ${mpText.includes("Internal Storage")}`);
  console.log(`  custom library listed: ${mpText.includes("SD Card")}`);
  console.log(`  games are paged, not all 28 at once: ${!mpText.includes("Test Game 27")}`);
  console.log(`  first page shows 20: ${mpText.includes("Test Game 19") && !mpText.includes("Test Game 20")}`);
  console.log(`  offers the next page: ${mpText.includes("1–20 / 28") && findAll(mp.host, '[data-page="next"]').length > 0}`);
  console.log(`  running game leads the page: ${mpText.includes("Cyberpunk 2077")}`);
  // How FSR 4 gets into a game is said in the list: its own FSR 3.1 swapped,
  // or OptiScaler with REFramework where there is no other way.
  console.log(`  a game with its own FSR 3.1 is marked for the drop-in: ${
    mpText.includes("FSR 드롭인 가능") && mpText.includes("드롭인")}`);
  console.log(`  a game that cannot go without REFramework is marked so: ${
    mpText.includes("REFramework 필수") && mpText.includes("REF 필수")}`);
  // A drop-in game the wiki still sends through REFramework for OptiScaler
  // says both: the drop-in needs nothing, the OptiScaler way needs REF.
  console.log(`  a drop-in game still says OptiScaler would need REFramework: ${
    mpText.includes("OptiScaler는 REFramework 필요")}`);
  console.log(`  a game the wiki lists for OptiPatcher is marked: ${
    mpText.includes("OptiPatcher 권장")}`);
  console.log(`  a game that needs a mod first is marked, and says which: ${
    mpText.includes("모드 필요") && mpText.includes("Luma 모드 필요")}`);
  console.log(`  no dead steam-menu status row: ${!mpText.includes("Steam menu shortcut")}`);

  // -- opening the page at one game -----------------------------------------
  // Picking a game used to land on the page's Now Playing tab: the deep link
  // travelled as a query string and the Steam client's router does not hand
  // that back to the route it renders. It travels in-process now, so both the
  // Quick Access panel (folder and name) and the Steam context menu (an app id
  // to look up) reach the game they named.
  console.log("\n=== opening the page at one game ===");
  {
    const { openManager } = await import("../src/navigation");
    openManager({ path: detail.path, name: detail.name, appid: "1091500" });
    const deep = await render("ManagerPage (deep link)", <ManagerPage />);
    console.log(`  a named game opens its own page, not Now Playing: ${
      findAll(deep.host, '[data-tab="now"]').length === 0 &&
      deep.host.textContent!.includes("파일로 설치됨")}`);

    // Nothing named: the library list, as before.
    const plain = await render("ManagerPage (no target)", <ManagerPage />);
    console.log(`  opening it with no game still lists them: ${
      findAll(plain.host, '[data-tab="games"]').length === 1}`);

    // The context menu knows only the app id, and the page is already open.
    await act(async () => {
      openManager({ appid: "1091500" });
    });
    await settle();
    console.log(`  an app id is looked up, even while the page is open: ${
      findAll(plain.host, '[data-tab="now"]').length === 0 &&
      plain.host.textContent!.includes("파일로 설치됨")}`);

    // A non-Steam shortcut has no app manifest, so Steam has no install folder
    // to report and this used to be where every one of them stopped: "Steam
    // did not report an install folder for this game". Its target is the
    // answer, and the client is the only side that can read it — the backend's
    // shortcuts.vdf is flushed on Steam's schedule, so a shortcut added this
    // session is not in it yet. What matters here is that the target actually
    // travels with the lookup rather than being dropped on the way.
    const previousLookup = fixtures.find_running_game;
    let handed: any = null;
    fixtures.find_running_game = (_appid: string, shortcut: any) => {
      handed = shortcut;
      return previousLookup;
    };
    (globalThis as any).appDetailsStore = {
      GetAppDetails: () => ({
        strShortcutExe: '"/home/deck/Games/Some Game/Binaries/Win64/Game.exe"',
        strShortcutStartDir: '"/home/deck/Games/Some Game"',
        strDisplayName: "Some Game",
      }),
    };
    await act(async () => {
      openManager({ appid: "3060399406" });
    });
    await settle();
    console.log(`  a non-Steam shortcut's target is handed to the lookup: ${
      handed?.exe === '"/home/deck/Games/Some Game/Binaries/Win64/Game.exe"' &&
      handed?.start_dir === '"/home/deck/Games/Some Game"' &&
      handed?.name === "Some Game"}`);

    // A Steam game has no shortcut fields at all, and asking for them must not
    // turn into a target made up out of nothing.
    (globalThis as any).appDetailsStore = { GetAppDetails: () => ({}) };
    handed = undefined;
    await act(async () => {
      openManager({ appid: "1091500" });
    });
    await settle();
    console.log(`  and a Steam game hands over nothing rather than an empty one: ${
      handed === undefined}`);
    (globalThis as any).appDetailsStore = undefined;
    fixtures.find_running_game = previousLookup;
  }

  console.log("\n=== steam library context menu ===");
  {
    const { __testing: menu } = await import("../src/libraryContextMenu");
    // The shapes Steam actually renders: a game menu carries an item whose
    // handler mentions launchSource, and Properties mentions AppProperties.
    const gameMenu = () => [
      { key: "a", props: { onSelected: () => "launchSource: LibraryDetails" } },
      { key: "b", props: { onSelected: () => "AddToHiddenCollection" } },
      { key: "properties", props: { onSelected: () => "AppProperties(x)" } },
    ];
    const screenshotMenu = [
      { key: "s1", props: { onSelected: () => "UploadScreenshot" } },
      { key: "s2", props: { onSelected: () => "DeleteScreenshot" } },
    ];

    console.log(`  game menu recognised: ${menu.isAppContextMenu(gameMenu())}`);
    console.log(`  other menus left alone: ${!menu.isAppContextMenu(screenshotMenu)}`);

    const items = gameMenu();
    menu.spliceMenuItem(items, 1091500);
    const idx = items.findIndex((x: any) => x?.key === menu.MARKER);
    const propIdx = items.findIndex((x: any) => x?.key === "properties");
    console.log(`  entry inserted: ${idx !== -1}`);
    console.log(`  entry sits above Properties: ${idx !== -1 && idx < propIdx}`);
    console.log(`  entry is labelled "${menu.MENU_LABEL}": ${
      (items[idx] as any)?.props?.children === menu.MENU_LABEL}`);

    // Steam re-renders the same menu; it must not stack duplicates.
    menu.removeExisting(items);
    menu.spliceMenuItem(items, 1091500);
    console.log(`  no duplicates after a re-render: ${
      items.filter((x: any) => x?.key === menu.MARKER).length === 1}`);

    // The appid captured on first render goes stale when Steam reuses the menu.
    const stale = 1018880;
    const withOverview: any[] = [
      { _owner: { pendingProps: { overview: { appid: 1091500 } } }, props: {} },
    ];
    console.log(`  stale appid replaced from the menu's own overview: ${
      menu.resolveAppid(withOverview, stale) === 1091500}`);
    const newClient: any[] = [{ props: { children: { app: { appid: 2358720 } } } }];
    console.log(`  newer clients resolved through props.children: ${
      menu.resolveAppid(newClient, undefined) === 2358720}`);
    const noAppid = menu.patchMenuItems([], undefined);
    console.log(`  nothing inserted without an appid: ${noAppid === undefined}`);
  }

  console.log("\n=== rendering GameDetail with every tab ===");
  const { GameDetail } = await import("../src/components/GameDetail");
  const gd = await render(
    "GameDetail",
    <GameDetail
      gamePath="/games/Cyberpunk 2077"
      gameName="Cyberpunk 2077"
      appid="1091500"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}}
    />
  );
  const tabs = findAll(gd.host, "[data-tab]").map((n) => n.getAttribute("data-tab"));
  // No settings screen: OptiScaler's overlay is where options are changed.
  console.log(`  setup is the only tab: ${tabs.join(", ") === "install"}`);
  console.log(`  no settings controls, basic or advanced: ${
    !gd.host.textContent!.includes("Frame multiplier") &&
    !gd.host.textContent!.includes("Every OptiScaler option") &&
    findAll(gd.host, "[data-mode-switch]").length === 0}`);
  console.log(`  the header names the FidelityFX build and FSR 4 Lite: ${
    gd.host.textContent!.includes("FFX 4.1.1.2740") && gd.host.textContent!.includes("FSR 4 Lite")}`);
  console.log(`  wiki recommendation shown: ${gd.host.textContent!.includes("위키 항목")}`);

  // -- setting a game up, as a checklist ------------------------------------
  // The Setup tab is the same three steps before and after: what will happen,
  // then what did. Everything else it used to hold is one row away.
  const setupTab = findAll(gd.host, '[data-tab="install"]')[0] as HTMLElement;
  await act(async () => { setupTab.click(); });
  await settle();
  const setupText = gd.host.textContent!;
  console.log(`  monitor is no longer a tab: ${!tabs.includes("monitor")}`);
  console.log(`  the install names the OptiScaler build: ${setupText.includes("OptiScaler 10.0.0-pre1")}`);
  // Every install writes the preset; the row checks it is still what the ini says.
  console.log(`  FSR 4 Lite is a checked row, not a setting: ${
    setupText.includes("FSR 4 Lite 켜짐") && setupText.includes("Insert")}`);
  // A running game is pointed at the overlay rather than at controls here.
  console.log(`  the running game is pointed at the overlay: ${
    setupText.includes("실행 중") && setupText.includes("Insert를 누르면 OptiScaler 오버레이")}`);
  console.log(`  setup states what is installed: ${
    setupText.includes("파일로 설치됨") && setupText.includes("dxgi.dll")}`);
  console.log(`  the wiki step is a toggle, off until asked for: ${
    findAll(gd.host, '[data-mock="ToggleField"][data-label^="위키 항목 따르지 않음"]').length === 1}`);
  console.log(`  and says what turning it on would do: ${
    setupText.includes("켜면 이 게임에 필요한 옵션을 위키에 맞춰 유지합니다")}`);
  // Removing has to be findable without hunting: it is on the tab, not behind
  // the manual page it used to live on.
  console.log(`  removing and resetting stay on the setup tab: ${
    setupText.includes("제거") && setupText.includes("설정 초기화")}`);
  console.log(`  setup no longer shows the manual install controls: ${
    !setupText.includes("파일 이름 지정")}`);
  // Not running is not a step of setting a game up, and was being listed as
  // the last one. What the log says lives on the Logs row either way.
  console.log(`  "not running" is not a setup step: ${!setupText.includes("Not running")}`);

  // "Manual setup" opens in the tab's place, and comes back.
  await act(async () => {
    (findAll(gd.host, '[data-mock="Field"][data-label="수동 설치"]')[0] as HTMLElement).click();
  });
  await settle();
  console.log(`  "manual setup" restores every install control: ${
    gd.host.textContent!.includes("파일 이름 지정") &&
    gd.host.textContent!.includes("dxgi.dll로 다시 설치") &&
    gd.host.textContent!.includes("Steam 실행 옵션")}`);
  const manualText = gd.host.textContent!;
  console.log(`  no live-control or FSR 4 build panels left: ${
    !manualText.includes("Live in-game control") && !manualText.includes("4.1.1b")}`);
  // Which build an install puts in: the nightly downloaded now.
  console.log(`  manual setup names the nightly it installs: ${
    manualText.includes("OptiScaler 10.0.0-pre1 (nightly-20261027)")}`);
  console.log(`  the launch options are spelled out there: ${
    manualText.includes("WINEDLLOVERRIDES")}`);
  // "The plugin cannot read them" and "they are empty" look identical from the
  // outside, and telling them apart took a source-code read the last time it
  // mattered. Both, and what removing would put back, are on the page now.
  console.log(`  and what Steam is actually passing is stated: ${
    manualText.includes("현재 Steam 설정") && manualText.includes("Steam에서 읽을 수 없음")}`);
  console.log(`  next to what removing would put back: ${
    manualText.includes("설치 전") && manualText.includes("gamemoderun %command%")}`);
  console.log(`  backup folder mentioned: ${
    manualText.includes("decky_optiscaler_backup_files")}`);
  // The manual panel is several screens long, so the way out is at both ends.
  console.log(`  the way back is at both ends of it: ${
    findAll(gd.host, '[data-back="setup"]').length === 2}`);
  await act(async () => {
    (findAll(gd.host, '[data-back="setup"]')[0] as HTMLElement).click();
  });
  await settle();
  console.log(`  and back returns to the checklist: ${
    gd.host.textContent!.includes("파일로 설치됨") &&
    !gd.host.textContent!.includes("파일 이름 지정")}`);

  // The old Monitor tab, now a row.
  await act(async () => {
    (findAll(gd.host, '[data-mock="Field"][data-label="로그"]')[0] as HTMLElement).click();
  });
  await settle();
  const logsText = gd.host.textContent!;
  console.log(`  the logs row opens what the Monitor tab used to show: ${
    logsText.includes("OptiScaler 로그 기록")}`);
  console.log(`  with the runtime state it read out of the log: ${
    logsText.includes("FSR 4.0.2")}`);
  await act(async () => {
    (findAll(gd.host, '[data-back="setup"]')[0] as HTMLElement).click();
  });
  await settle();

  // -- a game that is not set up yet ----------------------------------------
  fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
  const gdFresh = await render("GameDetail (not set up)",
    <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const freshText = gdFresh.host.textContent!;
  console.log(`  a matched game says so before anything is written: ${
    freshText.includes("자동 설치할 수 있습니다")}`);
  console.log(`  three steps, named: ${
    freshText.includes("OptiScaler를") &&
    freshText.includes("Steam 실행 옵션 설정") &&
    freshText.includes("설정 2개 적용")}`);
  console.log(`  the install step is required, the other two are toggles: ${
    findAll(gdFresh.host, '[data-mock="ToggleField"][data-label^="Steam 실행 옵션 설정"]').length === 1 &&
    findAll(gdFresh.host, '[data-mock="ToggleField"][data-label^="항목이 요구하는 설정 2개 적용"]').length === 1 &&
    freshText.includes("필수")}`);
  console.log(`  the launch options are shown in full, with the wiki's flag: ${
    freshText.includes('WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12')}`);
  console.log(`  the wiki's settings are named before they are applied: ${
    freshText.includes("Dxgi=false") && freshText.includes("DLSSG via Streamline → FSR FG")}`);
  console.log(`  the button counts what will run: ${freshText.includes("3단계 모두 실행")}`);
  // Switching a step off has to change what the button promises, or the
  // toggles are decoration.
  const wikiStep = findAll(gdFresh.host,
    '[data-mock="ToggleField"][data-label^="항목이 요구하는 설정 2개 적용"]')[0];
  await act(async () => {
    (findAll(wikiStep, "[data-toggle]")[0] as HTMLElement).click();
  });
  await settle();
  console.log(`  turning one off narrows the button: ${
    gdFresh.host.textContent!.includes("2단계 모두 실행")}`);
  console.log(`  no OptiPatcher step where the wiki does not list the game: ${
    !freshText.includes("OptiPatcher 함께 설치")}`);

  // The user's own launch options survive an install: ours go in beside them.
  {
    const written: [number, string][] = [];
    const savedClient = globalThis.SteamClient;
    globalThis.SteamClient = {
      Apps: {
        GetAppLaunchOptions: async () => "mangohud %command% -dx11",
        SetAppLaunchOptions: (id: number, value: string) => { written.push([id, value]); },
      },
    } as any;
    const autoBefore = fixtures.auto_install;
    fixtures.auto_install = { ok: true, applied: [], rejected: [] };
    const lm = await render("GameDetail (not set up, launch options of the user's)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    const merged = 'WINEDLLOVERRIDES="dxgi=n,b" mangohud %command% -dx12';
    console.log(`  the step shows the user's options with ours put in: ${
      lm.host.textContent!.includes(merged)}`);
    const run = findAll(lm.host, '[data-mock="DialogButton"]').find((n) =>
      n.textContent!.includes("단계 모두 실행")) as HTMLElement | undefined;
    await act(async () => { run?.click(); });
    await settle();
    console.log(`  and the install writes that, not the bare override: ${
      written.length === 1 && written[0][0] === 1091500 && written[0][1] === merged}`);
    fixtures.auto_install = autoBefore;
    globalThis.SteamClient = savedClient;
  }

  // -- OptiPatcher, where the wiki's column lists the game -------------------
  {
    const basePlan = fixtures.get_auto_plan;
    fixtures.get_auto_plan = { ...basePlan, plan: { ...basePlan.plan, optipatcher: true } };
    let autoArgs: unknown[] = [];
    fixtures.auto_install = (...args: unknown[]) => {
      autoArgs = args;
      return { ok: true, applied: [], rejected: [] };
    };
    const op = await render("GameDetail (OptiPatcher recommended)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    const opText = op.host.textContent!;
    console.log(`  the checklist offers OptiPatcher, on, saying why: ${
      findAll(op.host, '[data-mock="ToggleField"][data-label^="OptiPatcher 함께 설치"]').length === 1
      && opText.includes("스푸핑") && opText.includes("4단계 모두 실행")}`);
    const opStep = findAll(op.host,
      '[data-mock="ToggleField"][data-label^="OptiPatcher 함께 설치"]')[0];
    await act(async () => {
      (findAll(opStep, "[data-toggle]")[0] as HTMLElement).click();
    });
    await settle();
    console.log(`  and switching it off narrows the button: ${
      op.host.textContent!.includes("3단계 모두 실행")}`);
    const runButton = findAll(op.host, '[data-mock="DialogButton"]').find((n) =>
      n.textContent!.includes("단계 모두 실행")) as HTMLElement | undefined;
    await act(async () => { runButton?.click(); });
    await settle();
    console.log(`  the install is told to leave it out: ${autoArgs[4] === false}`);
    // Downloaded on first use: an install that could not get it says why,
    // from either install's answer, and stays quiet when it went in.
    const offline = { installed: false, error: "인터넷 연결이 필요합니다" };
    console.log(`  an OptiPatcher that could not be downloaded is reported: ${
      optipatcherMissed({ ok: true, optipatcher: offline }) === offline.error
      && optipatcherMissed({ ok: true, install: { optipatcher: offline } }) === offline.error
      && optipatcherMissed({ ok: true, optipatcher: { installed: true, error: null } }) === null
      && optipatcherMissed({ ok: true }) === null}`);
    fixtures.get_auto_plan = basePlan;
    fixtures.auto_install = { ok: true, applied: [], rejected: [] };
  }
  fixtures.get_game = detail;

  // -- the overlay saved over the preset -----------------------------------
  // OptiScaler's overlay writes its own values when Save is pressed there, so
  // the row reads the ini back and offers to put the preset in again.
  console.log("\n=== FSR 4 Lite after the overlay saved over it ===");
  {
    fixtures.get_game = { ...detail, install: { ...detail.install, fsr4: fsr4(false) } };
    const changed = await render("GameDetail (preset changed)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    const changedText = changed.host.textContent!;
    console.log(`  the row says it is off, and which key moved: ${
      changedText.includes("FSR 4 Lite 꺼짐") && changedText.includes("Dx11Upscaler=ffx_12")}`);
    // The header row is the one holding the way back to the games list.
    const header = findAll(changed.host, '[data-back="games"]')[0]?.parentElement;
    console.log(`  the header stops claiming FSR 4 Lite: ${
      Boolean(header) && !header!.textContent!.includes("FSR 4 Lite")}`);
    const before = calls.filter((c) => c === "apply_fsr4_preset").length;
    fixtures.get_game = detail;
    await act(async () => {
      (findAll(changed.host, '[data-mock="Field"]').find((n) =>
        n.textContent!.includes("FSR 4 Lite 꺼짐")) as HTMLElement).click();
    });
    await settle();
    console.log(`  selecting it applies the preset again and re-reads the folder: ${
      calls.filter((c) => c === "apply_fsr4_preset").length === before + 1 &&
      changed.host.textContent!.includes("FSR 4 Lite 켜짐")}`);
  }

  // -- a game that needs REFramework ----------------------------------------
  // Nine entries on the compatibility list say OptiScaler does nothing in this
  // game without REFramework already in the folder. The failure this guards
  // against is not an error message: it is an install that reports success and
  // changes nothing on screen, so the only thing that catches it is checking
  // that the step is on the list at all.
  const plainPlan = fixtures.get_auto_plan;
  const refPlan = (extra: Record<string, unknown>) => ({
    ...plainPlan,
    plan: {
      ...plainPlan.plan,
      launch_options: 'WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" %command% -dx12',
      reframework: {
        required: true, variant: "pd-upscaler", dll: "dinput8.dll", override: "dinput8",
        source: "compatibility list notes",
        detail: "Requires REFramework (pd-upscaler branch) + PDUpscaler plugin",
        asset: "RE2.zip", url: null,
        page: "https://github.com/TheRazerMD/REFramework/releases",
        plugin: "PDPerfPlugin.dll", plugin_name: "UpscalerBasePlugin 1.1.2",
        plugin_url: "https://www.nexusmods.com/site/mods/502",
        plugin_ready: false, plugin_verified: false, plugin_folder: "/home/deck/Downloads",
        automatic: true, reason: null,
        ...extra,
      },
    },
  });

  // -- what else a game needs ---------------------------------------------------
  console.log("\n=== what else a game needs ===");
  {
    const basePlan = fixtures.get_auto_plan;
    fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
    fixtures.get_auto_plan = {
      ...basePlan,
      plan: {
        ...basePlan.plan,
        requirements: [
          { key: "luma", kind: "mod", name: "Luma 모드", required: true,
            detail: "DLSS with Luma Framework", source: "wiki entry, “Upscaler Inputs”",
            link: "https://github.com/Filoppi/Luma-Framework/releases" },
          { key: "nukems", kind: "mod", name: "Nukem's dlssg-to-fsr3", required: false,
            detail: "Use Nukem's for less crashing.", source: "compatibility list notes", link: null },
        ],
      },
    };
    const rq = await render("GameDetail (needs a mod first)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    const rqText = rq.host.textContent!;
    const rows = findAll(rq.host, "[data-requirement]");
    console.log(`  the checklist says what else the game needs, before the steps: ${
      rqText.includes("OptiScaler 말고 필요한 것") && rows.length === 2
      && rqText.indexOf("OptiScaler 말고 필요한 것") < rqText.indexOf("파일로 설치")}`);
    console.log(`  firm and only-offered are told apart: ${
      rows[0]?.textContent!.includes("필수") && rows[1]?.textContent!.includes("권장")}`);
    console.log(`  with the wiki's words and where to get it: ${
      rows[0]?.textContent!.includes("DLSS with Luma Framework")
      && rows[0]?.textContent!.includes("github.com/Filoppi/Luma-Framework/releases")}`);
    fixtures.get_game = detail;
    const rqIn = await render("GameDetail (needs a mod, set up)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    console.log(`  and still says it once the game is set up: ${
      findAll(rqIn.host, "[data-requirement]").length === 2}`);
    fixtures.get_auto_plan = basePlan;
    const none = await render("GameDetail (needs nothing else)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    console.log(`  a game that needs nothing else has no such section: ${
      !none.host.textContent!.includes("OptiScaler 말고 필요한 것")}`);
  }

  // -- the upscaler, picked first ---------------------------------------------
  console.log("\n=== the upscaler, picked first ===");
  {
    const fresh = { ...detail, install: { ...detail.install, installed: false } };
    fixtures.get_game = fresh;
    const view = () => (
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />
    );
    const pick = async (host: HTMLElement, upscaler: string) => {
      await act(async () => {
        (findAll(host, `[data-upscaler="${upscaler}"]`)[0] as HTMLElement).click();
      });
      await settle();
    };
    const runButton = (host: HTMLElement) =>
      findAll(host, '[data-mock="DialogButton"]').find((n) =>
        n.textContent!.includes("단계 모두 실행") || n.textContent!.includes("설치만 하기"));

    const up = await render("GameDetail (upscaler list, no HelixSR)", view());
    const rows = findAll(up.host, "[data-upscaler]").map((n) => n.getAttribute("data-upscaler"));
    console.log(`  the five upscalers are listed: ${
      rows.join(",") === "fsr4-lite,fsr412l-exact,fsr412l-lossy,hlx-fsr4,hlx-dlss"}`);
    console.log(`  without FSR 3.1, FSR 4 Lite goes in through OptiScaler: ${
      findAll(up.host, '[data-upscaler="fsr4-lite"]')[0]?.textContent!.includes("OptiScaler")}`);
    console.log(`  FSR 4 Lite is picked by default: ${
      findAll(up.host, '[data-upscaler="fsr4-lite"]')[0]?.textContent!.includes("●")}`);
    // No FSR 3.1 of its own: cyboman's builds go in through OptiScaler instead.
    console.log(`  without FSR 3.1, cyboman's builds go in through OptiScaler: ${
      ["fsr412l-exact", "fsr412l-lossy"].every((id) => {
        const row = findAll(up.host, `[data-upscaler="${id}"]`)[0];
        return row?.textContent!.includes("OptiScaler") && !row.textContent!.includes("불가");
      })}`);
    const cybomanWith: unknown[][] = [];
    const autoInstallBefore = fixtures.auto_install;
    fixtures.auto_install = (...args: unknown[]) => {
      cybomanWith.push(args);
      return { ok: true };
    };
    await pick(up.host, "fsr412l-lossy");
    console.log(`  and the install step says it takes AMD's place, every API running it: ${
      up.host.textContent!.includes("FSR 4.1.2 Lite lossy를 내려받아")
      && up.host.textContent!.includes("FidelityFX 업스케일러 자리")
      && up.host.textContent!.includes("DX12·DX11·Vulkan")}`);
    await act(async () => { runButton(up.host)?.click(); });
    await settle();
    console.log(`  the install asks for it by name: ${cybomanWith[0]?.[5] === "fsr412l-lossy"}`);
    fixtures.auto_install = autoInstallBefore;
    // A BC-250 starts with HLX FSR 4, recommended; FSR 4 Lite says what it does there.
    {
      const deckGame = fixtures.get_game;
      fixtures.get_game = { ...deckGame, gpu: { ...deckGame.gpu, name: "BC-250", gfx: "gfx1013",
                                                generation: "RDNA1", fsr4: "unsupported", device: "bc250" } };
      const bc = await render("GameDetail (BC-250)", view());
      const hlxRow = findAll(bc.host, '[data-upscaler="hlx-fsr4"]')[0];
      console.log(`  on a BC-250 HLX FSR 4 is picked first, and marked recommended: ${
        hlxRow?.textContent!.includes("●") && hlxRow.textContent!.includes("추천")}`);
      console.log(`  and only HelixSR's two are offered there: ${
        findAll(bc.host, "[data-upscaler]").map((n) => n.getAttribute("data-upscaler")).join(",")
          === "hlx-fsr4,hlx-dlss"}`);
      fixtures.get_game = deckGame;
    }
    // HLX FSR 4 is downloaded: no HelixSR set-up needed, OptiScaler without FSR 3.1.
    const hlxRow = findAll(up.host, '[data-upscaler="hlx-fsr4"]')[0];
    console.log(`  HLX FSR 4 needs no HelixSR set-up, and goes in through OptiScaler here: ${
      hlxRow?.textContent!.includes("OptiScaler") && !hlxRow.textContent!.includes("불가")}`);
    await pick(up.host, "hlx-dlss");
    const noHelix = up.host.textContent!;
    console.log(`  picking HLX DLSS unbuilt offers to build it here, HelixSR Desktop's build used first: ${
      noHelix.includes("HLX DLSS를 빌드해야 합니다") && noHelix.includes("HelixSR Desktop으로 빌드해 둔")
      && noHelix.includes("HLX DLSS 빌드")}`);
    console.log(`  and will not install it: ${
      noHelix.includes("지금은 설치할 수 없습니다") && runButton(up.host)?.getAttribute("data-disabled") === "true"}`);

    // Building it: the agreement first, then its progress, read from the backend.
    const consent = await render("HlxBuildConsent", <HlxBuildConsent onOK={() => {}} />);
    console.log(`  the build asks to agree to NVIDIA's licence first: ${
      consent.host.textContent!.includes("NVIDIA 라이선스")
      && consent.host.textContent!.includes("공유하면 안 됩니다")}`);
    const idleBuild = fixtures.get_hlx_dlss_build;
    fixtures.get_hlx_dlss_build = { ...idleBuild, running: true, percent: 45, tag: "v3.2.0",
                                    step: "[####-----]  45%  3:12  shaders" };
    let rechecked = 0;
    const building = await render("HelixsrGuide (building)",
      <HelixsrGuide helixsr={fixtures.get_helixsr_status} onRecheck={() => { rechecked += 1; }} />);
    console.log(`  a build under way shows how far it is, and can be cancelled: ${
      building.host.textContent!.includes("HLX DLSS 빌드 중 45%")
      && building.host.textContent!.includes("HelixSR v3.2.0")
      && building.host.textContent!.includes("빌드 취소")}`);
    fixtures.get_hlx_dlss_build = { ...idleBuild, ok: false, error: "Proton을 찾지 못했습니다.",
                                    finished_at: 1 };
    await act(async () => { await new Promise((r) => setTimeout(r, 1200)); });
    await settle();
    console.log(`  and when it ends, HelixSR is checked again and a failure is said: ${
      rechecked === 1 && building.host.textContent!.includes("HLX DLSS를 빌드하지 못했습니다")
      && building.host.textContent!.includes("Proton을 찾지 못했습니다")}`);
    fixtures.get_hlx_dlss_build = idleBuild;

    // HelixSR Desktop has built HelixSR on this Deck.
    fixtures.get_helixsr_status = {
      found: true, page: "https://github.com/lonewolf0622/HelixSR/releases/latest", root: "/home/deck/.local/share/HelixSR-Desktop/releases/3.1.0",
      version: "3.1.0", scaler_version: "2.1.0", dlss_ready: true, fsr4_ready: true, scaler_hlx_ready: true,
    };
    const basePlan = fixtures.get_auto_plan;
    fixtures.get_auto_plan = { ...basePlan, plan: { ...basePlan.plan, optipatcher: true } };
    const handed: unknown[][] = [];
    const autoInstall = fixtures.auto_install;
    fixtures.auto_install = (...args: unknown[]) => {
      handed.push(args);
      return { ok: true };
    };
    const hx = await render("GameDetail (HLX DLSS picked)", view());
    await pick(hx.host, "hlx-dlss");
    const hxText = hx.host.textContent!;
    console.log(`  with HelixSR built, HLX DLSS goes in through HelixSR Scaler: ${
      hxText.includes("HelixSR Scaler를") && !hxText.includes("지금은 설치할 수 없습니다")}`);
    console.log(`  HelixSR Scaler's own OptiPatcher is used, so there is no OptiPatcher step: ${
      !hxText.includes("OptiPatcher 함께 설치") && hxText.includes("OptiPatcher도 그대로 함께 켜집니다")}`);
    await act(async () => { runButton(hx.host)?.click(); });
    await settle();
    const [, , , , patcherArg, upscalerArg] = handed[0] ?? [];
    console.log(`  the install asks for HLX DLSS, without the rolling OptiPatcher: ${
      upscalerArg === "hlx-dlss" && patcherArg === false}`);

    // HLX FSR 4 in a game with its own FSR 3.1 is a drop-in.
    fixtures.get_dropin = { possible: true, installed: false, dir: "/games/Cyberpunk 2077/bin/x64",
                            layout: "split", optiscaler_installed: false };
    const droppedWith: unknown[][] = [];
    fixtures.install_dropin = (...args: unknown[]) => {
      droppedWith.push(args);
      return { ok: true };
    };
    const hf = await render("GameDetail (HLX FSR 4 picked, FSR 3.1 game)", view());
    console.log(`  HLX FSR 4 is a drop-in where the game ships FSR 3.1: ${
      findAll(hf.host, '[data-upscaler="hlx-fsr4"]')[0]?.textContent!.includes("드롭인")}`);
    await pick(hf.host, "hlx-fsr4");
    const hfApply = findAll(hf.host, '[data-mock="ButtonItem"]').find((n) =>
      n.textContent!.includes("HLX FSR 4 드롭인 적용")) as HTMLElement | undefined;
    console.log(`  it says it keeps the game's file beside it: ${
      hf.host.textContent!.includes("*.original.dll")}`);
    await act(async () => { hfApply?.click(); });
    await settle();
    console.log(`  applying it asks for the HLX drop-in: ${droppedWith[0]?.[1] === "hlx-fsr4"}`);
    // FSR 4 Lite there is AMD's own FSR 4.1.2 from the nightly, as a test drop-in.
    console.log(`  FSR 4 Lite is a drop-in there too: ${
      findAll(hf.host, '[data-upscaler="fsr4-lite"]')[0]?.textContent!.includes("드롭인")}`);
    await pick(hf.host, "fsr4-lite");
    console.log(`  and says it is a test the Deck may be turned away from: ${
      hf.host.textContent!.includes("시험용입니다")}`);
    const amdApply = findAll(hf.host, '[data-mock="ButtonItem"]').find((n) =>
      n.textContent!.includes("FSR 4 Lite 드롭인 적용")) as HTMLElement | undefined;
    await act(async () => { amdApply?.click(); });
    await settle();
    console.log(`  applying it asks for the FSR 4 Lite drop-in: ${droppedWith[1]?.[1] === "fsr4-lite"}`);
    fixtures.install_dropin = { ok: true };
    fixtures.get_dropin = { possible: false, installed: false };

    // A game set up with FSR 4 Lite can be switched to HLX DLSS in place.
    fixtures.get_game = { ...detail, install: { ...detail.install, engine: "nightly", upscaler: "fsr4-lite" } };
    const installedWith: unknown[][] = [];
    const install = fixtures.install;
    fixtures.install = (...args: unknown[]) => {
      installedWith.push(args);
      return { ok: true };
    };
    const sw = await render("GameDetail (FSR 4 Lite in, HLX DLSS picked)", view());
    console.log(`  the upscaler a game has is marked: ${
      findAll(sw.host, '[data-upscaler="fsr4-lite"]')[0]?.textContent!.includes("적용됨")}`);
    await pick(sw.host, "hlx-dlss");
    const switchRow = findAll(sw.host, '[data-mock="Field"]').find((n) =>
      n.textContent!.includes("HLX DLSS로 바꾸기")) as HTMLElement | undefined;
    console.log(`  picking another offers to switch: ${Boolean(switchRow)}`);
    await act(async () => { switchRow?.click(); });
    await settle();
    const [, keptName, keptIni, , switchedTo] = installedWith[0] ?? [];
    console.log(`  switching reinstalls with it, keeping the file name and the ini: ${
      switchedTo === "hlx-dlss" && keptName === "dxgi.dll" && keptIni === true}`);

    // A game on HelixSR Scaler says so.
    fixtures.get_game = {
      ...detail,
      install: { ...detail.install, engine: "helixsr", upscaler: "hlx-dlss", version: "2.1.0",
                 tag: "helixsr-3.1.0", fsr4: { ...detail.install.fsr4, upscaler: "hlx-dlss" } },
    };
    const hs = await render("GameDetail (on HelixSR Scaler)", view());
    const hsText = hs.host.textContent!;
    console.log(`  a HelixSR Scaler game names its build: ${
      hsText.includes("HelixSR Scaler 2.1.0 (HelixSR 3.1.0)")}`);
    console.log(`  and its upscaler, not FSR 4 Lite: ${
      hsText.includes("HLX DLSS 켜짐") || hsText.includes("HLX DLSS 꺼짐")}`);

    fixtures.install = install;
    fixtures.auto_install = autoInstall;
    fixtures.get_auto_plan = basePlan;
    fixtures.get_helixsr_status = { found: false, page: "https://github.com/lonewolf0622/HelixSR/releases/latest" };
    fixtures.get_game = detail;
  }

  fixtures.get_auto_plan = refPlan({});
  fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
  const gdRef = await render("GameDetail (needs REFramework, not set up)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const refText = gdRef.host.textContent!;
  // -- the FSR drop-in ----------------------------------------------------------
  console.log("\n=== the FSR drop-in ===");
  {
    fixtures.get_dropin = { possible: true, installed: false, dir: "/games/MHW/bin",
                            layout: "monolithic", optiscaler_installed: false };
    const noHelixsr = fixtures.get_helixsr_status;
    fixtures.get_helixsr_status = { ...noHelixsr, found: true, version: "3.1.0", scaler_version: "2.1.0",
                                    dlss_ready: true, fsr4_ready: true, scaler_hlx_ready: true };
    const dg = await render("GameDetail (drop-in possible)",
      <GameDetail gamePath="/games/MHW" gameName="Monster Hunter Wilds" appid="2246340"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    // FSR 4 Lite is the default, and with FSR 3.1 in the game it is a drop-in.
    console.log(`  FSR 4 Lite, the default, is offered as a drop-in: ${
      dg.host.textContent!.includes("FSR 4 Lite 드롭인 적용")}`);
    // A game like Resident Evil Requiem: its own FSR 3.1 takes a drop-in, and
    // the wiki's OptiScaler way (HLX DLSS's HelixSR Scaler here) needs
    // REFramework. Each row says which.
    const scalerRow = findAll(dg.host, '[data-upscaler="hlx-dlss"]')[0];
    const lossyRow = findAll(dg.host, '[data-upscaler="fsr412l-lossy"]')[0];
    console.log(`  the OptiScaler way says it needs REFramework: ${
      scalerRow?.textContent!.includes("REFramework도 있어야 합니다")}`);
    console.log(`  the drop-in says it does not, and is marked the simpler one: ${
      lossyRow?.textContent!.includes("REFramework 없이 동작합니다")
      && lossyRow?.textContent!.includes("간단")}`);
    fixtures.get_helixsr_status = noHelixsr;
    await act(async () => {
      (findAll(dg.host, '[data-upscaler="fsr412l-lossy"]')[0] as HTMLElement).click();
    });
    await settle();
    const dText = dg.host.textContent!;
    console.log(`  a game with its own FSR 3.1 is offered FSR 4 without OptiScaler: ${
      dText.includes("FSR 드롭인") && dText.includes("OptiScaler와 REFramework가 필요 없습니다")}`);
    console.log(`  and says what it will replace: ${dText.includes("AMD 로더")}`);
    const before = calls.filter((c) => c === "install_dropin").length;
    const apply = findAll(dg.host, '[data-mock="ButtonItem"]').find((n) =>
      n.textContent!.includes("드롭인 적용")) as HTMLElement | undefined;
    await act(async () => { apply?.click(); });
    await settle();
    console.log(`  applying it asks the backend once: ${
      calls.filter((c) => c === "install_dropin").length === before + 1}`);

    fixtures.get_dropin = { possible: true, installed: true, intact: false, tag: "dll-2026-10-29",
                            variant: "4.1.2l-lossy", upscaler: "fsr412l-lossy",
                            dir: "/games/MHW/bin", layout: "split" };
    const dg2 = await render("GameDetail (drop-in undone by an update)",
      <GameDetail gamePath="/games/MHW" gameName="Monster Hunter Wilds" appid="2246340"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    console.log(`  a game update that put the original back is said, with a way to re-apply: ${
      dg2.host.textContent!.includes("원래 파일이 돌아왔습니다") && dg2.host.textContent!.includes("다시 적용")}`);

    // One build in, the other picked: it offers to swap them.
    fixtures.get_dropin = { possible: true, installed: true, intact: true, tag: "dll-2026-10-29",
                            variant: "4.1.2l-lossy", upscaler: "fsr412l-lossy",
                            dir: "/games/MHW/bin", layout: "split" };
    const swap = await render("GameDetail (Lite lossy in, Lite exact picked)",
      <GameDetail gamePath="/games/MHW" gameName="Monster Hunter Wilds" appid="2246340"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    await act(async () => {
      (findAll(swap.host, '[data-upscaler="fsr412l-exact"]')[0] as HTMLElement).click();
    });
    await settle();
    console.log(`  picking the other 4.1.2 build offers to swap it in: ${
      swap.host.textContent!.includes("FSR 4.1.2 Lite exact로 바꾸기")}`);

    fixtures.get_dropin = { possible: true, installed: false, dir: "/games/X", layout: "split",
                            optiscaler_installed: true };
    const dg3 = await render("GameDetail (drop-in with OptiScaler in)",
      <GameDetail gamePath="/games/X" gameName="X" appid={null}
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    await act(async () => {
      (findAll(dg3.host, '[data-upscaler="fsr412l-lossy"]')[0] as HTMLElement).click();
    });
    await settle();
    console.log(`  with OptiScaler in, it says the two do not mix and offers no button: ${
      dg3.host.textContent!.includes("함께 쓸 수 없습니다") &&
      !findAll(dg3.host, '[data-mock="ButtonItem"]').some((n) => n.textContent!.includes("드롭인 적용"))}`);
    fixtures.get_dropin = { possible: false, installed: false };
  }

  console.log("\n=== a game that needs REFramework ===");
  console.log(`  the step is on the list before anything is written: ${
    refText.includes("REFramework 설치")}`);
  console.log(`  it says why, citing the entry that said so: ${
    refText.includes("이 게임에 후킹할 수 없습니다") &&
    refText.includes("compatibility list notes")}`);
  console.log(`  and which of the two builds it is: ${
    refText.includes("이 게임용 pd-upscaler 빌드")}`);
  console.log(`  it is required, not a toggle like the other two steps: ${
    findAll(gdRef.host, '[data-mock="ToggleField"][data-label^="REFramework 설치"]').length === 0}`);
  console.log(`  so the button counts four steps, not three: ${
    refText.includes("4단계 모두 실행")}`);
  // Proton ships its own dinput8 and loads that in preference to the game
  // folder, so REF needs an override exactly as OptiScaler's proxy does. The
  // wiki never says so — it is written for Windows.
  console.log(`  REFramework gets a WINEDLLOVERRIDES entry of its own: ${
    refText.includes('WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" %command% -dx12')}`);
  console.log(`  and the row says why both are needed: ${
    refText.includes("두 모드 모두 작동하지 않습니다")}`);
  // The one file that can never be automatic: not ours to ship, behind a login.
  console.log(`  PDPerfPlugin.dll is the user's to download, and says from where: ${
    refText.includes("PDPerfPlugin.dll 직접 받기") &&
    refText.includes("https://www.nexusmods.com/site/mods/502") &&
    refText.includes("저작권")}`);
  console.log(`  and where to put it, with a way to look again: ${
    refText.includes("/home/deck/Downloads") &&
    findAll(gdRef.host, '[data-mock="ButtonItem"]').some((n) => n.textContent!.includes("다시 확인"))}`);
  const recheckButton = findAll(gdRef.host, '[data-mock="ButtonItem"]').find((n) =>
    n.textContent!.includes("다시 확인")) as HTMLElement | undefined;
  const plansBefore = calls.filter((c) => c === "get_auto_plan").length;
  await act(async () => { recheckButton?.click(); });
  await settle();
  console.log(`  looking again asks the backend again: ${
    calls.filter((c) => c === "get_auto_plan").length > plansBefore}`);

  // Once the user has supplied it, it is a step the install performs.
  fixtures.get_auto_plan = refPlan({ plugin_ready: true, plugin_verified: true });
  const gdRefBundled = await render("GameDetail (REFramework, plugin supplied)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const bundledText = gdRefBundled.host.textContent!;
  console.log(`  a supplied PDPerfPlugin goes in with the install, with libxess.dll: ${
    bundledText.includes("PDPerfPlugin.dll 함께 설치") && bundledText.includes("libxess.dll")}`);
  console.log(`  and is not asked for again: ${
    !bundledText.includes("PDPerfPlugin.dll 직접 받기") && !bundledText.includes("저작권")}`);
  // Another build than 1.1.2 is used, but the wiki says 1.2.0 does not work.
  fixtures.get_auto_plan = refPlan({ plugin_ready: true, plugin_verified: false });
  const gdRefOther = await render("GameDetail (REFramework, other plugin build)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
  console.log(`  a build other than 1.1.2 is called out: ${
    gdRefOther.host.textContent!.includes("다른 버전")}`);

  // A build this plugin has no asset for must say so rather than pretend.
  fixtures.get_auto_plan = refPlan({
    automatic: false, asset: null,
    reason: "이 게임에 맞는 REFramework 빌드가 알려져 있지 않아 직접 다운로드해야 합니다",
  });
  const gdRefManual = await render("GameDetail (REFramework, no known build)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const refManualText = gdRefManual.host.textContent!;
  console.log(`  a game with no known build says so instead of guessing: ${
    refManualText.includes("REFramework 빌드가 알려져 있지 않아") &&
    refManualText.includes("TheRazerMD/REFramework")}`);
  console.log(`  and does not count itself as a step the button performs: ${
    refManualText.includes("3단계 모두 실행")}`);

  // Automatic installation is switched off (constants.REFRAMEWORK_AUTO_INSTALL),
  // which reaches the UI as exactly the same shape: required, not automatic,
  // with a reason. The requirement has to survive that — it is the half that
  // keeps these games from installing successfully and doing nothing.
  fixtures.get_auto_plan = refPlan({
    automatic: false, reason: "이 플러그인은 더 이상 대신 다운로드하지 않습니다",
  });
  const gdRefOff = await render("GameDetail (REFramework, download withdrawn)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const refOffText = gdRefOff.host.textContent!;
  console.log(`  with the download off the game still says it needs REFramework: ${
    refOffText.includes("REFramework 설치") &&
    refOffText.includes("이 게임에 후킹할 수 없습니다")}`);
  console.log(`  says the plugin will not fetch it, and where to get it: ${
    refOffText.includes("더 이상 대신 다운로드하지 않습니다") &&
    refOffText.includes("TheRazerMD/REFramework")}`);
  console.log(`  and keeps the launch-options override REF needs from Proton: ${
    refOffText.includes('WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" %command% -dx12')}`);

  // -- the same game, already set up ---------------------------------------
  fixtures.get_auto_plan = refPlan({});
  fixtures.get_game = {
    ...detail,
    install: { ...detail.install, reframework: { installed: false, revision: null, managed: false } },
    reframework: { ...detail.reframework, required: true, plugin: "PDPerfPlugin.dll",
                   plugin_name: "UpscalerBasePlugin 1.1.2",
                   plugin_url: "https://www.nexusmods.com/site/mods/502",
                   plugin_installed: false, complete: false },
  };
  const gdRefMissing = await render("GameDetail (set up, REFramework missing)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const missingText = gdRefMissing.host.textContent!;
  console.log(`  an install missing it says so rather than looking finished: ${
    missingText.includes("REFramework 없음") &&
    missingText.includes("화면에 아무 변화가 없습니다")}`);
  // The pd games do not upscale at all without PDPerfPlugin, and OptiScaler
  // still loads and its overlay still opens, so "connected" is not evidence of
  // anything. This is how that was reported.
  console.log(`  a missing companion file is said loudly, not as a quiet pill: ${
    missingText.includes("PDPerfPlugin.dll 없음") &&
    missingText.includes("화면에 아무 변화가 없습니다")}`);

  // Supplied after the game was set up: it goes in on its own, from a button.
  fixtures.get_auto_plan = refPlan({ plugin_ready: true, plugin_verified: true });
  fixtures.install_pd_plugin = { ok: true, files: ["PDPerfPlugin.dll", "libxess.dll"] };
  const gdRefLate = await render("GameDetail (set up, PDPerfPlugin supplied later)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
  const lateButton = findAll(gdRefLate.host, '[data-mock="ButtonItem"]').find((n) =>
    n.textContent!.includes("PDPerfPlugin.dll 게임에 넣기")) as HTMLElement | undefined;
  const pdBefore = calls.filter((c) => c === "install_pd_plugin").length;
  await act(async () => { lateButton?.click(); });
  await settle();
  console.log(`  a file supplied after setup goes in from a button: ${
    Boolean(lateButton) && calls.filter((c) => c === "install_pd_plugin").length === pdBefore + 1}`);
  fixtures.get_auto_plan = refPlan({});

  fixtures.get_game = {
    ...detail,
    install: { ...detail.install,
               reframework: { installed: true, revision: "684ca77369ec1050", managed: true } },
    reframework: { ...detail.reframework, required: true, installed: true,
                   revision: "684ca77369ec1050", plugin: null, plugin_installed: false,
                   complete: true },
  };
  const gdRefToggle = await render("GameDetail (REFramework removable)",
    <GameDetail gamePath="/games/MHW" gameName="Monster Hunter Wilds" appid="2246340"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  // REFramework is a third-party DLL that can stop a game booting. When that
  // happens the only way to learn which of the two mods did it is to take one
  // out, so it has to be removable without removing OptiScaler.
  const refToggle = findAll(gdRefToggle.host,
    '[data-mock="ToggleField"][data-label^="REFramework 설치됨"]');
  console.log(`  REFramework can be taken out on its own: ${refToggle.length === 1}`);
  console.log(`  and the row says why you would: ${
    gdRefToggle.host.textContent!.includes("게임이 실행되지 않으면 끄세요")}`);

  fixtures.get_game = {
    ...detail,
    install: { ...detail.install,
               reframework: { installed: true, revision: "684ca77369ec1050", managed: true } },
    reframework: { ...detail.reframework, required: true, installed: true,
                   revision: "684ca77369ec1050", plugin: "PDPerfPlugin.dll",
                   plugin_name: "UpscalerBasePlugin 1.1.2",
                   plugin_url: "https://www.nexusmods.com/site/mods/502",
                   plugin_installed: true, complete: true },
  };
  const gdRefOk = await render("GameDetail (set up, REFramework present)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const okText = gdRefOk.host.textContent!;
  console.log(`  and once it is there, it is ticked with the build it is: ${
    okText.includes("REFramework 설치됨") && okText.includes("684ca77369ec")}`);
  console.log(`  the plugin the user added is ticked too: ${
    okText.includes("PDPerfPlugin.dll 있음")}`);

  // Silently remapping the overlay key is how "pressing Insert does nothing"
  // gets reported as the overlay being broken. It had simply moved.
  fixtures.get_auto_plan = {
    ...refPlan({}),
    plan: {
      ...refPlan({}).plan,
      hotkey: { value: "0x24", name: "Home", source: "wiki entry, “Notes”" },
    },
  };
  fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
  const gdHotkey = await render("GameDetail (entry moves the overlay key)",
    <GameDetail gamePath="/games/RE2" gameName="Resident Evil 2" appid="883710"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  const hotkeyText = gdHotkey.host.textContent!;
  console.log(`  a plan that moves the overlay key says so before writing it: ${
    hotkeyText.includes("오버레이가 다른 키로 열립니다")}`);
  console.log(`  and names the key to press, not the code: ${
    hotkeyText.includes("OptiScaler는 Home") && !hotkeyText.includes("0x24")}`);
  console.log(`  and which key REFramework keeps: ${
    hotkeyText.includes("REFramework는 Insert로 엽니다")}`);

  // An entry that only says to move REF's key (Resident Evil Requiem, Monster
  // Hunter Wilds): the plugin moves OptiScaler's instead, and says it did.
  fixtures.get_auto_plan = {
    ...refPlan({}),
    plan: {
      ...refPlan({}).plan,
      hotkey: { value: "0x24", name: "Home",
                source: "REFramework와 단축키 충돌 방지 (둘 다 Insert 사용)" },
    },
  };
  const gdOurKey = await render("GameDetail (plugin moves the overlay key)",
    <GameDetail gamePath="/games/RE9" gameName="Resident Evil Requiem" appid="3764200"
      status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
  const ourKeyText = gdOurKey.host.textContent!;
  console.log(`  a key the plugin moved is not put down to the entry: ${
    ourKeyText.includes("오버레이가 다른 키로 열립니다") && !ourKeyText.includes("이 항목은 OptiScaler")
    && ourKeyText.includes("OptiScaler는 Home")}`);

  // The other 676 games must not grow a permanently unticked REFramework step.
  fixtures.get_auto_plan = plainPlan;
  fixtures.get_game = detail;
  const gdPlain = await render("GameDetail (no REFramework requirement)",
    <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
      status={fixtures.get_status}
      runningGame={{ appid: 1091500, name: "Cyberpunk 2077", gameid: "1091500" }}
      onBack={() => {}} />);
  console.log(`  a game that does not need it never mentions it: ${
    !gdPlain.host.textContent!.includes("REFramework")}`);

  // A game with no compatibility entry has nothing to be automatic about, so
  // neither the mode strip nor the toggle exists and the panel is unchanged.
  const matchedPlan = fixtures.get_auto_plan;
  fixtures.get_auto_plan = {
    recommendation: { ...matchedPlan.recommendation, matched: false, game: null,
                      detail: {}, near_misses: [{ name: "Cyberpunk 2078", page: null, score: 0.6 }] },
    plan: { ...matchedPlan.plan, available: false, game: null, settings: [],
            framegen: null, unresolved: [], launch_flags: [] },
  };
  const gdNoEntry = await render("GameDetail (no wiki entry)",
    <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
      status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
  const noEntryText = gdNoEntry.host.textContent!;
  console.log(`  no entry means no mode choice: ${
    findAll(gdNoEntry.host, '[data-tab="auto"]').length === 0}`);
  console.log(`  no entry says so on the checklist: ${
    noEntryText.includes("일치하는 위키 항목")}`);
  console.log(`  no entry offers no automatic toggle: ${
    findAll(gdNoEntry.host, '[data-mock="ToggleField"][data-label="Automatic"]').length === 0}`);
  console.log(`  no entry points at setting it up by hand: ${
    noEntryText.includes("수동 설치")}`);
  fixtures.get_auto_plan = matchedPlan;

  // -- the launch options, and taking them back out -------------------------
  // Installing OptiScaler writes a WINEDLLOVERRIDES entry into Steam; removing
  // it used to leave that behind, and when it did clear it, it cleared whatever
  // else the game had too. Both halves are decided from what was recorded at
  // install time, so the rules are worth asserting on their own.
  console.log("\n=== launch options on removal ===");
  {
    const lo = await import("../src/launchOptions");
    const ours = 'WINEDLLOVERRIDES="dxgi=n,b" %command%';

    console.log(`  our own override is recognised: ${
      lo.hasOverride(ours, "dxgi.dll") && !lo.hasOverride(ours, "winmm.dll")}`);
    console.log(`  an .asi install needs no override: ${
      lo.launchOptionFor("OptiScaler.asi") === "%command%"}`);
    // Someone else's flags are not ours to delete.
    console.log(`  stripping ours keeps the user's own flags: ${
      lo.stripOverride('WINEDLLOVERRIDES="dxgi=n,b" mangohud %command% -dx12', "dxgi.dll")
        === "mangohud %command% -dx12"}`);
    console.log(`  a bare %command% left over is an empty field: ${
      lo.stripOverride(ours, "dxgi.dll") === ""}`);
    console.log(`  another mod's override is left alone: ${
      lo.stripOverride('WINEDLLOVERRIDES="dxgi=n,b" %command%', "winmm.dll") !== ""}`);
    console.log(`  stripping ours keeps the other clauses of the same variable: ${
      lo.stripOverride('WINEDLLOVERRIDES="d3d11=n;dxgi=n,b" %command%', "dxgi.dll")
        === 'WINEDLLOVERRIDES="d3d11=n" %command%'}`);
    console.log(`  and our REFramework's override with it, when asked: ${
      lo.stripOverride('WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" %command% -dx12', "dxgi.dll", ["dinput8"])
        === "%command% -dx12"}`);

    // Installing merges into what Steam has, rather than replacing it.
    const merge = lo.mergeLaunchOptions;
    console.log(`  an empty field gets the override and the entry's arguments: ${
      merge("", ["dxgi"], ["-dx12"]) === 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12'}`);
    console.log(`  a wrapper and variables of the user's stay, the override in front: ${
      merge("PROTON_LOG=1 mangohud %command% -novid", ["dxgi"], ["-dx12"])
        === 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_LOG=1 mangohud %command% -novid -dx12'}`);
    console.log(`  arguments without %command% are kept as the game's arguments: ${
      merge("-novid -windowed", ["dxgi"], []) === 'WINEDLLOVERRIDES="dxgi=n,b" %command% -novid -windowed'}`);
    console.log(`  an existing WINEDLLOVERRIDES gets our clause, not a second variable: ${
      merge('WINEDLLOVERRIDES="d3d11=n" %command%', ["dxgi"], [])
        === 'WINEDLLOVERRIDES="d3d11=n;dxgi=n,b" %command%'}`);
    console.log(`  two variables are made one, and another value for our dll replaced: ${
      merge("WINEDLLOVERRIDES=dxgi=b gamemoderun %command% WINEDLLOVERRIDES=\"xinput1_3=n\"", ["dxgi"], [])
        === 'WINEDLLOVERRIDES="xinput1_3=n;dxgi=n,b" gamemoderun %command%'}`);
    console.log(`  a dll in a shared clause is taken out of it, the others kept: ${
      merge('WINEDLLOVERRIDES="dxgi,d3d11=n" %command%', ["dxgi"], [])
        === 'WINEDLLOVERRIDES="d3d11=n;dxgi=n,b" %command%'}`);
    console.log(`  an argument already there is not added twice, in any case: ${
      merge("%command% -DX12", ["dxgi"], ["-dx12"]) === 'WINEDLLOVERRIDES="dxgi=n,b" %command% -DX12'}`);
    console.log(`  another API is replaced by the one the entry asks for: ${
      merge("%command% -dx11 -novid", ["dxgi"], ["-dx12"])
        === 'WINEDLLOVERRIDES="dxgi=n,b" %command% -novid -dx12'}`);
    console.log(`  Unity's -force-d3d12 is not mistaken for -d3d12: ${
      merge("%command% -force-d3d12", ["dxgi"], ["-d3d12"])
        === 'WINEDLLOVERRIDES="dxgi=n,b" %command% -d3d12'
      && merge("%command% -force-d3d12", ["dxgi"], ["-force-d3d12"])
        === 'WINEDLLOVERRIDES="dxgi=n,b" %command% -force-d3d12'}`);
    const twice = merge(merge("mangohud %command%", ["dxgi", "dinput8"], ["-dx12"]), ["dxgi", "dinput8"], ["-dx12"]);
    console.log(`  merging again changes nothing: ${
      twice === 'WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" mangohud %command% -dx12'}`);
    console.log(`  and stripping it gives the user's back: ${
      lo.stripOverride(twice, "dxgi.dll", ["dinput8"]) === "mangohud %command% -dx12"}`);
    console.log(`  an override clause counts as ours wherever it sits: ${
      lo.hasOverride('WINEDLLOVERRIDES="d3d11=n;dxgi=n,b" %command%', "dxgi.dll")
      && !lo.hasOverride('WINEDLLOVERRIDES="dxgi=b" %command%', "dxgi.dll")
      && !lo.hasOverride('WINEDLLOVERRIDES="ddxgi=n,b" %command%', "dxgi.dll")}`);

    // Recorded and not empty: putting it back is the exact answer.
    const withRecord = lo.launchChoices({
      current: 'WINEDLLOVERRIDES="dxgi=n,b" gamemoderun %command%',
      recorded: "gamemoderun %command%",
      filename: "dxgi.dll",
    });
    console.log(`  a recorded value is offered first, verbatim: ${
      withRecord[0].action === "restore" && withRecord[0].value === "gamemoderun %command%"}`);
    // Restoring and stripping would land on the same string here, and a dialog
    // offering the same outcome twice is one nobody can answer.
    console.log(`  an identical second choice is collapsed away: ${
      withRecord.map((c) => c.action).join(",") === "restore,keep"}`);

    // Recorded and empty: the game genuinely had none, so clearing is honest.
    const wasEmpty = lo.launchChoices({ current: ours, recorded: "", filename: "dxgi.dll" });
    console.log(`  "there were none before" offers no restore: ${
      !wasEmpty.some((c) => c.action === "restore") &&
      wasEmpty[0].action === "clear" && wasEmpty[0].value === ""}`);

    // No record at all: only what we recognise as ours comes out.
    const noRecord = lo.launchChoices({
      current: 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12',
      recorded: null,
      filename: "dxgi.dll",
    });
    console.log(`  with nothing recorded only our override is removed: ${
      noRecord[0].action === "clear" && noRecord[0].value === "%command% -dx12"}`);
    console.log(`  leaving them alone is always on offer, and changes nothing: ${
      noRecord[noRecord.length - 1].action === "keep" &&
      noRecord[noRecord.length - 1].value === null}`);
    // Steam will not report launch options on every client build, and leaning
    // on that one getter is what made the first version of this dialog inert:
    // it offered nothing, so removing OptiScaler left its own override behind.
    // Clearing is still offered — last, and never as the default.
    const blind = lo.launchChoices({ current: null, recorded: null, filename: "dxgi.dll" });
    console.log(`  an unreadable field can still be cleared, as a last resort: ${
      blind.map((c) => c.action).join(",") === "keep,clear" && blind[1].value === ""}`);
    console.log(`  and it says it is emptying the field, not pruning it: ${
      blind[1].description.includes("알려 주지 않아")}`);
    console.log(`  but a record still answers it: ${
      lo.launchChoices({ current: null, recorded: "mangohud %command%", filename: "dxgi.dll" })[0]
        .action === "restore"}`);
    // Somebody else's launch options, no override of ours in them.
    console.log(`  a field with none of our override in it is not touched: ${
      lo.launchChoices({ current: "mangohud %command%", recorded: null, filename: "dxgi.dll" })
        .map((c) => c.action).join(",") === "keep"}`);
    console.log(`  a game with no launch options has nothing to ask: ${
      !lo.hasLaunchQuestion("1091500", { current: "", recorded: "", filename: "dxgi.dll" })}`);
    console.log(`  and neither has a game Steam does not own: ${
      !lo.hasLaunchQuestion(null, { current: ours, recorded: "", filename: "dxgi.dll" })}`);
    // A remembered answer that no longer applies must not be forced through.
    console.log(`  a remembered choice that no longer applies falls back: ${
      lo.resolveChoice(wasEmpty, "restore")?.action === "clear" &&
      lo.resolveChoice(noRecord, "keep")?.action === "keep"}`);
    // A game Steam does not own has no choices at all, and asking for one back
    // must not be a crash on the way to the dialog.
    console.log(`  nothing to choose between resolves to nothing: ${
      lo.resolveChoice([], "restore") === undefined}`);

    // -- the dialog itself ---------------------------------------------------
    const { RemovePrompt } = await import("../src/components/RemovePrompt");
    const prompt = await render(
      "RemovePrompt",
      <RemovePrompt
        gameName="Cyberpunk 2077"
        filename="dxgi.dll"
        backedUp={2}
        launch={{
          current: 'WINEDLLOVERRIDES="dxgi=n,b" gamemoderun %command%',
          recorded: "gamemoderun %command%",
          filename: "dxgi.dll",
        }}
        remembered={null}
        canRemember
        onConfirm={() => {}}
      />
    );
    const promptText = prompt.host.textContent!;
    console.log(`  removing still says what happens to the files: ${
      promptText.includes("따로 보관한 파일 2개")}`);
    console.log(`  and now asks about the launch options: ${
      findAll(prompt.host, '[data-mock="DropdownItem"][data-label="Steam 실행 옵션"]')
        .length === 1}`);
    console.log(`  naming what will be put back: ${
      promptText.includes("gamemoderun %command%")}`);
    console.log(`  with a way to stop being asked: ${
      findAll(prompt.host, '[data-mock="ToggleField"][data-label="이 선택 기억"]')
        .length === 1}`);
    // Picking one has to be visible on the control and change what the dialog
    // explains, or the dropdown is decoration.
    await act(async () => {
      (findAll(prompt.host, '[data-mock="DropdownItem"] [data-opt-value="keep"]')[0] as HTMLElement).click();
    });
    await settle();
    const picked = findAll(
      prompt.host, '[data-mock="DropdownItem"][data-label="Steam 실행 옵션"]')[0];
    console.log(`  picking one is reflected back: ${
      picked.getAttribute("data-selected") === "keep" &&
      prompt.host.textContent!.includes("그대로 유지:")}`);

    // A remembered answer is shown rather than applied invisibly, and the
    // question is not asked again.
    const remembered = await render(
      "RemovePrompt (remembered)",
      <RemovePrompt
        gameName="Cyberpunk 2077"
        filename="dxgi.dll"
        backedUp={0}
        launch={{ current: ours, recorded: "", filename: "dxgi.dll" }}
        remembered="clear"
        canRemember
        onConfirm={() => {}}
      />
    );
    console.log(`  a remembered answer replaces the question: ${
      findAll(remembered.host, '[data-mock="DropdownItem"]').length === 0 &&
      remembered.host.textContent!.includes("기억하도록 한 선택")}`);
    console.log(`  and says where to take it back: ${
      remembered.host.textContent!.includes("설정")}`);

    // Nothing to decide: the dialog says so rather than showing an empty control.
    const nothing = await render(
      "RemovePrompt (no launch options)",
      <RemovePrompt gameName="Test" filename="dxgi.dll" backedUp={0} launch={null}
        remembered={null} canRemember onConfirm={() => {}} />
    );
    console.log(`  a game with none says so: ${
      findAll(nothing.host, '[data-mock="DropdownItem"]').length === 0 &&
      nothing.host.textContent!.includes("복원할 실행 옵션이 없습니다")}`);
  }

  // -- a wiki that will not download ----------------------------------------
  // The list failing to download and the game not being on it produced the
  // same empty result, and the checklist printed the same sentence for both —
  // so a network fault presented as every game in the library being unknown to
  // the wiki, with no way to tell and nothing to press.
  console.log("\n=== the compatibility list cannot be reached ===");
  {
    const matched = fixtures.get_auto_plan;
    const offline = {
      ...matched.recommendation,
      matched: false, game: null, detail: {}, near_misses: [],
      list_available: false, entry_count: 0,
      list_meta: { source: "cache", fetched_at: null,
                   error: "URLError: <urlopen error [Errno 101] Network is unreachable>" },
    };
    fixtures.get_auto_plan = {
      recommendation: offline,
      plan: { ...matched.plan, available: false, game: null, settings: [],
              framegen: null, unresolved: [], launch_flags: [] },
    };
    fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
    const down = await render("GameDetail (wiki unreachable)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    const downText = down.host.textContent!;
    console.log(`  a download failure is not called a missing entry: ${
      downText.includes("호환성 목록을 다운로드할 수 없습니다") &&
      !downText.includes("일치하는 위키 항목")}`);
    console.log(`  the actual error is printed, not a generic one: ${
      downText.includes("Network is unreachable")}`);
    console.log(`  and it says the two are not the same thing: ${
      downText.includes("게임이 목록에 없다는 뜻이 아니라")}`);
    console.log(`  there is something to press about it: ${
      downText.includes("다시 시도")}`);
    // The same distinction after the install, where the row used to be a
    // permanent "no wiki entry matched this game".
    fixtures.get_game = detail;
    const downInstalled = await render("GameDetail (installed, wiki unreachable)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    console.log(`  an installed game says it too: ${
      downInstalled.host.textContent!.includes("호환성 목록을 다운로드할 수 없습니다") &&
      !downInstalled.host.textContent!.includes("일치하는 위키 항목")}`);

    // A list that downloaded and simply does not have this game is unchanged:
    // that is the ordinary case and nothing is wrong.
    fixtures.get_auto_plan = {
      recommendation: { ...offline, list_available: true, entry_count: 685,
                        list_meta: { source: "network", fetched_at: 1, error: null } },
      plan: { ...matched.plan, available: false, game: null, settings: [],
              framegen: null, unresolved: [], launch_flags: [] },
    };
    const miss = await render("GameDetail (genuine miss)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    console.log(`  a game genuinely not on the list still says so: ${
      miss.host.textContent!.includes("일치하는 위키 항목") &&
      !miss.host.textContent!.includes("호환성 목록을 다운로드할 수 없습니다")}`);
    fixtures.get_auto_plan = matched;
  }

  // -- a refresh arriving behind the answer ---------------------------------
  // Answers come from the cache, so they arrive even with no route to the
  // wiki. When that cache is old the backend refreshes it behind the answer,
  // and the plan is rebuilt only if the refresh actually brought something —
  // the list carries a content fingerprint, so "something new" is exactly
  // "the fingerprint changed" and an unchanged refresh redraws nothing.
  console.log("\n=== a stale list refreshed behind the answer ===");
  {
    const matched = fixtures.get_auto_plan;
    const stale = (revision: string) => ({
      recommendation: {
        ...matched.recommendation,
        list_meta: { source: "cache", fetched_at: 1, error: null, stale: true, revision },
      },
      plan: { ...matched.plan, game: `Cyberpunk 2077 (${revision})` },
    });

    // The cached answer is served first, from a list flagged stale.
    fixtures.get_auto_plan = stale("old-revision");
    fixtures.wiki_status = {
      ...fixtures.wiki_status, stale: true, revalidating: true, revision: "old-revision",
    };
    fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
    const swr = await render("GameDetail (stale list)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    console.log(`  a stale list still answers, from cache: ${
      swr.host.textContent!.includes("old-revision")}`);

    // Nothing new: the watch ends and the page is left alone.
    fixtures.wiki_status = { ...fixtures.wiki_status, revalidating: false };
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2600));
    });
    await settle();
    console.log(`  a refresh that brought nothing redraws nothing: ${
      swr.host.textContent!.includes("old-revision")}`);

    // Something new: the fingerprint moves and the plan is rebuilt from it.
    fixtures.get_auto_plan = stale("new-revision");
    fixtures.wiki_status = {
      ...fixtures.wiki_status, stale: true, revalidating: true, revision: "new-revision",
    };
    const fresh = await render("GameDetail (refresh lands)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    // First paint is the cached answer; the watch then sees a new fingerprint.
    fixtures.get_auto_plan = stale("newer-still");
    fixtures.wiki_status = { ...fixtures.wiki_status, revision: "newer-still" };
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2600));
    });
    await settle();
    console.log(`  a refresh that brought something rebuilds the plan: ${
      fresh.host.textContent!.includes("newer-still")}`);

    fixtures.get_auto_plan = matched;
    fixtures.get_game = detail;
    fixtures.wiki_status = {
      ...fixtures.wiki_status, stale: false, revalidating: false, revision: "aaaaaaaaaaaa",
    };
  }

  // -- a game whose wiki page has never been downloaded ---------------------
  // The Forza Horizon 5 case: the compatibility list was cached but this
  // game's own page was not, and the page was fetched in front of the answer —
  // two URLs deep, the second attempt only starting once the first had timed
  // out. On a Deck with a bad route to the wiki that never returned, so the
  // tab sat on "Checking the OptiScaler wiki…" for ever, while a game whose
  // page happened to be cached answered fine.
  console.log("\n=== a wiki page that has not arrived yet ===");
  {
    const matched = fixtures.get_auto_plan;
    fixtures.get_auto_plan = {
      recommendation: {
        ...matched.recommendation,
        detail_pending: true,
        list_meta: { source: "cache", fetched_at: 1, error: null, stale: false,
                     revision: "list.1" },
      },
      plan: matched.plan,
    };
    fixtures.wiki_status = {
      ...fixtures.wiki_status, revision: "list.1", revalidating: true,
    };
    fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
    const pending = await render("GameDetail (page pending)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    const pendingText = pending.host.textContent!;
    console.log(`  it answers from the list row instead of waiting: ${
      pendingText.includes("자동 설치할 수 있습니다") &&
      !pendingText.includes("OptiScaler 위키 확인 중")}`);
    console.log(`  and says the fuller answer is still coming: ${
      pendingText.includes("아직 읽는 중입니다")}`);
    // The page is what names the filename to install as, so acting in that
    // window would install under the default name when the entry says
    // otherwise. The wait is on the button alone, and only while the watch is
    // still running — never once it has given up.
    console.log(`  the install button waits for it, and says why: ${
      pendingText.includes("이 게임 항목 읽는 중…")}`);

    // When the page lands the revision moves, and the answer is rebuilt.
    fixtures.get_auto_plan = {
      recommendation: {
        ...matched.recommendation,
        detail_pending: false,
        list_meta: { source: "cache", fetched_at: 1, error: null, stale: false,
                     revision: "list.2" },
      },
      plan: { ...matched.plan, filename: "winmm.dll" },
    };
    fixtures.wiki_status = { ...fixtures.wiki_status, revision: "list.2" };
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2600));
    });
    await settle();
    console.log(`  the page arriving replaces it with the fuller one: ${
      pending.host.textContent!.includes("winmm.dll") &&
      !pending.host.textContent!.includes("Still reading this game's own entry")}`);
    console.log(`  and releases the button: ${
      !pending.host.textContent!.includes("이 게임 항목 읽는 중…") &&
      pending.host.textContent!.includes("3단계 모두 실행")}`);

    fixtures.get_auto_plan = matched;
    fixtures.get_game = detail;
    fixtures.wiki_status = {
      ...fixtures.wiki_status, revision: "aaaaaaaaaaaa", revalidating: false,
    };
  }

  // -- a page the wiki will not serve ---------------------------------------
  // Pending and *still arriving* are different things. A page the wiki refuses
  // stays pending for ever, and the checklist kept saying "still reading" and
  // holding its button on the strength of it — permanently.
  console.log("\n=== a wiki page that never arrives ===");
  {
    const matched = fixtures.get_auto_plan;
    fixtures.get_auto_plan = {
      recommendation: {
        ...matched.recommendation, detail_pending: true,
        list_meta: { source: "cache", fetched_at: 1, error: null, stale: false,
                     revision: "list.1" },
      },
      plan: matched.plan,
    };
    // The backend has already given up: nothing is being refreshed.
    fixtures.wiki_status = {
      ...fixtures.wiki_status, revision: "list.1", revalidating: false,
    };
    fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
    const never = await render("GameDetail (page never arrives)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 2600));
    });
    await settle();
    const neverText = never.host.textContent!;
    console.log(`  it stops claiming to still be reading: ${
      !neverText.includes("Still reading this game's own entry")}`);
    console.log(`  and lets the install go ahead with what it has: ${
      !neverText.includes("이 게임 항목 읽는 중…") && neverText.includes("3단계 모두 실행")}`);
    fixtures.get_auto_plan = matched;
    fixtures.get_game = detail;
    fixtures.wiki_status = { ...fixtures.wiki_status, revision: "aaaaaaaaaaaa" };
  }

  // -- an answer whose revision can never match -----------------------------
  // The watch reloads when the backend's revision differs from the one the
  // answer was built with, which assumes the two are comparable. Once they
  // were not — a pinned wiki entry came back with no revision at all — so
  // every check read as "something changed" and the plan reloaded every two
  // seconds for ever, flickering. Refusing to reload twice for one revision
  // makes that impossible rather than merely fixed.
  console.log("\n=== an answer that can never match the watch ===");
  {
    const matched = fixtures.get_auto_plan;
    let asked = 0;
    fixtures.get_auto_plan = () => {
      asked += 1;
      return {
        recommendation: {
          ...matched.recommendation, detail_pending: true,
          // No revision at all, the way a pinned entry used to answer.
          list_meta: { source: "manual", fetched_at: null, error: null, stale: true },
        },
        plan: matched.plan,
      };
    };
    fixtures.wiki_status = {
      ...fixtures.wiki_status, revision: "never-matches", revalidating: true, stale: true,
    };
    fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
    const loop = await render("GameDetail (unmatchable revision)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    const afterFirst = asked;
    await act(async () => {
      await new Promise((r) => setTimeout(r, 9000));
    });
    await settle();
    console.log(`  it reloads once, not once every two seconds: ${
      asked - afterFirst <= 1} (${asked - afterFirst} reloads in 9s)`);
    console.log(`  and the panel is still showing the plan, not a spinner: ${
      !loop.host.textContent!.includes("OptiScaler 위키 확인 중")}`);
    fixtures.get_auto_plan = matched;
    fixtures.get_game = detail;
    fixtures.wiki_status = {
      ...fixtures.wiki_status, revision: "aaaaaaaaaaaa", revalidating: false, stale: false,
    };
  }

  // A backend that never answers must not leave the tab waiting for ever.
  console.log("\n=== an answer that never comes ===");
  {
    const matched = fixtures.get_auto_plan;
    fixtures.get_auto_plan = () => new Promise(() => {});
    fixtures.get_game = { ...detail, install: { ...detail.install, installed: false } };
    const stuck = await render("GameDetail (backend hangs)",
      <GameDetail gamePath="/games/Cyberpunk 2077" gameName="Cyberpunk 2077" appid="1091500"
        status={fixtures.get_status} runningGame={null} onBack={() => {}} />);
    console.log(`  it says it is checking, at first: ${
      stuck.host.textContent!.includes("OptiScaler 위키 확인 중")}`);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 8600));
    });
    await settle();
    console.log(`  but gives up showing the wait rather than hanging on it: ${
      !stuck.host.textContent!.includes("OptiScaler 위키 확인 중") &&
      stuck.host.textContent!.includes("수동 설치")}`);
    fixtures.get_auto_plan = matched;
    fixtures.get_game = detail;
  }

  // -- the plugin's own settings --------------------------------------------
  console.log("\n=== global settings tab ===");
  {
    // An earlier deep-link test left a request pending; this page is the
    // library list, not a game.
    const { takePendingTarget } = await import("../src/navigation");
    takePendingTarget();
    const settings = await render("ManagerPage (settings)", <ManagerPage />);
    const tabIds = findAll(settings.host, "[data-tab]").map((n) => n.getAttribute("data-tab"));
    console.log(`  the main page has a settings tab: ${tabIds.includes("settings")}`);
    const settingsBody = findAll(settings.host, '[data-tab="settings"]')[0];
    const settingsText = settingsBody.textContent!;
    console.log(`  it carries the switch that stops answers being kept: ${
      findAll(settingsBody, '[data-mock="ToggleField"][data-label="선택 기억"]')
        .length === 1}`);
    console.log(`  it lists what is remembered, in words: ${
      settingsText.includes("OptiScaler 제거 시") &&
      settingsText.includes("설치 전의 값으로 복원합니다")}`);
    console.log(`  each one can be put back to a question: ${
      findAll(settingsBody, '[data-forget="remove_launch_options"]').length === 1}`);
    console.log(`  unanswered questions are not listed: ${
      findAll(settingsBody, '[data-forget="launch_options"]').length === 0}`);
    // Nothing is bundled: the nightly the installs use is stated, with when.
    console.log(`  the downloaded nightly is stated: ${
      settingsText.includes("OptiScaler 10.0.0-pre1") && settingsText.includes("nightly-20261027")}`);
    console.log(`  games keep their build until reinstalled, and it says so: ${
      settingsText.includes("다시 설치할 때까지 기존 빌드를 유지합니다")}`);
    console.log(`  no AMD driver library is listed any more: ${
      !settingsText.includes("amdvkffx64.dll")}`);
    // Which build of each download channel installs use.
    const nightlyPick = findAll(settingsBody, '[data-channel="nightly"]')[0];
    const nightlyOptions = findAll(nightlyPick ?? settingsBody, "[data-opt]").map((n) => n.textContent!);
    console.log(`  each download channel can be pinned, from the build the plugin was made against: ${
      Boolean(nightlyPick) && nightlyOptions[0] === "설치한 버전 (새 빌드 알림)"
      && nightlyOptions.some((o) => o.startsWith("nightly-20261027") && o.includes("플러그인 빌드 기준"))
      && nightlyOptions.length === 3}`);
    console.log(`  the build set up is the default, and a pin is shown as picked: ${
      nightlyPick?.getAttribute("data-selected") === ""
      && findAll(settingsBody, '[data-channel="dropin"]')[0]?.getAttribute("data-selected") === "dll-2026-10-29"}`);
    const pinsBefore = calls.filter((c) => c === "set_channel_version").length;
    const pinned: unknown[][] = [];
    const setChannel = fixtures.set_channel_version;
    fixtures.set_channel_version = (...args: unknown[]) => {
      pinned.push(args);
      return { ok: true };
    };
    await act(async () => {
      (findAll(nightlyPick, '[data-opt-value="nightly-20261028"]')[0] as HTMLElement | undefined)?.click();
    });
    await settle();
    console.log(`  picking one pins it: ${
      calls.filter((c) => c === "set_channel_version").length === pinsBefore + 1
      && pinned[0]?.[0] === "nightly" && pinned[0]?.[1] === "nightly-20261028"}`);
    fixtures.set_channel_version = setChannel;
    console.log(`  Settings lists what was downloaded, with checking and removing it all: ${
      settingsText.includes("받은 파일") && settingsText.includes("새 빌드 확인")
      && settingsText.includes("받은 파일 모두 지우기")
      && findAll(settingsBody, '[data-component="helixsr"]')[0]?.textContent!.includes("HLX DLSS 빌드 안 됨")}`);
    // The plugin's own updates: Decky only offers them for store plugins.
    console.log(`  it says a newer plugin release is out: ${settingsText.includes("0.1.2 버전이 나왔습니다")}`);
    const handed: unknown[][] = [];
    globalThis.DeckyBackend = {
      callable: ((route: string) => async (...args: unknown[]) => {
        handed.push([route, ...args]);
      }) as any,
    };
    const updateButton = findAll(settingsBody, '[data-mock="ButtonItem"]').find((n) =>
      n.textContent!.includes("0.1.2 버전으로 업데이트")) as HTMLElement | undefined;
    await act(async () => { updateButton?.click(); });
    await settle();
    const [route, url, name, version, sha, kind] = handed[0] ?? [];
    console.log(`  Update hands the release to Decky's own installer: ${
      route === "utilities/install_plugin" && String(url).endsWith("Decky-Upscaler-Manager-v0.1.2.zip")
      && name === "Decky Upscaler Manager" && version === "0.1.2" && sha === "ab".repeat(32)
      && kind === 2}`);
    globalThis.DeckyBackend = undefined;
    // Games set up from an older nightly can be brought up to date at once.
    const gamesNow = findAll(settings.host, '[data-tab="settings"]')[0];
    console.log(`  it counts the games on an older build: ${
      gamesNow.textContent!.includes("이전 빌드를 쓰는 게임 1개") && gamesNow.textContent!.includes("Cyberpunk 2077")}`);
    const updateGames = findAll(gamesNow, '[data-mock="ButtonItem"]').find((n) =>
      n.textContent!.includes("게임 1개 업데이트")) as HTMLElement | undefined;
    const before = calls.filter((c) => c === "update_installed_games").length;
    await act(async () => { updateGames?.click(); });
    await settle();
    console.log(`  and updates them in one go: ${
      calls.filter((c) => c === "update_installed_games").length === before + 1}`);
    console.log(`  Settings says whether HelixSR is set up, and how: ${
      gamesNow.textContent!.includes("HelixSR (HLX DLSS)")
      && gamesNow.textContent!.includes("HLX DLSS를 빌드해야 합니다")}`);
    console.log(`  Settings says where to get PDPerfPlugin.dll and that it is not here yet: ${
      gamesNow.textContent!.includes("PDPerfPlugin (pd-upscaler 게임용)")
      && gamesNow.textContent!.includes("PDPerfPlugin.dll 없음")
      && gamesNow.textContent!.includes("nexusmods.com/site/mods/502")}`);
    // Without Desktop Mode: a phone gets it from Nexus, then sends it over Wi-Fi.
    const pdButton = (label: string) =>
      findAll(gamesNow, '[data-mock="ButtonItem"]').find((n) =>
        n.textContent!.includes(label)) as HTMLElement | undefined;
    console.log(`  it offers the phone, a picked file and the Downloads folder: ${
      Boolean(pdButton("휴대폰으로 받아서 보내기")) && Boolean(pdButton("파일 선택 (SD 카드·USB)"))
      && Boolean(pdButton("다시 확인"))}`);
    await act(async () => { pdButton("휴대폰으로 받아서 보내기")?.click(); });
    await settle();
    const qrs = () => findAll(gamesNow, "[data-qr]").map((n) => n.getAttribute("data-qr"));
    console.log(`  step 1 is a QR code for the Nexus Mods files tab, and nothing is opened yet: ${
      qrs().includes("https://www.nexusmods.com/site/mods/502?tab=files")
      && !calls.includes("start_pd_upload")}`);
    fixtures.start_pd_upload = { ok: true, active: true, url: "http://192.168.0.23:38517/tok",
                                 expires_at: 1787000600, result: null };
    fixtures.get_pd_upload_status = { ok: true, active: true, url: "http://192.168.0.23:38517/tok",
                                      expires_at: 1787000600, result: null };
    fixtures.stop_pd_upload = { ok: true };
    await act(async () => { pdButton("다음: 스팀덱으로 보내기")?.click(); });
    await settle();
    console.log(`  step 2 opens the upload page and shows its address as a QR code: ${
      calls.includes("start_pd_upload") && qrs().includes("http://192.168.0.23:38517/tok")
      && gamesNow.textContent!.includes("같은 Wi-Fi")}`);
    const stopsBefore = calls.filter((c) => c === "stop_pd_upload").length;
    await act(async () => { pdButton("닫기")?.click(); });
    await settle();
    console.log(`  and leaving it closes the page: ${
      calls.filter((c) => c === "stop_pd_upload").length === stopsBefore + 1 && qrs().length === 0}`);
    console.log(`  it names the OptiPatcher build installs use: ${
      gamesNow.textContent!.includes("rolling (2026-10-27)")}`);
    // Where the wiki's actual state is readable without opening a log.
    console.log(`  it reports the compatibility list: ${
      settingsText.includes("목록의 게임 685개")}`);
    console.log(`  and offers to download it again: ${
      settingsText.includes("다시 다운로드")}`);
    // Available and current are different questions once answers come from
    // cache: a list can be perfectly usable and months old, and a refresh can
    // be failing behind it without anything breaking.
    console.log(`  it says how old the list is: ${settingsText.includes("시간 전")}`);
  }

  // Before the first install there is nothing downloaded, and opening the page
  // must not fetch 57 MB: it says the first install will.
  {
    const { takePendingTarget } = await import("../src/navigation");
    takePendingTarget();
    const notSetUp = {
      ...setUp, setup_done: false,
      channels: {
        nightly: { ...setUp.channels.nightly, installed: null },
        dropin: { ...setUp.channels.dropin, installed: null },
        helixsr: { ...setUp.channels.helixsr, installed: null, source: null },
      },
    };
    fixtures.get_components = notSetUp;
    const before = calls.filter((c) => c === "start_setup").length;
    const fresh = await render("ManagerPage (not set up)", <ManagerPage />);
    const freshText = fresh.host.textContent!;
    console.log(`  before the set-up, the page offers only the set-up: ${
      freshText.includes("먼저 필요한 파일을 설치하세요") && findAll(fresh.host, "[data-tab]").length === 0
      && findAll(fresh.host, '[data-mock="ButtonItem"]').some((n) => n.textContent === "설치")}`);
    console.log(`  and opening the page downloads nothing: ${
      calls.filter((c) => c === "start_setup").length === before}`);
    const dlssToggle = findAll(fresh.host, '[data-mock="ToggleField"]').find((n) =>
      n.getAttribute("data-label") === "HLX DLSS 사용");
    console.log(`  HLX DLSS is offered as a choice, off unless turned on, buildable later: ${
      dlssToggle?.querySelector("[data-toggle]")?.getAttribute("data-checked") === "false"
      && dlssToggle.textContent!.includes("설정에서 언제든 빌드할 수 있습니다")}`);
    await act(async () => { (dlssToggle?.querySelector("[data-toggle]") as HTMLElement | null)?.click(); });
    await settle();
    console.log(`  and turns on with a press: ${
      dlssToggle?.querySelector("[data-toggle]")?.getAttribute("data-checked") === "true"}`);
    const freshPanel = await render("QuickPanel (not set up)",
      <QuickPanel runningGame={null} onOpenManager={() => {}} />);
    console.log(`  so does the side panel: ${
      freshPanel.host.textContent!.includes("먼저 필요한 파일을 설치하세요")
      && findAll(freshPanel.host, "[data-tab]").length === 0}`);
    fixtures.get_components = {
      ...notSetUp,
      job: { ...idleJob, running: true, kind: "setup", steps: [
        { key: "nightly", label: "OptiScaler nightly", state: "done", detail: "nightly-20261027" },
        { key: "dropin", label: "cyboman FSR 4.1.2 Lite", state: "done", detail: "dll-2026-10-29" },
        { key: "helixsr", label: "HelixSR (HLX FSR 4)", state: "done", detail: "v3.2.0" },
        { key: "hlx_dlss", label: "HLX DLSS 빌드", state: "running", detail: null },
      ] },
      build: { ...idleBuild, running: true, percent: 30, step: "shaders" },
    };
    // As the set-up button does with the answer to starting it.
    await act(async () => { publishComponents(fixtures.get_components); });
    await settle();
    const goingText = fresh.host.textContent!;
    console.log(`  the set-up shows each step, the HLX DLSS build with how far it is: ${
      goingText.includes("완료") && goingText.includes("shaders · 30%") && goingText.includes("설치 중…")
      && findAll(fresh.host, '[data-step="hlx_dlss"][data-state="running"]').length === 1}`);
    fixtures.get_components = setUp;
    await act(async () => { await new Promise((r) => setTimeout(r, 1200)); });
    await settle();
    console.log(`  once set up, the page is the plugin again: ${
      findAll(fresh.host, "[data-tab]").length > 0 && !fresh.host.textContent!.includes("먼저 필요한 파일을")}`);

    // Newer builds, and a HelixSR Desktop set-up gone, are said on the main page.
    fixtures.get_components = {
      ...setUp,
      channels: {
        ...setUp.channels,
        nightly: { ...setUp.channels.nightly, latest: "nightly-20261101", update: true },
        helixsr: { ...setUp.channels.helixsr, installed: null, source: null, desktop_missing: true },
      },
      updates: ["nightly"],
    };
    const notice = await render("ComponentNotice", <ComponentNotice />);
    console.log(`  a newer build is said on the main page, to update in Settings: ${
      notice.host.textContent!.includes("새 빌드가 있습니다")
      && notice.host.textContent!.includes("OptiScaler nightly nightly-20261101")
      && notice.host.textContent!.includes("설정 탭에서 업데이트하세요")}`);
    console.log(`  and HelixSR Desktop's HelixSR gone is said, with what to do: ${
      notice.host.textContent!.includes("HelixSR Desktop의 HelixSR가 없어졌습니다")}`);
    const section = await render("ComponentsSection (updates)", <ComponentsSection />);
    const updateArgs: unknown[][] = [];
    fixtures.update_component = (...args: unknown[]) => {
      updateArgs.push(args);
      return { ok: true, components: fixtures.get_components };
    };
    const nightlyUpdate = findAll(section.host, '[data-mock="ButtonItem"]').find((n) =>
      n.textContent!.includes("OptiScaler nightly 업데이트 (nightly-20261101)")) as HTMLElement | undefined;
    await act(async () => { nightlyUpdate?.click(); });
    await settle();
    console.log(`  Settings updates it on a press: ${updateArgs[0]?.[0] === "nightly"}`);
    console.log(`  and offers to set HelixSR up with the plugin instead: ${
      findAll(section.host, '[data-mock="ButtonItem"]').some((n) => n.textContent === "플러그인으로 HelixSR 설치")}`);
    fixtures.get_components = {
      ...setUp,
      channels: {
        ...setUp.channels,
        helixsr: { ...setUp.channels.helixsr, installed: null, source: "desktop", desktop_version: "3.2.0",
                   dlss_ready: true, latest: "v3.2.1", update: true },
      },
      updates: ["helixsr"],
    };
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    const desktopNotice = await render("ComponentNotice (HelixSR Desktop)", <ComponentNotice />);
    const desktopSection = await render("ComponentsSection (HelixSR Desktop)", <ComponentsSection />);
    console.log(`  HelixSR Desktop's HelixSR is updated by that app, and only said here: ${
      desktopNotice.host.textContent!.includes("HelixSR v3.2.1 (HelixSR Desktop에서 업데이트)")
      && !desktopNotice.host.textContent!.includes("설정 탭에서 업데이트하세요")
      && desktopSection.host.textContent!.includes("HelixSR Desktop으로 업데이트하세요")
      && !findAll(desktopSection.host, '[data-mock="ButtonItem"]').some((n) => n.textContent!.includes("HelixSR 업데이트"))}`);
    fixtures.get_components = setUp;
    publishComponents(setUp as any);
    await settle();
  }

  {
    const { takePendingTarget } = await import("../src/navigation");
    takePendingTarget();
    fixtures.wiki_status = {
      ...fixtures.wiki_status, source: "bundled", age: 60 * 60 * 24 * 30,
      error: "URLError: <urlopen error [Errno 101] Network is unreachable>",
    };
    const offlineSettings = await render("ManagerPage (offline wiki)", <ManagerPage />);
    const offlineText = findAll(offlineSettings.host, '[data-tab="settings"]')[0].textContent!;
    console.log(`  a Deck that never downloaded one uses the bundled copy: ${
      offlineText.includes("플러그인에 포함된 사본")}`);
    console.log(`  and says the refresh behind it failed, without calling it broken: ${
      offlineText.includes("마지막 새로 고침이 실패해") &&
      offlineText.includes("Network is unreachable") &&
      offlineText.includes("목록의 게임 685개")}`);
    fixtures.wiki_status = {
      ...fixtures.wiki_status, source: "cache", age: 3600, error: null,
    };
    // It is plugin-wide, so it must not turn up in the sidebar.
    console.log(`  the quick panel does not carry it: ${
      !findAll(qp.host, "[data-tab]").some((n) => n.getAttribute("data-tab") === "settings")}`);
  }

  console.log("\n=== backend calls made ===");
  console.log("  " + Array.from(new Set(calls)).join(", "));

  const real = errors.filter((e) => !e.includes("not wrapped in act"));
  console.log(`\n=== React errors/warnings: ${real.length} ===`);
  real.slice(0, 12).forEach((e) => console.log("  ! " + e.slice(0, 300)));
  process.exit(real.length > 0 ? 1 : 0);
})();
