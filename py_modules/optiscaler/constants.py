"""Shared constants for the Decky Upscaler Manager plugin."""

# OptiScaler itself is not bundled. Every install uses the newest build on the
# project's nightly channel, downloaded once and shared by every game. The
# release API is the trust anchor: it names the archive and its SHA-256, and is
# only ever read over a verified TLS connection (see nightly.py).
NIGHTLY_REPO = "optiscaler/OptiScaler-nightly"
# Enough to list every build since the one a plugin build was made against.
NIGHTLY_RELEASES_API = f"https://api.github.com/repos/{NIGHTLY_REPO}/releases?per_page=60"
NIGHTLY_RELEASES_PAGE = f"https://github.com/{NIGHTLY_REPO}/releases"
# The one asset a nightly release carries, e.g. OptiScaler_v10.0.0-pre1_20261027.7z.
NIGHTLY_ASSET_RE = r"^OptiScaler_v?(?P<version>.+?)_(?P<date>\d{8})\.7z$"
# How long a downloaded nightly is used before the channel is asked again.

# The newest build of each download channel when this plugin was built, written
# by scripts/pin_channels.py in the release workflow. Settings offers that build
# and every one published since to pick from, instead of always the newest.
CHANNEL_BASELINE = "channel-baseline.json"
CHANNELS = ("nightly", "dropin", "helixsr")
CHANNEL_LIST_TTL = 10 * 60  # seconds
# How often the channels are asked whether a newer build is out, for the
# notice on the main page; Settings can ask at once.
UPDATE_CHECK_TTL = 6 * 60 * 60  # seconds
# What "remove downloaded files" removes under the plugin's runtime folder:
# everything downloaded, nothing the user put there (user-files) and not the
# compatibility list, which is not a download the set-up makes.
RUNTIME_DOWNLOADS = ["nightly", "payload", "fsr4-dropin", "helixsr", "optipatcher", "reframework"]

# This plugin's own releases, published by .github/workflows/release.yml. The
# latest one is compared with the running version, and Decky Loader is handed
# its zip to install when the user asks. Read over verified TLS only, like the
# nightly channel: the SHA-256 it names is what Decky checks the zip against.
PLUGIN_REPO = "supercleans/decky-upscaler-manager"
PLUGIN_RELEASE_API = f"https://api.github.com/repos/{PLUGIN_REPO}/releases/latest"
PLUGIN_ASSET_RE = r"^Decky-Upscaler-Manager-v(?P<version>[0-9][0-9A-Za-z.\-]*)\.zip$"
PLUGIN_CHECK_TTL = 6 * 60 * 60  # seconds

# cyboman's shader-optimised FSR 4 builds for RDNA2 integrated graphics (the
# Steam Deck), from fsr4-shader-performance-overrides (GPL-2.0): AMD's GPU
# check lifted, so they start on RDNA2, and AMD's FidelityFX loader does not
# check signatures. Each is one amd_fidelityfx_upscaler_dx12.dll. A game that
# ships FSR 3.1 as its own DLL takes one as a drop-in, with no OptiScaler and no
# REFramework; any other game gets it in place of the OptiScaler nightly's own.
# Taken from the newest `dll-*` release, verified against GitHub's digest for
# the archive. From 2026-10-29 the archive is built on FSR 4.1.2 and carries
# four folders; the two built on AMD's smaller Lite network are offered here.
DROPIN_REPO = "zgauthier2000/fsr4-shader-performance-overrides"
DROPIN_RELEASES_API = f"https://api.github.com/repos/{DROPIN_REPO}/releases?per_page=60"
DROPIN_RELEASES_PAGE = f"https://github.com/{DROPIN_REPO}/releases"
DROPIN_ASSET_RE = r"^fsr4\.1\.\d+-igpu-cyboman-rdna2-(?P<date>[0-9][0-9.\-]*)\.7z$"
# The archive's folders for the two Lite builds: AMD's Lite picture byte for
# byte, a little faster; and a retrained one, about 18% faster than AMD's Lite.
CYBOMAN_LITE_EXACT = "4.1.2l-exact"
CYBOMAN_LITE_LOSSY = "4.1.2l-lossy"
# In a game without FSR 3.1 of its own, OptiScaler runs one as a custom upscaler:
# OptiScaler/custom/<name>/ffx/<dll> becomes an entry of its own in the overlay's
# DX12 list, beside AMD's, and Dx12Upscaler=<name> makes it the one used. DX11
# takes no custom name, and a custom one for Vulkan wants a Vulkan DLL, which
# cyboman does not build, so those games run AMD's FSR 4 from the nightly.
CUSTOM_UPSCALER_DIR = "custom"
DROPIN_MANIFEST = ".decky-optiscaler-dropin.json"
# What a game's own FSR 3.1 looks like on disk. With the upscaler as a file of
# its own (FidelityFX SDK 2), only that file is swapped. With one monolithic
# amd_fidelityfx_dx12.dll (SDK 1.x), that file becomes AMD's SDK 2 loader under
# the same name, beside the upscaler and the frame generator - the loader and
# frame generator come from the OptiScaler nightly, which carries both.
FFX_DX12_DLL = "amd_fidelityfx_dx12.dll"
FFX_UPSCALER_FILE = "amd_fidelityfx_upscaler_dx12.dll"
FFX_LOADER_FILE = "amd_fidelityfx_loader_dx12.dll"
FFX_FRAMEGEN_FILE = "amd_fidelityfx_framegeneration_dx12.dll"

# The folder OptiScaler v10 keeps its libraries in, next to the proxy dll. The
# ini's Libraries.OptiDllPath defaults to it, and so does Plugins.Path
# (``<OptiDllPath>/plugins``).
OPTI_DIR = "OptiScaler"

# What "FSR 4 Lite on a Steam Deck" means in v10 ini keys, written on every
# install (docs/steam-deck-fsr4.md). Since the nightly of 2026-10-29 the FSR
# 4.1.2 upscaler DLLs it ships carry the INT8 Lite model themselves, and
# OptiScaler identifies the Deck's Van Gogh as an INT8 Lite GPU on its own, so
# the [FSR] keys stay at their defaults: FSR 4 (UpscalerIndex 0) on the best
# model the GPU has. What is left is the backend: DX12 reaches FSR 4 through
# `ffx`, written so that a game switched from another upscaler comes back to
# it, and DX11/Vulkan through its DX12 interop variant `ffx_12` (their default
# is FSR 2.2). Everything else is left to OptiScaler's own overlay.
#
# ASI loading is always on: OptiScaler reads OptiScaler/plugins/*.asi only with
# it, which is where OptiPatcher goes (and where HelixSR Scaler ships its own),
# and with no .asi there it has nothing to load.
ASI_LOADING = {"Plugins": {"LoadAsiPlugins": "true"}}
DECK_FSR4_PRESET = {
    "Upscalers": {"Dx12Upscaler": "ffx", "Dx11Upscaler": "ffx_12",
                  "VulkanUpscaler": "ffx_12"},
    **ASI_LOADING,
}

# HelixSR (https://github.com/lonewolf0622/HelixSR) runs NVIDIA's DLSS network
# (HLX DLSS) and AMD's FSR 4 network (HLX FSR 4) as plain D3D12 compute shaders.
# HLX DLSS has to be built on the user's own machine from NVIDIA's files, which
# may not be shared: a build HelixSR Desktop made is used when there is one, and
# otherwise the release this plugin downloads is built here, by HelixSR's own
# setup run unmodified (hlxbuild.py). HLX DLSS installs copy that build. It only
# runs inside HelixSR Scaler, HelixSR's OptiScaler fork (GPL-3.0), which the
# same release carries.
#
# HLX FSR 4 comes built in the release ZIP from 3.2.0 (made from AMD's MIT
# FSR SDK), so it is downloaded like cyboman's builds (hlx.py). It is a
# FidelityFX DLL of its own: a drop-in in a game with FSR 3.1, and an
# OptiScaler custom upscaler in any other.
HELIXSR_PAGE = "https://github.com/lonewolf0622/HelixSR/releases/latest"
# Where a build is looked for, as HelixSR Scaler's own setup_linux.sh does:
# HelixSR Desktop's releases first, then a ZIP extracted somewhere obvious.
HELIXSR_SEARCH = [
    ".local/share/HelixSR-Desktop/releases/*/HelixSR",
    ".local/share/HelixSR-Desktop/releases/*/HelixSR*/HelixSR",
    "Downloads/HelixSR*/HelixSR",
    "Downloads/*/HelixSR*/HelixSR",
    "HelixSR*/HelixSR",
    "Desktop/HelixSR*/HelixSR",
]
HELIXSR_DIR = "HelixSR"
HELIXSR_DLL = "helixsr.dll"
HELIXSR_SCALER_DIR = "helixsr-scaler"
HELIXSR_HLX_DIR = "HLX-FSR4"
# A built helixsr.dll ends in a 32-byte trailer starting HXSRNET1 (HXSRFG01
# with frame generation after it); a built HLX FSR 4 in a 24-byte one starting
# HLXFSR4D. Copied straight out of the ZIP, neither has one and neither runs.
HELIXSR_NET_TRAILERS = (b"HXSRNET1", b"HXSRFG01")
HELIXSR_HLX_TRAILER = b"HLXFSR4D"
# What HelixSR Desktop (or HelixSR Scaler's own setup) leaves in a game it
# installed into: such a game is that app's to update and remove, not ours.
HELIXSR_FOREIGN_MARKERS = ["HelixSR-Scaler.files", f"{HELIXSR_DIR}/helixsr-install.json"]
# Where HelixSR Scaler keeps AMD's own FidelityFX upscaler, beside HLX FSR 4.
FFX_UPSCALER_AMD_FILE = "amd_fidelityfx_upscaler_dx12.amd.dll"
# HelixSR's releases: the ZIP from the first release that carries HLX FSR 4
# built, unpacked whole, HLX-FSR4/<FFX_UPSCALER_FILE> used as it is and the
# rest there for HLX DLSS to be built in.
HELIXSR_REPO = "lonewolf0622/HelixSR"
HELIXSR_RELEASES_API = f"https://api.github.com/repos/{HELIXSR_REPO}/releases?per_page=60"
HELIXSR_ASSET_RE = r"^HelixSR-(?P<version>\d+\.\d+\.\d+)\.zip$"
HELIXSR_PREBUILT_HLX = (3, 2, 0)
# HelixSR's setup, which builds HLX DLSS in its release folder: the script the
# user would run, and the Python one it calls, which names NVIDIA's DLL. Frame
# generation is left out: nothing here uses it, and it needs more of NVIDIA's.
HELIXSR_SETUP = "helixsr-setup.sh"
HELIXSR_SETUP_PY = "setup/helixsr_setup.py"
HELIXSR_SETUP_ARGS = ("--no-fg",)
# Where the setup looks for the Wine it runs Microsoft's shader compiler with,
# under the user's home, before a system one: told apart here only to say
# "install Proton" before starting a build that would stop for want of it.
# Where HelixSR's setup keeps what it downloads (a portable Python, Microsoft's
# shader compiler), shared with HelixSR Desktop, which keeps its own data
# beside it: removed with the plugin's downloads only when that app is not here.
HELIXSR_TOOLS_DIR = ".local/share/HelixSR"
HELIXSR_DESKTOP_DATA = ".local/share/HelixSR-Desktop"
HELIXSR_WINE_SEARCH = [
    ".local/share/Steam/steamapps/common/Proton*/files/bin/wine",
    ".steam/steam/steamapps/common/Proton*/files/bin/wine",
    ".local/share/Steam/compatibilitytools.d/*/files/bin/wine",
    ".steam/root/compatibilitytools.d/*/files/bin/wine",
]

# The upscaler a game is set up for, picked first; how it gets in follows.
UPSCALER_FSR4_LITE = "fsr4-lite"      # nightly's AMD FSR 4.1.2: drop-in with FSR 3.1 (a test), else
                                      # OptiScaler nightly + FSR 4 Lite preset
UPSCALER_LITE_EXACT = "fsr412l-exact" # cyboman: drop-in with FSR 3.1, else in OptiScaler (custom)
UPSCALER_LITE_LOSSY = "fsr412l-lossy" # likewise
UPSCALER_HLX_FSR4 = "hlx-fsr4"        # HelixSR's release: likewise
UPSCALER_HLX_DLSS = "hlx-dlss"        # HelixSR Scaler, from the user's HelixSR set-up
UPSCALERS = [UPSCALER_FSR4_LITE, UPSCALER_LITE_EXACT, UPSCALER_LITE_LOSSY,
             UPSCALER_HLX_FSR4, UPSCALER_HLX_DLSS]
DEFAULT_UPSCALER = UPSCALER_FSR4_LITE
# Where another one is the better start (sysinfo.gpu_info()["device"]). The
# BC-250 is not given FSR 4 by OptiScaler, and runs int8 slowly; HLX FSR 4
# picks its fp16 version there.
DEVICE_UPSCALERS = {"bc250": UPSCALER_HLX_FSR4}
# And where only some can be picked at all: on the BC-250, AMD's FSR 4 and
# cyboman's builds of it are left to OptiScaler's own GPU check, which turns
# that GPU down, so only HelixSR's two.
DEVICE_ALLOWED_UPSCALERS = {"bc250": [UPSCALER_HLX_FSR4, UPSCALER_HLX_DLSS]}
# cyboman's archive folder for each of its upscalers.
CYBOMAN_VARIANTS = {UPSCALER_LITE_EXACT: CYBOMAN_LITE_EXACT, UPSCALER_LITE_LOSSY: CYBOMAN_LITE_LOSSY}
# The FidelityFX upscaler builds an OptiScaler install carries besides AMD's,
# every one of them whichever is picked, so the overlay can switch between
# them: each one's folder in OptiScaler/custom, also its name in the overlay's
# DX12 list. The picked one takes AMD's place as OptiScaler's own FidelityFX
# upscaler instead, since DX11 and Vulkan games reach FFX only through the DX12
# interop backends (ffx_12), which cannot name a custom one; AMD's own then
# moves into the custom folder (CUSTOM_AMD_NAME).
CYBOMAN_CUSTOM_NAMES = {upscaler: f"cyboman-{variant}" for upscaler, variant in CYBOMAN_VARIANTS.items()}
CUSTOM_UPSCALER_NAMES = {**CYBOMAN_CUSTOM_NAMES, UPSCALER_HLX_FSR4: "hlx-fsr4"}
CUSTOM_AMD_NAME = "amd-fsr4"
# The drop-in variant each drop-in upscaler installs.
DROPIN_VARIANT_HLX = "hlx"
DROPIN_VARIANT_AMD = "amd"
DROPIN_VARIANTS = {**CYBOMAN_VARIANTS, UPSCALER_HLX_FSR4: DROPIN_VARIANT_HLX,
                   UPSCALER_FSR4_LITE: DROPIN_VARIANT_AMD}
# Which OptiScaler build an install uses: the nightly, or HelixSR Scaler.
ENGINE_NIGHTLY = "nightly"
ENGINE_HELIXSR = "helixsr"
# What each upscaler means in ini keys, written on every install of it as the
# FSR 4 Lite preset always was. HLX DLSS takes Dx12Upscaler=dlss, as HelixSR's
# own installer writes it ([DLSS] HelixSR is true by default and not written),
# with ASI loading on as everywhere.
UPSCALER_PRESETS = {
    UPSCALER_FSR4_LITE: DECK_FSR4_PRESET,
    # The picked build sits where AMD's would, so the same FFX backends run it.
    **{upscaler: DECK_FSR4_PRESET for upscaler in CUSTOM_UPSCALER_NAMES},
    UPSCALER_HLX_DLSS: {
        **DECK_FSR4_PRESET,
        "Upscalers": {"Dx12Upscaler": "dlss", "Dx11Upscaler": "auto",
                      "VulkanUpscaler": "auto"},
    },
}

INI_NAME = "OptiScaler.ini"
LOG_NAME = "OptiScaler.log"
# Written by this plugin so an install can be recognised later with certainty.
MANIFEST_NAME = ".decky-optiscaler.json"
# Anything OptiScaler would overwrite is moved here instead, and moved back on
# uninstall. Kept as a visible folder so it is obvious what happened.
BACKUP_DIR = "decky_optiscaler_backup_files"
# The same idea for the one thing that is not a file in this folder: the Steam
# launch options the game had before OptiScaler went in. Only the frontend can
# read them out of Steam, so they are handed here and written verbatim, and
# removing OptiScaler can then offer to put them back.
LAUNCH_RECORD_NAME = "decky_optiscaler_previous_launch_options.txt"

# OptiPatcher (https://github.com/optiscaler/OptiPatcher) is a separate ASI from
# the OptiScaler project. It patches supported games so their DLSS/DLSS-FG
# inputs are exposed without DXGI spoofing, which some games - Red Dead
# Redemption 2, for one - need before OptiScaler can do anything useful. Its
# list of supported games is compiled in and grows every week or two, while the
# wiki's OptiPatcher column follows the newest build. So, like OptiScaler, it
# is not bundled: the first install that wants it downloads the newest
# `rolling` build, verified against GitHub's digest (see optipatcher.py).
OPTIPATCHER_NAME = "OptiPatcher.asi"
OPTIPATCHER_REPO = "optiscaler/OptiPatcher"
OPTIPATCHER_TAG = "rolling"
OPTIPATCHER_RELEASE_API = (
    f"https://api.github.com/repos/{OPTIPATCHER_REPO}/releases/tags/{OPTIPATCHER_TAG}"
)
OPTIPATCHER_RELEASES_PAGE = f"https://github.com/{OPTIPATCHER_REPO}/releases/tag/{OPTIPATCHER_TAG}"
OPTIPATCHER_CHECK_TTL = 6 * 60 * 60  # seconds

# REFramework (https://github.com/praydog/REFramework) is a separate mod, not
# part of OptiScaler. A handful of RE Engine games — the Resident Evil titles,
# Devil May Cry 5, Monster Hunter Wilds, PRAGMATA — cannot host OptiScaler at
# all without it, because REF is what exposes the upscaler hooks OptiScaler
# attaches to. The compatibility list says so in prose ("Requires REFramework"),
# and until this the plugin read straight past it: the install succeeded, the
# launch options were set, and the game rendered exactly as it had before.
#
# Both builds ship the same single file, which is the whole reason installing it
# from here is safe to do automatically.
#
# Automatic installation was withdrawn in 0.0.5.3-testing, because placing a
# third-party engine hook in somebody's game folder on their behalf is a big
# promise. It is back on, with what made that promise hard to keep fixed: every
# download is now checked against the SHA-256 GitHub's release API names for
# that exact asset, the API is only read over verified TLS, and only an asset
# in the expected repository's own release downloads is taken. Setting this to
# False turns the download off again; detection, the launch-options override,
# the status read and removal do not depend on it.
REFRAMEWORK_AUTO_INSTALL = True
# What the plan says instead, in the sentence the checklist builds around it.
REFRAMEWORK_WITHHELD = (
    "이 플러그인은 더 이상 대신 다운로드하지 않습니다"
)
REFRAMEWORK_DLL = "dinput8.dll"
REFRAMEWORK_REVISION = "reframework_revision.txt"
# What may be taken out of an REFramework archive at all: this writes into a
# folder full of somebody's game, and "extract the zip" is not a thing to do on
# trust.
REFRAMEWORK_FILES = [REFRAMEWORK_DLL, REFRAMEWORK_REVISION]
# ...but only the DLL is placed next to the executable. The nightly's own
# release notes are blunt about it — "do NOT extract any file other than
# dinput8.dll into your game folder, or your game may become unstable" — so the
# revision stamp stays in the download cache and is recorded in our manifest
# instead, which is where we wanted to read it from anyway.
REFRAMEWORK_INSTALL_FILES = [REFRAMEWORK_DLL]

# praydog's own nightly, which is now one unified build covering every game it
# supports — hence a single asset rather than the per-game ones the wiki text
# still describes.
REFRAMEWORK_NIGHTLY_URL = (
    "https://github.com/praydog/REFramework-nightly/releases/latest/download/REFramework.zip"
)
REFRAMEWORK_NIGHTLY_PAGE = "https://github.com/praydog/REFramework-nightly/releases/latest"
# Where the nightly's digest comes from: the latest release, through the API.
REFRAMEWORK_NIGHTLY_API = (
    "https://api.github.com/repos/praydog/REFramework-nightly/releases/latest"
)
REFRAMEWORK_NIGHTLY_DOWNLOADS = "https://github.com/praydog/REFramework-nightly/releases/download/"

# The pd-upscaler branch, which the Resident Evil entries and DMC5 ask for by
# name. It is built per game, and PDPerfPlugin does not support the unified
# nightly above, so the two are genuinely different downloads rather than one
# being a newer version of the other. The official repo's artifact links expire,
# which is why the wiki points at this mirror.
REFRAMEWORK_PD_RELEASES = "https://api.github.com/repos/TheRazerMD/REFramework/releases"
REFRAMEWORK_PD_PAGE = "https://github.com/TheRazerMD/REFramework/releases"
REFRAMEWORK_PD_DOWNLOADS = "https://github.com/TheRazerMD/REFramework/releases/download/"

# Which per-game asset each compatibility-list entry needs, by the entry's
# normalised key. Curated rather than guessed: the asset names are game codes
# ("RE2", "DMC5") that no amount of matching gets to from "Resident Evil 2
# (2019)", and installing the wrong game's REFramework build is a crash on
# launch. A game not in here reports that it could not be fetched and links the
# release page — it never falls back to a near-enough asset.
REFRAMEWORK_PD_ASSETS = {
    "devilmaycry5": "DMC5.zip",
    "dragonsdogmaii": "DD2.zip",
    "monsterhunterrise": "MHRISE.zip",
    "monsterhunterstories3twistedreflection": "MHSTORIES3.zip",
    "monsterhunterwilds": "MHWILDS.zip",
    "pragmata": "PRAGMATA.zip",
    "residentevil22019": "RE2.zip",
    "residentevil32020": "RE3.zip",
    "residentevil42023": "RE4.zip",
    "residentevil7biohazard": "RE7.zip",
    "residentevil8village": "RE8.zip",
    "residentevil9requiem": "RE9.zip",
}

# PureDark's UpscalerBasePlugin, which the pd-upscaler entries need alongside
# REFramework. It may not be redistributed, and it is on Nexus Mods behind a
# login, so this plugin neither ships nor downloads it: the user downloads it
# and leaves PDPerfPlugin.dll in their Downloads folder (any subfolder), where
# it is picked up, kept in the plugin's data folder and installed with
# REFramework. A copy already next to the executable counts as well.
REFRAMEWORK_PD_PLUGIN = "PDPerfPlugin.dll"
REFRAMEWORK_PD_PLUGIN_NAME = "UpscalerBasePlugin 1.1.2"
# The 1.1.2 build (1.2.0 "doesn't load the back-end properly", per every
# pd-upscaler entry on the wiki). It has no version resource or signature to
# check, so these bytes are what is recognised; another build is still used,
# with a warning that it is not the one the wiki names.
REFRAMEWORK_PD_PLUGIN_SHA256 = (
    "2e3b10d46a587af3294ff1d02244ea410441befd1f8eaff329ff3f968d2d9a7f"
)
# Where the user leaves the downloaded file, relative to the home folder, and
# how deep into it to look.
REFRAMEWORK_PD_PLUGIN_DROP_DIR = "Downloads"
REFRAMEWORK_PD_PLUGIN_DROP_DEPTH = 3
# Where OptiScaler v10 moved libxess.dll from, and where PDPerfPlugin's
# TemporalUpscaler still looks for it: the game root, next to PDPerfPlugin.dll.
# The wiki's pd-upscaler entries: "copy pasting the libxess.dll to the root ...
# is enough to make it work again."
REFRAMEWORK_PD_ROOT_LIBS = ["libxess.dll"]
# A pd-upscaler build the wiki pins rather than the newest release: "currently
# newer versions of REF PD are broken in DMC5, so use this last working one".
# A GitHub attachment, so GitHub names no digest - the bytes are pinned here.
REFRAMEWORK_PD_PINNED = {
    "DMC5.zip": {
        "url": "https://github.com/user-attachments/files/26169274/DMC5_working.zip",
        "sha256": "8f258480f390a3d063731805c00f58f0246be35580e600747f3c00d917ec225c",
        "tag": "DMC5_working (wiki)",
    },
}
REFRAMEWORK_PD_PLUGIN_URL = "https://www.nexusmods.com/site/mods/502"

# The filenames OptiScaler may be installed under. Order matters: it is the
# order setup_linux.sh presents and the order we probe for existing installs.
PROXY_FILENAMES = [
    "dxgi.dll",
    "winmm.dll",
    "version.dll",
    "dbghelp.dll",
    "d3d12.dll",
    "wininet.dll",
    "winhttp.dll",
    "OptiScaler.asi",
]
DEFAULT_PROXY = "dxgi.dll"

# What a release puts next to the proxy dll, as whole folders. Their contents
# change from one nightly to the next, so they are copied as they come rather
# than file by file from a list that would go stale.
PAYLOAD_DIRS = [OPTI_DIR, "Licenses"]

# Where OptiScaler looks for .asi plugins: Plugins.Path defaults to
# "<OptiDllPath>/plugins". OptiPatcher goes here.
PLUGIN_SUBDIR = f"{OPTI_DIR}/plugins"

# Extra files OptiScaler or its helpers create at runtime; removed on uninstall.
RUNTIME_ARTIFACTS = [
    "OptiScaler.log",
    "fakenvapi.log",
    "dlssg_to_fsr3.log",
    "nvngx.ini",
]

# Directories that never contain a game's shipping executable.
EXE_DIR_BLACKLIST = {
    "engine",
    "_commonredist",
    "commonredist",
    "directx",
    "dotnet",
    "vcredist",
    "redist",
    "installers",
    "support",
    "tools",
    "dxsetup",
}

# Launcher executables that are not the real render target.
EXE_NAME_BLACKLIST = {
    "unitycrashhandler64.exe",
    "unitycrashhandler32.exe",
    "crashreportclient.exe",
    "crashhandler.exe",
    "uninstall.exe",
    "vcredist_x64.exe",
    "vcredist_x86.exe",
    "dxsetup.exe",
    "eossdk-win64-shipping.exe",
    "epicwebhelper.exe",
    "activationui.exe",
    "touchup.exe",
    "notification_helper.exe",
}

# The FidelityFX SDK upscaler inside the release. Its file version is the FSR
# version OptiScaler's overlay reports for the FFX backend, so the game page
# shows it. FSR 4 arrived with the 4.0.2 build (FFX SDK 2.0).
FFX_UPSCALER_DLL = f"{OPTI_DIR}/amd_fidelityfx_upscaler_dx12.dll"
FSR4_MIN_SDK_VERSION = (4, 0, 2, 0)


WIKI_RAW_BASE = "https://raw.githubusercontent.com/wiki/optiscaler/OptiScaler"
WIKI_HTML_BASE = "https://github.com/optiscaler/OptiScaler/wiki"
COMPAT_LIST_PAGE = "Compatibility-List.md"
COMPAT_CACHE_TTL = 24 * 60 * 60  # seconds

STEAM_ROOTS = [
    ".steam/steam",
    ".local/share/Steam",
    ".steam/root",
    ".var/app/com.valvesoftware.Steam/data/Steam",
]
