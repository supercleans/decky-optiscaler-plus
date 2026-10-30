"""Decky Upscaler Manager — manage OptiScaler per game from the Steam Deck UI."""

import os
import sys

import decky

sys.path.append(os.path.join(os.path.dirname(__file__), "py_modules"))

from optiscaler.service import OptiScalerService  # noqa: E402


class Plugin:
    service: OptiScalerService = None

    async def _main(self):
        decky.logger.info("Decky Upscaler Manager starting")
        self.service = OptiScalerService(
            plugin_dir=decky.DECKY_PLUGIN_DIR,
            settings_dir=decky.DECKY_PLUGIN_SETTINGS_DIR,
            runtime_dir=decky.DECKY_PLUGIN_RUNTIME_DIR,
            home=decky.HOME,
            logger=decky.logger,
        )
        decky.logger.info("payload status: %s", self.service.payload.status())
        # Start the compatibility list refreshing now rather than when a game
        # is first opened: it is served from cache either way, so the only
        # thing waiting costs is how out of date the first answer is.
        self.service.prime_wiki()

    async def _unload(self):
        decky.logger.info("Decky Upscaler Manager unloading")
        # An upload page must not outlive the plugin that opened it, nor a
        # build the plugin that started it.
        await self.service.stop_pd_upload()
        await self.service.cancel_hlx_dlss_build()

    async def _uninstall(self):
        decky.logger.info("Decky Upscaler Manager uninstalled")

    # -- status ----------------------------------------------------------
    async def get_status(self) -> dict:
        return await self.service.get_status()

    # -- libraries -------------------------------------------------------
    async def list_libraries(self) -> list:
        return await self.service.list_libraries()

    async def add_custom_library(self, path: str, name: str = None) -> dict:
        return await self.service.add_custom_library(path, name)

    async def remove_custom_library(self, path: str) -> dict:
        return await self.service.remove_custom_library(path)

    async def browse(self, path: str = None) -> dict:
        return await self.service.browse(path)

    # -- games -----------------------------------------------------------
    async def list_all_games(self) -> list:
        return await self.service.list_all_games()

    async def list_games(self, library_path: str, source: str = "steam") -> list:
        return await self.service.list_games(library_path, source)

    async def assess_games(self, games: list, force: bool = False) -> dict:
        return await self.service.assess_games(games, force)

    async def get_game(self, game_path: str, name: str = None) -> dict:
        return await self.service.get_game(game_path, name)

    async def find_running_game(self, appid: str, shortcut: dict = None) -> dict:
        return await self.service.find_running_game(appid, shortcut)

    async def apply_fsr4_preset(self, target_dir: str) -> dict:
        return await self.service.apply_fsr4_preset(target_dir)

    async def get_launch_options(self, appid: str) -> dict:
        return await self.service.get_launch_options(appid)

    async def record_launch_options(self, target_dir: str, options: str = None,
                                    appid: str = None) -> dict:
        return await self.service.record_launch_options(target_dir, options, appid)

    async def get_pref(self, key: str, default=None) -> dict:
        return await self.service.get_pref(key, default)

    async def set_pref(self, key: str, value=None) -> dict:
        return await self.service.set_pref(key, value)

    async def set_game_target(self, game_path: str, target_dir: str) -> dict:
        return await self.service.set_game_target(game_path, target_dir)

    # -- wiki ------------------------------------------------------------
    async def get_recommendation(self, name: str, extra_names: list = None,
                                 force: bool = False, game_path: str = None) -> dict:
        return await self.service.get_recommendation(name, extra_names, force, game_path)

    async def search_wiki(self, query: str, limit: int = 30) -> dict:
        return await self.service.search_wiki(query, limit)

    async def set_wiki_entry(self, game_path: str, entry_name: str) -> dict:
        return await self.service.set_wiki_entry(game_path, entry_name)

    async def verify_install(self, target_dir: str) -> dict:
        return await self.service.verify_install(target_dir)

    async def refresh_wiki(self) -> dict:
        return await self.service.refresh_wiki()

    async def wiki_status(self, force: bool = False) -> dict:
        return await self.service.wiki_status(force)

    # -- automatic set-up ------------------------------------------------
    async def get_auto_plan(self, name: str, extra_names: list = None,
                            force: bool = False, game_path: str = None) -> dict:
        return await self.service.get_auto_plan(name, extra_names, force, game_path)

    async def set_auto_mode(self, game_path: str, enabled: bool) -> dict:
        return await self.service.set_auto_mode(game_path, enabled)

    async def auto_install(self, target_dir: str, game_path: str = None,
                           name: str = None, extra_names: list = None,
                           optipatcher: bool = None, upscaler: str = None) -> dict:
        return await self.service.auto_install(target_dir, game_path, name, extra_names,
                                               optipatcher, upscaler)

    async def apply_auto_settings(self, target_dir: str, game_path: str = None,
                                  name: str = None, extra_names: list = None) -> dict:
        return await self.service.apply_auto_settings(target_dir, game_path, name, extra_names)

    # -- install ---------------------------------------------------------
    async def install(self, target_dir: str, filename: str = "dxgi.dll",
                      preserve_ini: bool = True, optipatcher: bool = False,
                      upscaler: str = None) -> dict:
        return await self.service.install(target_dir, filename, preserve_ini, optipatcher,
                                          None, upscaler)

    async def get_helixsr_status(self) -> dict:
        return await self.service.get_helixsr_status()

    # -- the plugin's own downloads ----------------------------------------
    async def get_components(self) -> dict:
        return await self.service.get_components()

    async def check_updates(self, force: bool = False) -> dict:
        return await self.service.check_updates(force)

    async def start_setup(self, build_hlx_dlss: bool = False, install_lsfgvk: bool = False) -> dict:
        """Download everything; build HLX DLSS and install lsfg-vk when the user asked."""
        return await self.service.start_setup(build_hlx_dlss, install_lsfgvk)

    async def update_component(self, channel: str) -> dict:
        return await self.service.update_component(channel)

    async def remove_downloads(self) -> dict:
        return await self.service.remove_downloads()

    # -- frame generation (lsfg-vk) ----------------------------------------
    async def get_frame_generation(self, appid: str) -> dict:
        return await self.service.get_frame_generation(appid)

    async def set_frame_generation(self, appid: str, name: str, settings: dict = None) -> dict:
        return await self.service.set_frame_generation(appid, name, settings)

    async def release_lsfg_wrapper(self, appid: str) -> dict:
        return await self.service.release_lsfg_wrapper(appid)

    async def build_hlx_dlss(self) -> dict:
        """Build HLX DLSS with HelixSR's setup; the user agreed to NVIDIA's licence."""
        return await self.service.build_hlx_dlss()

    async def get_hlx_dlss_build(self) -> dict:
        return await self.service.get_hlx_dlss_build()

    async def cancel_hlx_dlss_build(self) -> dict:
        return await self.service.cancel_hlx_dlss_build()

    async def get_reframework_status(self, target_dir: str, game_path: str = None,
                                     name: str = None, extra_names: list = None) -> dict:
        return await self.service.get_reframework_status(
            target_dir, game_path, name, extra_names)

    async def install_reframework(self, target_dir: str, game_path: str = None,
                                  name: str = None, extra_names: list = None) -> dict:
        return await self.service.install_reframework(
            target_dir, game_path, name, extra_names)

    async def remove_reframework(self, target_dir: str) -> dict:
        return await self.service.remove_reframework(target_dir)

    async def get_pd_plugin_status(self) -> dict:
        return await self.service.get_pd_plugin_status()

    async def install_pd_plugin(self, target_dir: str) -> dict:
        return await self.service.install_pd_plugin(target_dir)

    async def import_pd_plugin(self, path: str) -> dict:
        return await self.service.import_pd_plugin(path)

    async def start_pd_upload(self) -> dict:
        return await self.service.start_pd_upload()

    async def get_pd_upload_status(self) -> dict:
        return await self.service.get_pd_upload_status()

    async def stop_pd_upload(self) -> dict:
        return await self.service.stop_pd_upload()

    async def get_optipatcher_status(self, target_dir: str) -> dict:
        return await self.service.get_optipatcher_status(target_dir)

    async def install_optipatcher(self, target_dir: str, enabled: bool = True) -> dict:
        return await self.service.install_optipatcher(target_dir, enabled)

    async def uninstall(self, target_dir: str, remove_ini: bool = True) -> dict:
        return await self.service.uninstall(target_dir, remove_ini)

    # -- configuration ---------------------------------------------------
    async def read_config(self, target_dir: str) -> dict:
        return await self.service.read_config(target_dir)

    async def write_config(self, target_dir: str, changes: list) -> dict:
        return await self.service.write_config(target_dir, changes)

    async def reset_config(self, target_dir: str) -> dict:
        return await self.service.reset_config(target_dir)

    # -- monitoring ------------------------------------------------------
    async def check_plugin_update(self, force: bool = False) -> dict:
        return await self.service.check_plugin_update(force)

    async def update_installed_games(self) -> dict:
        return await self.service.update_installed_games()

    async def get_channel_versions(self, channel: str) -> dict:
        return await self.service.get_channel_versions(channel)

    async def set_channel_version(self, channel: str, tag: str = None) -> dict:
        return await self.service.set_channel_version(channel, tag)

    async def get_dropin(self, game_path: str) -> dict:
        return await self.service.get_dropin(game_path)

    async def install_dropin(self, game_path: str, upscaler: str = "fsr412l-lossy") -> dict:
        return await self.service.install_dropin(game_path, upscaler)

    async def remove_dropin(self, game_path: str) -> dict:
        return await self.service.remove_dropin(game_path)

    async def get_monitor(self, target_dir: str) -> dict:
        return await self.service.get_monitor(target_dir)

    async def clear_log(self, target_dir: str) -> dict:
        return await self.service.clear_log(target_dir)

    async def set_logging(self, target_dir: str, enabled: bool) -> dict:
        return await self.service.set_logging(target_dir, enabled)
