# Steam Deck: FSR 4 Lite

From the OptiScaler nightly of 2026-10-29, FSR 4 on the Steam Deck needs no
extra files and no FSR 4 settings. The FidelityFX SDK 2.4 upscaler the nightly
ships (FSR 4.1.2) carries the **INT8 Lite** model itself, and OptiScaler
identifies the Deck's Van Gogh APU as an INT8 Lite GPU on its own. The plugin
only points OptiScaler's upscaler backend at it.

## Where the files come from

**OptiScaler** is not bundled. The first install downloads the newest build from
[OptiScaler-nightly](https://github.com/optiscaler/OptiScaler-nightly/releases),
checks it against the SHA-256 the release names (read over a verified TLS
connection), and every game shares that copy. The channel is asked again after
six hours, or when **Settings → Check for a newer nightly** is pressed; a newer
build reaches a game when you install it again. Offline, the last download is
used. The very first install needs an internet connection.

**Settings → 다운로드 버전** can pin one build instead of the newest. The list
starts at the build that was newest when the plugin release was made.

FSR 4 comes from the release's own `OptiScaler/amd_fidelityfx_upscaler_dx12.dll`
(and `_vk.dll`). AMD's driver FidelityFX libraries (`amdxcffx64.dll`,
`amdvkffx64.dll`), which earlier nightlies needed for the INT8 Lite model, are
neither shipped nor installed.

## Settings

Every install writes this preset into `OptiScaler.ini`, including over an ini
kept from an earlier install:

```ini
[Upscalers]
Dx12Upscaler=ffx          ; FSR 3.X/4 FidelityFX backend on DX12
Dx11Upscaler=ffx_12       ; same backend through DX11on12 (default: FSR 2.2)
VulkanUpscaler=ffx_12     ; same backend through VKon12 (default: FSR 2.2)

[Plugins]
LoadAsiPlugins=true       ; load OptiScaler/plugins/*.asi (OptiPatcher)
```

`Dx12Upscaler=ffx` is what OptiScaler picks by itself on a GPU it gives FSR 4
to; it is written so a game switched from HLX DLSS or a cyboman build comes
back to it. The `[FSR]` keys are left at their defaults: `Fsr4GpuSupport`
(the GPU's own FSR 4 support, INT8 Lite on a Deck), `Fsr4Model` (the best model
the GPU supports) and `UpscalerIndex` (0, FSR 4). Wiki-driven automatic
settings never overwrite the preset's keys.

There is no settings screen in the plugin. Everything else — frame generation,
sharpening, the FSR 4 model — is changed in **OptiScaler's own overlay**
(`Insert` by default; on a Deck, bind it to a button in Steam Input). The overlay
applies most changes immediately; **Save Settings** in it writes them to the
ini so they last past the game closing.

If the overlay saved different values over the preset, the game's Setup page
says so, and **Apply FSR 4 Lite again** writes the preset back without
reinstalling anything.

## As a drop-in

In a game that ships FSR 3.1 as a DX12 DLL, FSR 4 Lite goes in without
OptiScaler: the nightly's `amd_fidelityfx_upscaler_dx12.dll` replaces the
game's (with the nightly's loader and frame generator in games with the
all-in-one `amd_fidelityfx_dx12.dll`). This is a test. Without OptiScaler in
front of it, AMD's file does its own GPU check, which may turn the Deck down;
if the game's FSR does not become FSR 4, remove the drop-in.

## Verification

Launch the game and use a supported upscaler input (the Cyberpunk setup tested
here uses XeSS). Turn on OptiScaler's watermark and check for **`FSR4`**. Plain
`FSR3` means FSR 4 was not used — usually `UpscalerIndex`, `Fsr4GpuSupport` or
`Fsr4Model` was changed in the overlay. Set them back to auto, or apply FSR 4
Lite again from Setup and reset them in the overlay.

The watermark identifies the model actually running; Setup only identifies which
files and settings are in the folder.

## Switching model or turning it off

Use OptiScaler's overlay:

- **FSR 4 Lite** — INT8 Lite. What OptiScaler picks on a Deck by itself.
- **FSR 3.X** — the same backend with `UpscalerIndex=1` (FSR 3.1.5). The safe
  choice if FSR 4 misbehaves.

This is experimental support for a GPU AMD does not officially cover. Evaluate
motion/ghosting, image quality and base frame rate in the same scene before and
after. It does not enable FSR 4 frame generation; you can keep FSR 3 frame
generation with FSR 4 upscaling, and should test stability separately.

## Repairing, uninstalling

- Installing again keeps your `OptiScaler.ini`, REFramework and launch
  options, and removes anything the previous install put down that this one
  does not.
- Setup's **Verify** compares the game against the downloaded nightly. A game
  installed from an older nightly reads as outdated, not broken; install it
  again to update it.
- Uninstall restores the game's original backed-up files and removes everything
  the plugin placed.

Avoid modified DLLs in games whose anti-cheat forbids them.
