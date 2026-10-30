# Changelog

Newest first. Each release ships `Decky-Upscaler-Manager-vX.Y.Z.zip` for Decky
Loader's *Install from URL* (Developer mode). Releases up to 0.0.7 are the
Decky OptiScaler plugin this one grew out of, which bundled **OptiScaler
0.9.4**; from 0.1.0 OptiScaler is downloaded from its nightly channel.

## [Unreleased]

### Changed

- **Renamed to Decky Upscaler Manager** (was Decky OptiScaler Plus), as it now
  puts in more than OptiScaler: cyboman's FSR 4 builds and HelixSR's HLX FSR 4
  and HLX DLSS too. The repositories are renamed with it (GitHub forwards the
  old addresses), the release asset is `Decky-Upscaler-Manager-vX.Y.Z.zip`,
  and the library context menu entry reads **Upscaler Manager**. Decky treats
  the new name as a new plugin: install it from the release, set it up, and
  uninstall Decky OptiScaler Plus. Games set up with the old one are
  recognised as they are.
- **The source is public**, in the same repository as the releases
  (supercleans/decky-upscaler-manager), starting from a fresh history. The
  release workflow publishes there with the workflow's own token; the
  separate source repository and its RELEASE_TOKEN are gone.

## [0.1.12] - 2026-10-30

### Added

- **Set the plugin up once.** Until it is, the plugin shows only **설치**,
  which downloads everything installs use, in the background with each step
  shown: the OptiScaler nightly, cyboman's FSR 4.1.2 Lite builds (not on a
  BC-250, which cannot pick them) and a HelixSR release with HLX DLSS built
  in it, after the user agrees to NVIDIA's licence. A HelixSR that HelixSR
  Desktop set up is used instead, and nothing of HelixSR is downloaded. HLX
  DLSS failing to build is said and can be built again from Settings; a
  download failing leaves the plugin not set up, with the reason and a retry.
- **Updates are said, and made from Settings.** The channels are asked every
  few hours; a newer build is said at the top of the main page, and
  **설정 → 받은 파일** updates each one (HelixSR is built again in the new
  release) or checks at once. HelixSR Desktop's HelixSR is only said to have
  an update, for that app to make. A HelixSR Desktop set-up that has gone is
  said, and the plugin can set HelixSR up itself instead.
- **받은 파일 모두 지우기** removes everything the plugin downloaded, and
  HelixSR's setup tools unless HelixSR Desktop shares them; games keep what
  was installed in them, and the plugin goes back to its set-up.

### Changed

- Installs use what was set up and never download a newer build behind the
  user: the nightly is no longer checked every six hours, and cyboman's
  builds and HelixSR are no longer looked up on every install. A pin in
  **다운로드 버전** still takes that build; unpinned, a channel stays on the
  build set up and says when a newer one is out. **새 nightly 확인** is
  replaced by **받은 파일**.

## [0.1.11] - 2026-10-30

### Added

- **Pick which build is downloaded.** Settings → **다운로드 버전** offers, for
  the OptiScaler nightly and for cyboman's FSR 4.1.2 Lite builds, **최신
  (자동)** (as before) or one build to stay on. The list starts at the build
  that was newest when this plugin release was made, marked **플러그인 빌드
  기준**, and runs to the newest now; builds already on the Deck are marked
  too, and offline the list is just those. A pinned nightly is what installs
  and **게임 업데이트** move games to, and what "older build" is judged
  against; letting go of a pin checks for the newest on the next install. The
  release workflow records the starting builds in
  `defaults/channel-baseline.json` (`scripts/pin_channels.py`).
- **HLX FSR 4 is downloaded, and goes into OptiScaler itself.** HelixSR 3.2.0
  ships HLX FSR 4 built (from AMD's MIT FSR SDK 2.4.0) in its release ZIP, so,
  like cyboman's builds, the plugin downloads it from HelixSR's official
  releases: the ZIP, checked against the digest the release names, unpacked
  whole (about 370 MB, kept for HLX DLSS to be built in, below), its
  `HLX-FSR4/amd_fidelityfx_upscaler_dx12.dll` refused without the trailer a
  built one ends in. A game with FSR 3.1 takes HLX FSR 4 as a drop-in, as
  before; any other now gets it through the OptiScaler nightly, instead of
  through HelixSR Scaler. Only the releases in use stay unpacked.
- **HLX DLSS without HelixSR Desktop.** A build HelixSR Desktop made is still
  used first; without one, **HLX DLSS 빌드** (in the upscaler list and in
  Settings → HelixSR) runs HelixSR's own `helixsr-setup.sh`, unmodified, in
  the release the plugin downloaded. Once the user agrees to NVIDIA's licence,
  the plugin downloads the NVIDIA DLSS DLL the setup names, checks it against
  the SHA-256 the setup names, and hands it over with `--dlss`, deleting it
  afterwards; frame generation is left out (`--no-fg`), and the setup's input
  is closed without `--yes`, so its closing games step changes nothing. The
  setup downloads a portable Python and Microsoft's shader compiler once,
  into `~/.local/share/HelixSR` as HelixSR Desktop does, and needs Proton.
  The build runs in the background with its progress shown, can be cancelled,
  and goes on with the panel closed.
- **Every FSR 4 build, in every OptiScaler install.** An install from the
  nightly carries cyboman's FSR 4.1.2 Lite exact and lossy, HLX FSR 4 and
  AMD's FSR 4, whichever was picked: the picked one as OptiScaler's own
  FidelityFX upscaler (below), the others in `OptiScaler/custom/`, so the
  overlay can switch between them in game. One that cannot be downloaded is
  left out and reported, unless it is the picked one, which fails the install
  as before.
- **Settings → 다운로드 버전** also pins the HelixSR release HLX FSR 4 comes
  from, starting at 3.2.0.
- **FSR 4 Lite as a drop-in (a test).** In a game that ships FSR 3.1, FSR 4
  Lite now goes in like cyboman's builds: the nightly's own
  `amd_fidelityfx_upscaler_dx12.dll` (FidelityFX SDK 2.4, FSR 4.1.2) in place
  of the game's, with the nightly's loader and frame generator in games with
  the all-in-one DLL. Any other game gets it through OptiScaler, as before.
  With no OptiScaler in front of it, AMD's file does its own GPU check, which
  may turn the Steam Deck down; the drop-in says so and is to be removed if
  the game's FSR does not become FSR 4.

### Changed

- **cyboman's FSR 4.1.2 Lite builds replace lossy2.** fsr4-shader-performance-
  overrides moved to FSR 4.1.2 (`dll-2026-10-29`): the archive is now named
  `fsr4.1.2-igpu-cyboman-rdna2-…`, which the plugin did not recognise, so it
  kept installing the 4.1.1 lossy2 of `dll-2026-10-22`. It now picks the newest
  archive whatever its 4.1.x number, and offers the two builds on AMD's
  smaller Lite network as upscalers of their own:
  - **FSR 4.1.2 Lite exact** (`4.1.2l-exact`): AMD's FSR 4.1.2 Lite picture,
    byte for byte, a little faster than AMD's Lite.
  - **FSR 4.1.2 Lite lossy** (`4.1.2l-lossy`): retrained, about 18% faster
    than AMD's Lite, a slightly different picture.
- **And they reach games without FSR 3.1.** A game that ships FSR 3.1 takes
  either as a drop-in, as before. Any other game now gets OptiScaler's nightly
  with the build as a **custom upscaler** (the nightly's new
  `OptiScaler/custom/<name>/ffx/` folder): an entry of its own in the overlay's
  DX12 list, beside AMD's FSR 4.1.2, made the one used by
  `Dx12Upscaler=cyboman-4.1.2l-exact` (or `-lossy`). DX11 takes no custom
  upscaler and a Vulkan one wants a Vulkan DLL, which cyboman does not build,
  so those games run AMD's FSR 4. Switching build or going back to FSR 4 Lite
  takes the old folder out, and a verify checks the file against what was put
  there.
- **The ini schema follows the nightly of 2026-10-29.** `Dx12Upscaler` and
  `VulkanUpscaler` accept a custom upscaler's folder name besides their backend
  ids, and the new `FfxVkSRPath`/`FfxVkFGPath` keys are known.
- **FSR 4 lossy2 is gone.** The new release no longer carries it.
- **ASI loading is always on.** Every upscaler's preset writes
  `[Plugins] LoadAsiPlugins=true`, instead of only when OptiPatcher went in:
  OptiScaler reads `OptiScaler/plugins/*.asi` only with it, and with nothing
  there it has nothing to load. Turning OptiPatcher on or off no longer
  touches the ini.
- **HLX presets no longer write `[DLSS] HelixSR=true`**, which is HelixSR
  Scaler's default. HLX DLSS still writes `Dx12Upscaler=dlss`, as HelixSR's own
  installer does, so a game switched from FSR 4 Lite does not keep `ffx`.

- **A picked build runs in DX11 and Vulkan games too.** Through OptiScaler,
  cyboman's builds and HLX FSR 4 used to go in as custom upscalers, which only
  the DX12 list can name; DX11 and Vulkan games, which reach FFX through the
  DX12 interop backends (`ffx_12`), ran AMD's FSR 4 instead. The picked build
  now takes AMD's place as OptiScaler's own FidelityFX upscaler
  (`OptiScaler/amd_fidelityfx_upscaler_dx12.dll`, the layout HelixSR Scaler
  uses), `Dx12Upscaler=ffx` for every one, and AMD's own moves into the custom
  folder as `amd-fsr4` to stay in the overlay's list beside the other builds.
  A verify checks the replaced file against what was put there.
- **The BC-250 offers HLX FSR 4 and HLX DLSS only.** OptiScaler does not give
  its GPU FSR 4, so AMD's FSR 4 and cyboman's builds of it run as FSR 3 there;
  the list leaves them out, the backend refuses them, and an install does not
  download cyboman's builds.
- **The upscaler a game starts with depends on the machine.** The GPU's PCI
  id tells a Steam Deck (LCD `1002:163f`, OLED `1002:1435`) from a BC-250
  (`1002:13fe`, gfx1013). A BC-250 starts with **HLX FSR 4**, marked 추천:
  its int8 is slow, where HLX FSR 4 picks an fp16 version. Anything else
  starts with FSR 4 Lite, as before, and a game already set up keeps its
  upscaler.
- **A Steam Deck OLED no longer reads as Rembrandt.** Its PCI id `0x1435` was
  in the table under the wrong name.
- **Launch options are added to, not replaced.** Setting them up used to
  write the whole field, so a `mangohud`, a `gamescope` wrapper or a `PROTON_`
  variable of the user's went (kept only in the record for putting back on
  removal). Now the overrides go in front of whatever Steam has: into its
  `WINEDLLOVERRIDES` when there is one (one assignment, ours replacing a
  clause for the same DLL such as `dxgi=b`), and the entry's arguments after
  `%command%` unless they are already there, one picking the graphics API
  replacing another (`-dx11` for an entry's `-dx12`). Doing it twice changes
  nothing, and taking ours out on removal or from the toggle leaves the rest,
  other DLLs in the same variable included.
- **The manual install's launch options carry the entry's arguments** too
  (`-dx12`...), as the checklist's always did.
- **Unity's `-force-d3d12` and `-force-vulkan` are read from the wiki**, which
  names them for seven games on the list (Cities: Skylines II, House Flipper 2,
  Tainted Grail...); they were missed, so those games stayed on DX11. A "don't"
  in the sentence before no longer cancels a flag either.

### Removed

- **AMD's driver FidelityFX libraries.** `amdxcffx64.dll` and `amdvkffx64.dll`
  are no longer shipped (the plugin zip is about 150 MB smaller) or put into
  games. The nightly's own FSR 4.1.2 upscaler DLLs (FidelityFX SDK 2.4) carry
  the INT8 Lite model that only `amdvkffx64.dll` used to have, and the nightly
  does not load either library any more.
- **The FSR 4 Lite preset's `[FSR]` keys.** `Fsr4GpuSupport=4`, `Fsr4Model=3`,
  `UpscalerIndex=0` and `Fsr4Preset=auto` are no longer written: they are what
  OptiScaler picks for the Steam Deck by itself now that it identifies Van
  Gogh as an INT8 Lite GPU. The preset keeps the `ffx`/`ffx_12` backends and
  ASI loading.
- **Code for installs this plugin never had.** It has not been released to
  anyone, so nothing needs carrying forward: the clean-up of OptiScaler
  0.9.4-era folders (support DLLs at the game root, `D3D12_Optiscaler/`), of
  the original plugin's in-game control plugin and its root-level `plugins/`
  OptiPatcher, the `.decky-optiscaler.bak` backups of its v0.1, the warning
  for an `OptiScaler.ini` still using `FGType`, defaults filled in for
  manifests without an engine or upscaler, and the list cache's format number.
  OptiScaler put in by hand (v10 layout) is still recognised and removed.

## [0.1.10] - 2026-10-29

### Added

- **What else a game needs is said up front.** Some games are on the
  compatibility list as working only with something else in place first: a
  mod OptiScaler hooks into (a Luma build, a DLSS mod, SekiroTSR, ERSS-FG,
  Warhammer3DLSS), `nvngx_dlss.dll` copied into the folder, Engine.ini lines,
  an anti-cheat switched off, a Steam beta branch. The Setup tab now lists
  these in **OptiScaler 말고 필요한 것**, above the steps and after the
  install, each marked **필수** or **권장** with the wiki's own sentence and
  where to get it. They are not installed from here. The games list marks
  such games **모드 필요** (or **추가 작업**) and names what they need.
  REFramework and PDPerfPlugin stay steps of their own, and launch arguments
  still go into the launch options.
- Every game in the wiki's **Luma Unreal Engine** table is marked as needing
  Luma's UE mod, and every game in **Upscaler mods support** as needing the
  upscaler mod its entry names: the list says so once per table, not per row,
  so the table a row came from is now kept. A list cached before this is
  refreshed on the next look rather than a day later, and the bundled list is
  refreshed (711 games).
- **OptiScaler's overlay moves off Insert in REFramework games.** REFramework's
  overlay opens on Insert too, so one press opened both. The pd-upscaler
  entries (Resident Evil 2/3/4/7/8, Devil May Cry 5) already moved
  OptiScaler's to Home through their own `ShortcutKey=0x24`; the others
  (Resident Evil Requiem, Monster Hunter Wilds, Onimusha, PRAGMATA) only say
  to move REF's, in REF's own menu, so nothing was changed there. Now any game
  installed with REFramework gets `ShortcutKey=0x24` (Home) for OptiScaler
  unless its entry names another key, and the checklist says OptiScaler opens
  on Home and REFramework on Insert. It is one of the wiki settings, so it
  follows the "위키 항목 따르기" switch.
- **Each upscaler says what its way needs.** In a game whose own FSR 3.1
  takes a drop-in but whose OptiScaler way needs something first (Resident
  Evil Requiem: REFramework), the OptiScaler upscalers say "REFramework도
  있어야 합니다" and the drop-in ones "REFramework 없이 동작합니다", marked
  **간단**.

## [0.1.9] - 2026-10-29

### Added

- **Pick the upscaler first.** A game's Setup tab now starts with the
  upscaler: **FSR 4 Lite** (OptiScaler nightly, the default), **FSR 4 lossy2**
  (the drop-in), **HLX FSR 4** or **HLX DLSS**. How it goes in follows from the
  pick and the game's own files, and only that way's steps are shown. Options
  the game cannot take say why; the one a game has is marked 적용됨, and
  picking another offers to switch in place, keeping the file name, the ini and
  the launch options.
- **HLX DLSS and HLX FSR 4 from HelixSR.**
  [HelixSR](https://github.com/lonewolf0622/HelixSR) runs NVIDIA's DLSS
  network and AMD's FSR 4 network as plain compute shaders. Both are built on
  the user's own machine from NVIDIA's and AMD's files and may not be shared,
  so the plugin neither downloads nor builds them: set HelixSR up once with
  HelixSR Desktop in Desktop Mode, and installs here copy that build.
  - **HLX DLSS** goes in with HelixSR Scaler, HelixSR's OptiScaler fork, with
    the ini keys HelixSR's own installer writes (`Dx12Upscaler=dlss`,
    `[DLSS] HelixSR=true`). The Scaler's own OptiPatcher is used as it comes,
    with ASI loading on, as HelixSR does.
  - **HLX FSR 4** is a drop-in in a game with FSR 3.1, put in the way
    HelixSR's own drop-in is (under the game's file name, the game's file kept
    beside it as `*.original.dll`), and HelixSR Scaler in any other game.
  - Settings and the HLX options say whether a build is here, built or not,
    with a **HelixSR 다시 확인** button. A game HelixSR Desktop itself
    installed into is left to it.
  - **Update installed games** moves HLX games to a newer HelixSR build when
    HelixSR Desktop has made one, and FSR 4 Lite games to the nightly as
    before. Switching a game between the nightly and HelixSR Scaler starts
    the OptiScaler folder over, so neither leaves files behind.

### Changed

- The Quick Access games list shows **four games a page**, and both games
  lists open on the **설치됨** tab when any game is set up.
- The drop-in panel is shown when a drop-in upscaler is picked (or one is in
  place), rather than on every game with FSR 3.1.
- With HelixSR Scaler, the FidelityFX version shown is AMD's, read from the
  `*.amd.dll` beside HLX FSR 4.

## [0.1.8] - 2026-10-28

### Changed

- **PDPerfPlugin.dll is no longer shipped; you supply it.** PureDark's
  UpscalerBasePlugin may not be redistributed, so it is out of the package.
  Download UpscalerBasePlugin 1.1.2 from
  [Nexus Mods](https://www.nexusmods.com/site/mods/502) and leave
  `PDPerfPlugin.dll` in `~/Downloads` (any subfolder): the plugin finds it,
  keeps a copy and installs it with REFramework as before. Settings and the
  pd-upscaler games' checklist say where to get it, where to put it and
  whether it is here, with a **다시 확인** button; a build other than 1.1.2 is
  used with a warning, and a game set up before the file was supplied can be
  given it from a button. Copies already in game folders are kept.
- **Getting PDPerfPlugin.dll onto the Deck without Desktop Mode.** "휴대폰으로
  받아서 보내기" shows two QR codes in turn: the first opens the Nexus Mods
  files tab on a phone to download it, the second opens a one-file page on the
  Deck's own address, over the same Wi-Fi, to send it. The page uses a fresh
  random address, takes one file (the DLL, or the zip/7z it came in, which is
  unpacked), and closes once it has it, after ten minutes, or when the step is
  left. "파일 선택 (SD 카드·USB)" picks the file, or its archive, with Decky's
  file picker instead.

## [0.1.7] - 2026-10-28

### Changed

- **Releases come from a private source repository.** The plugin's code is
  kept in a private repository now, and each release is published here as
  before, so installs, the update button and *Install from URL* work the same.

## [0.1.6] - 2026-10-28

- Translate the README into Korean

## [0.1.5] - 2026-10-28

### Changed

- **OptiPatcher is no longer bundled; it is downloaded like OptiScaler.** The
  first install that wants it fetches the newest `rolling` build, checked
  against GitHub's digest, and every game shares that copy. `bin/` holds only
  AMD's driver libraries and PDPerfPlugin now.
- **With no download and no connection, OptiScaler still goes in** and the
  install says OptiPatcher could not be fetched, the way a failed REFramework
  download is reported. A reinstall keeps the OptiPatcher the game already has
  rather than dropping it. Settings shows the downloaded build, or that none is
  downloaded yet.

## [0.1.4] - 2026-10-28

### Added

- **OptiPatcher is a step you can see and switch off.** Where the wiki's
  OptiPatcher column lists the game, the setup checklist shows "OptiPatcher 함께
  설치 — 위키 권장", on, with what it does (opens DLSS / DLSS-FG inputs without
  spoofing the GPU, which some games need and others misbehave under);
  switching it off installs without it. It used to go in silently with no way
  to leave it out.
- **Manual setup starts OptiPatcher the way the wiki says**, instead of always
  off, and says when the wiki does not list the game. The OptiPatcher panel
  points out a recommended game that does not have it.
- **An `OP` badge in the games list** for games in the wiki's OptiPatcher column
  ("OptiPatcher 권장" on the full page).

### Changed

- **OptiPatcher is the newest rolling build.** Its supported games are compiled
  in and grow every week or two (Borderlands 4, Final Fantasy XIV, Marvel's
  Spider-Man 2 and more Nixxes ports since the build that shipped), while the
  wiki's OptiPatcher column follows the newest one, so an install now downloads
  the `rolling` release's `OptiPatcher.asi`, checked against GitHub's digest
  over verified TLS, and asks again every six hours or on **Check for a newer
  nightly**. Offline it uses the last download, and with none the bundled copy,
  now the 2026-10-27 rolling build.
- **Updating installed games brings OptiPatcher up to date too.** A game already
  on the current nightly with an older OptiPatcher gets the newer `.asi` and
  nothing else; the game page offers the same for one game, and Settings shows
  which build installs use.

## [0.1.3] - 2026-10-28

### Added

- **FSR drop-in: FSR 4 without OptiScaler or REFramework**, for games that ship
  FSR 3.1 as a DirectX 12 DLL of their own (Monster Hunter Wilds, Resident
  Evil Requiem and others). The game's FSR option keeps working and runs FSR 4
  instead: its upscaler file is swapped for cyboman's shader-optimised FSR
  4.1.1 build for the Steam Deck ("lossy2", from
  [fsr4-shader-performance-overrides](https://github.com/zgauthier2000/fsr4-shader-performance-overrides),
  GPL-2.0, AMD's GPU check lifted), or, where the game has one all-in-one
  `amd_fidelityfx_dx12.dll`, that file becomes AMD's SDK 2 loader beside the
  upscaler and the frame generator. Downloaded from the newest `dll-*` release
  and checked against GitHub's digest; every replaced file is backed up and put
  back on removal; it never shares a folder with OptiScaler. The game page
  offers it above the setup checklist and says when a game update has put the
  original back. Not for online games or games with anti-cheat.
- **The pd-upscaler games set themselves up** (Resident Evil 2, 3, 4, 7, 8 and
  Devil May Cry 5). PureDark's PDPerfPlugin.dll (UpscalerBasePlugin 1.1.2, the
  build the wiki names; 1.2.0 does not load) now ships in `bin/`, pinned by
  hash, and goes in with REFramework; and `libxess.dll` is copied to the game
  root beside it, where PDPerfPlugin looks for it now that OptiScaler v10 keeps
  it in `OptiScaler/` — without that its upscaler never started. Both are
  recorded in the install, kept through reinstalls and removed with
  REFramework.
- **The games list says how FSR 4 gets into each game**: **드롭인** for a game
  whose own FSR 3.1 can be swapped, **REF 필수** for one where OptiScaler is the
  only way and the wiki says it needs REFramework. A drop-in game the wiki
  still sends through REFramework for OptiScaler (Monster Hunter Wilds,
  Resident Evil Requiem) shows **드롭인** and **REF** — "OptiScaler는
  REFramework 필요" — since both ways stay open: the game page offers the
  drop-in above the OptiScaler checklist, which installs REFramework with it.

### Changed

- **REFramework is downloaded and installed again** for the RE Engine games
  whose wiki entry needs it (Resident Evil, Devil May Cry 5, Monster Hunter
  Wilds, PRAGMATA and others): praydog's REFramework-nightly, or the per-game
  pd-upscaler build from TheRazerMD/REFramework where the entry asks for it.
  Every download is now checked against the SHA-256 GitHub's release API names
  for that exact file, the API is read over verified TLS only, and only files
  from those two repositories' own releases are taken. Builds are cached by
  hash, a newer release is picked up, and offline the last verified build is
  used. Devil May Cry 5 is pinned to the build its wiki entry links, because
  newer pd-upscaler builds are broken there.

### Fixed

- The 0.1.2 note on REFramework tracking described the wrong symptom: what a
  reinstall lost was REFramework's own removal (it stayed behind in a game
  with no `dinput8.dll` of its own), not the game's original file.

## [0.1.2] - 2026-10-28

### Changed

- **The interface is in Korean.** Every screen, notice, toast, button and
  badge, the Steam library menu entry ("OptiScaler 설정"), and the messages the
  backend shows in the UI — compatibility badges' reasons, the wiki plan's
  warnings, REFramework's reasons. Product names, file names and ini keys stay
  as they are; low-level error details stay in English.

### Added

- **The plugin tells you when a newer release is out, and installs it.**
  Decky Loader only offers updates for plugins from its store, so this one
  asks its own GitHub releases (every six hours, or from **Settings → Check
  for updates**) and shows **Update to x.y.z** in the Quick Access panel, on
  the main page and in Settings. The button hands the release to Decky's own
  installer, which checks the zip against the release's SHA-256 and asks
  before replacing anything.
- **Update every game on an older nightly at once.** Settings lists the games
  set up from an older OptiScaler build and **Update N games** installs the
  downloaded nightly in each, keeping its filename, settings and OptiPatcher.
  A game that is running is skipped.

### Fixed

- Installing OptiScaler again over a game whose REFramework came from this
  plugin kept the file but stopped tracking it: the game page showed it as
  installed by hand, and uninstalling OptiScaler afterwards left REFramework's
  `dinput8.dll` behind in a game that had none of its own. (A game's own
  `dinput8.dll` was always restored.) It is tracked through reinstalls now.

## [0.1.1] - 2026-10-28

### Changed

- **The games list pages instead of growing.** **‹ Prev** and **Next ›** swap
  one page for the next, with the range shown between them (`9–16 of 87`), so
  the list is never longer than a page and there is nothing to scroll back up
  through. The pager wraps around, so the focus is never left on a dead button.
- **The Quick Access panel shows eight games a page, one line each**: the name
  and its badge. The full page keeps twenty a page and the line that says why.

## [0.1.0] - 2026-10-28

The first Decky OptiScaler Plus release: OptiScaler v10 from the nightly
channel, FSR 4 Lite on every install, and the settings left to OptiScaler's own
overlay.

### Changed

- **Renamed to Decky OptiScaler Plus**, with its own Decky route and context
  menu entry, so it installs as a separate plugin next to Decky OptiScaler
  rather than over it. Games set up by Decky OptiScaler are still recognised as
  managed; the plugin's own remembered choices start fresh.
- **Every push to `main` is released** by the release workflow: it picks the
  version, runs the checks, records the version in `package.json` and this
  file, tags it and publishes the zip.

- **OptiScaler is no longer bundled.** The first install downloads the newest
  build from [OptiScaler-nightly](https://github.com/optiscaler/OptiScaler-nightly/releases)
  (v10 today), checks it against the SHA-256 its release names — read over a
  verified TLS connection only — and every game shares it. The channel is asked
  again after six hours or from **Settings → Check for a newer nightly**; a game
  keeps its build until it is installed again. Offline, the last download is
  used; the very first install needs a connection.
- **Every install sets the game up for FSR 4 Lite.** AMD's driver FidelityFX
  libraries (`amdxcffx64.dll`, `amdvkffx64.dll` — the Vulkan one is the only
  place the INT8 Lite model exists) ship with the plugin, hash-pinned, and go
  into the game's `OptiScaler/` folder; the ini gets `Dx12Upscaler=ffx`,
  `Dx11Upscaler`/`VulkanUpscaler=ffx_12`, `Fsr4GpuSupport=4`, `Fsr4Model=3`,
  `UpscalerIndex=0`. Setup shows whether the preset is still in place and can
  apply it again. See [Steam Deck FSR 4 Lite](docs/steam-deck-fsr4.md).
- **v10's folder layout.** OptiScaler's libraries live in `OptiScaler/` and its
  plugins in `OptiScaler/plugins/`. Installing over a 0.9.4-era game removes
  the old root-level DLLs, `D3D12_Optiscaler/` and the old `plugins/` folder,
  handing back anything of the game's they had displaced; OptiPatcher moves
  with it. Thanks to [@n1ckmp3](https://github.com/n1ckmp3), whose
  `fsr4-lite-v10` branch worked out the v10 port and the preset.
- The ini schema is generated from a v10 nightly's `OptiScaler.ini`, and now
  reads choices written above a separate `Default (auto) is …` line, so
  `Upscalers.Dx12Upscaler` is validated as the closed set it is.

### Removed

- **The Basic and Advanced settings screens.** Change settings in OptiScaler's
  overlay (`Insert`; bind it in Steam Input), which applies most of them while
  the game runs and saves them with **Save Settings**.
- **Live control from the Quick Access panel**, its in-game ASI and the frame
  rate tiles. The ASI read OptiScaler's memory at offsets fixed to 0.9.4, which
  a nightly that changes daily cannot keep up with; the overlay does the same
  job from inside the game. Reinstalling or uninstalling removes the old ASI.
- **FSR 4.1.1b — Steam Deck** and FSR 4 file import, replaced by FSR 4 Lite.

### Added

- **The games list says which games OptiScaler is worth trying in**, before
  you open any of them. Each row gets a badge from two checks: the game's own
  folder (a shipped DLSS, XeSS or FSR library, a 64-bit Windows executable,
  anti-cheat) and the wiki's compatibility list. **WIKI ✓**, **PARTIAL** and
  **NO** are the wiki's word; **LIKELY**, **ANTI-CHEAT** and **?** come from the
  folder alone; **N/A** is a 32-bit or native Linux install, whatever the wiki
  says. A new **Compatible** tab lists the hopeful ones. The badges fill in
  after the list, recently played first, and a folder is only walked again
  once it changes. Matching a game against the compatibility list is about four
  times faster for it, with identical results: candidates that could not reach
  the match threshold are ruled out before the full comparison.

## [0.0.7] - 2026-09-18

FSR 4 on the Steam Deck, and the compatibility list is whole again.

### Added

- **FSR 4.1.1b — Steam Deck**, in the Basic upscaler dropdown. One choice
  downloads the community RDNA 2 build of the FidelityFX upscaler, checks it
  against a hash pinned in the plugin, puts it next to the game and switches on
  the INT8 override that reaches FSR 4 on RDNA 2. Close the game first; it
  applies on the next launch. Frame generation is left exactly as it was.
  Thanks to [@drewboardman](https://github.com/drewboardman), who built this and
  tested it on a Deck.
- Setup names which upscaler build is in the game folder, identified by its bytes
  rather than its version — the community build reports the same 4.1.1 the
  released SDK does — and will put the bundled one back.

### Fixed

- **297 of the 695 games on the compatibility list were answering "no wiki entry
  matched".** One row on the wiki was saved without its leading `|`, which the
  parser read as the end of the table, so everything after Metro Exodus was
  invisible: Monster Hunter Wilds, the Resident Evil entries, Stalker 2, The
  Witcher 3 and 293 others. A row that lost its first character is now read as
  the row it is. Bundled list regenerated — 698 entries.
- Games listed under *Upscaler mods support* and *Luma Unreal Engine* no longer
  claim OptiPatcher support they do not have, and their notes are their notes
  rather than the images column. Those two tables have one column fewer than the
  main one, and were being read as though they did not.
- The refreshed list adds Onimusha: Way of the Sword to the games that need
  REFramework in place before OptiScaler can do anything.
- All six FSR 4 quality presets are offered. The reference INI writes them as one
  comma-separated line, of which two were being read, so Quality, Performance,
  DRS and Ultra Performance were rejected by the settings writer and never
  reached the file.
- Choosing an FSR version on RDNA 2 no longer turns on the FSR 4 upgrade path.
  That path forces the FP8 model, which such a GPU does not have, and OptiScaler
  answers with a silent FSR 3 fallback.
- Verification recognises a community upscaler by hash, and reinstalling keeps it
  instead of overwriting it with the bundled build.
- Replacing the upscaler is atomic and rolls back the DLL, the INI and the
  manifest together if any part of it fails. It refuses while the game is
  running, and on an install this plugin did not make.

[0.0.7]: https://github.com/danielcamilo1/decky-optiscaler/releases/tag/v0.0.7

## [0.0.6] - 2026-08-28

Everything from the `0.0.5.x-testing` prereleases, as one release.

### Added

- Non-Steam games can be set up. Their folder is taken from the shortcut's
  target, since Steam reports no install folder for them.
- Games whose wiki entry requires
  [REFramework](https://github.com/praydog/REFramework) say so on the setup
  checklist and link the right build. Installing it for you is disabled for
  now, until I can gather more information to get it fully working.

### Fixed

- A non-Steam game's launch options are read from `shortcuts.vdf`, so removing
  OptiScaler no longer wipes them.
- Settings are read only from the install method this plugin actually performs.
  Monster Hunter Wilds would not boot because of this.
- Settings hedged by an "if", a "try", an "e.g." or a "desired" are reported
  rather than applied. Resident Evil 2 was getting 2× output scaling it never
  asked for.
- Setup names the OptiScaler overlay's new shortcut key when an entry moves it
  off Insert.
- Wiki pages with brackets in the name download again — Resident Evil, Dead
  Space (2023) and Elden Ring were affected. Bundled list regenerated.

[0.0.6]: https://github.com/danielcamilo1/decky-optiscaler/releases/tag/v0.0.6

## [0.0.5.3-testing] - 2026-08-27

Prerelease on the `testing` branch.

### Added

- Non-Steam games can be set up. Their folder is taken from the shortcut's
  target, since Steam reports no install folder for them.

### Changed

- Automatic REFramework setup is disabled for now, until I can gather more
  information to get it fully working. The games that need it still say so and
  link the right build, and REFramework installed by 0.0.5.1/0.0.5.2-testing can
  still be removed.

### Fixed

- A non-Steam game's launch options are read from `shortcuts.vdf`, so removing
  OptiScaler no longer wipes them.

## [0.0.5.2-testing] - 2026-08-24

Prerelease.

### Fixed

- Monster Hunter Wilds would not boot: settings were being read from install
  methods other than the one performed.
- Resident Evil 2 got 2× output scaling it never asked for. Settings hedged by
  an "if", a "try", an "e.g." or a "desired" are reported, not applied.
- Setup names the OptiScaler overlay's new shortcut key when an entry moves it
  off Insert.

## [0.0.5.1-testing] - 2026-08-24

Prerelease. REFramework auto-install — **disabled in 0.0.5.3-testing**.

### Added

- The nine compatibility-list games that need REFramework are detected, and the
  build, the `dinput8` override and `PDPerfPlugin.dll` are stated on the
  checklist.

### Fixed

- Wiki pages with brackets in the name download again — Resident Evil, Dead
  Space (2023) and Elden Ring were affected. Bundled list regenerated.

## [0.0.5] - 2026-08-23

### Added

- Removing OptiScaler asks what to do with the Steam launch options: restore
  what was there, remove only the OptiScaler override, or change nothing. The
  answer can be remembered.
- A Settings tab on the main page: remembered answers, the switch that stops
  answers being kept, and the state of the compatibility list.
- A copy of the compatibility list ships with the plugin, so an offline Deck
  still matches games.

### Changed

- The compatibility list is read from cache and refreshed in the background,
  instead of a network timeout in front of every question.

### Fixed

- Launch options are read from three sources, not just
  `SteamClient.Apps.GetAppLaunchOptions`, which some client builds do not have.
- A wiki that will not download is no longer reported as "your game is not on
  the list", and there is a **Try again** button.
- A stalled connection is retried over IPv4.
- The last-resort unverified TLS context no longer reads the system trust store.

[0.0.5]: https://github.com/danielcamilo1/decky-optiscaler/releases/tag/v0.0.5

## [0.0.4] - 2026-08-21

### Added

- The exact FSR version the running game built, rather than just the backend id.
- A second dropdown for which FSR version to run. Applies without a restart.
- Both frame rates while frame generation is on: what the game renders and what
  reaches the screen.
- A live-control readout that says why a number is missing, and a warning when a
  game's in-game plugin is out of date.

### Fixed

- A dropdown could keep a name its option list no longer used.
- Asking for FSR 4 could silently give you FSR 3.
- A game on the SD card reported itself as "writing to a different folder".
- The newest FSR version was named after the reference INI's build, not the
  bundled one.

[0.0.4]: https://github.com/danielcamilo1/decky-optiscaler/releases/tag/v0.0.4

## [0.0.3] - 2026-08-20

### Fixed

- The upscaler dropdown lagged one change behind after reopening the panel.
- The FidelityFX FG version control disappeared on games reporting one
  generator.

[0.0.3]: https://github.com/danielcamilo1/decky-optiscaler/releases/tag/v0.0.3

## [0.0.2] - 2026-08-20

### Fixed

- A control could display a value it was not set to.
- Picking the third FidelityFX frame generator did nothing.
- Settings the config writer refused are reported instead of left on screen.
- Re-reading the config could undo an edit or blank the panel.
- The live upscaler switch works for DX11 games.

[0.0.2]: https://github.com/danielcamilo1/decky-optiscaler/releases/tag/v0.0.2

## [0.0.1] - 2026-08-20

First public release.

### Added

- Per-game install, into a folder scored automatically and overridable by hand.
  Steam libraries including the SD card, plus any folder as a custom library.
- Automatic setup from the OptiScaler
  [Compatibility List](https://github.com/optiscaler/OptiScaler/wiki/Compatibility-List),
  as a checklist that names the wiki field behind every line before writing it.
- Basic settings (four controls) and Advanced (all 288 options across 34
  sections), generated from the shipped `OptiScaler.ini` and preserving its
  comments.
- Live in-game control of frame generation, the FidelityFX FG version and the
  upscaler, with a frame rate readout, via a bundled ASI plugin.
- Quick Access panel: the running game's live controls and a filtered game list.
- Files an install would overwrite are backed up and restored on uninstall.
- `OptiScaler.log` parsing, bundled
  [OptiPatcher](https://github.com/optiscaler/OptiPatcher), and an **OptiScaler
  Settings** entry in the Steam library context menu.

[0.0.1]: https://github.com/danielcamilo1/decky-optiscaler/releases/tag/v0.0.1
