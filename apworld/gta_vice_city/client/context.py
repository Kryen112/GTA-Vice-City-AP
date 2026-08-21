"""The Archipelago-facing half of the bridge client.

Subclasses CommonContext to speak the real AP protocol against a hosted seed,
and hosts the AsiBridge that the GTA: Vice City mod connects to. It bridges the
two: AP received-items and checked-locations resync down to the mod, and mod
check, goal and progress events up to AP. The protocol and framing live in
bridge.py and protocol.py, which are tested headless; this module is the live
wiring, verified against a real server and game.

Normally launched from the Archipelago Launcher's "GTA Vice City Client"
button. During development, from inside the Archipelago repo:
    python -m worlds.gta_vice_city.client.context --connect localhost:38281 --name Player1

On connect it makes sure the install folder is known, opening a folder picker
the first time and saving the choice to host.yaml, then launches gta-vc.exe
when auto-launch is on. The /play command launches the game on demand and
/setfolder re-picks the install folder.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import warnings
from pathlib import Path

# Silence the setuptools deprecation AP emits when it imports pkg_resources,
# before importing CommonClient so the filter is already in place.
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import Utils
from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    handle_url_arg,
    server_loop,
)
from NetUtils import ClientStatus

from . import protocol, saves
from .bridge import AsiBridge
from .saves import SaveManager

DEFAULT_BRIDGE_PORT = 52300
logger = logging.getLogger("Client")


def looks_like_install(path: Path) -> bool:
    """A folder counts as a GTA Vice City install only if it holds gta-vc.exe.
    An unset UserFolderPath resolves to the Archipelago root, so a non-empty
    value is not enough on its own."""
    return (path / "gta-vc.exe").is_file()


def game_process_running() -> bool:
    """Whether any gta-vc.exe runs, including one the client did not launch."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq gta-vc.exe", "/NH"],
            capture_output=True, text=True, timeout=3, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        # Callers guard destructive save moves, so an unanswerable check fails
        # closed: assume the game is running.
        return True
    return "gta-vc.exe" in result.stdout


class GTAViceCityCommandProcessor(ClientCommandProcessor):
    def _cmd_play(self) -> None:
        """Launch GTA Vice City, or relaunch it after quitting."""
        self.ctx.launch_game()

    def _cmd_setfolder(self, path: str = "") -> None:
        """Choose the GTA Vice City install folder (the one holding gta-vc.exe)
        and save it to host.yaml. With no argument, opens a folder picker."""
        chosen = path if path and Path(path).is_dir() else Utils.open_directory(
            "Select the GTA Vice City install folder (holds gta-vc.exe)",
            suggest=str(self.ctx.install_dir or ""))
        if not chosen:
            self.output("No folder selected.")
            return
        if not looks_like_install(Path(chosen)):
            self.output("That folder has no gta-vc.exe. Pick the GTA Vice City "
                        "install folder.")
            return
        self.ctx.set_install_dir(chosen)
        self.output(f"Install folder set to {self.ctx.install_dir} (saved to host.yaml).")

    def _cmd_restore(self) -> None:
        """Restore your normal saves, undoing Archipelago save isolation. Close
        the game first."""
        self.ctx.restore_saves()

    def _cmd_installmod(self) -> None:
        """Install or update the bundled GTA Vice City mod in the install
        folder. Close the game first."""
        self.ctx.install_mod()

    def _cmd_uninstall(self) -> None:
        """Remove the mod from the install folder, bring the backed-up stock
        main.scm back, and restore your normal saves. Close the game first.
        Connecting to a room sets everything up again while auto_install_mod
        and isolate_saves are on (the defaults)."""
        self.ctx.uninstall_mod()


class GTAViceCityContext(CommonContext):
    game = "Grand Theft Auto Vice City"
    # Receive our own items, starting inventory, and items from other worlds.
    items_handling = 0b111
    command_processor = GTAViceCityCommandProcessor

    def __init__(self, server_address: str | None, password: str | None,
                 bridge_port: int, slot_name: str | None = None) -> None:
        super().__init__(server_address, password)
        if slot_name:
            self.auth = slot_name
        self.bridge_port = bridge_port
        self.game_launched = False
        self.game_process: subprocess.Popen | None = None
        # Set by /restore, so a reconnect does not swap the normal saves back
        # out after the player asked for them.
        self.isolation_suspended = False
        # The install folder, from host.yaml if it already holds gta-vc.exe.
        # A blank setting resolves to the Archipelago root, so it is validated,
        # not just checked for being non-empty.
        self.install_dir: Path | None = None
        folder = self._configured_folder()
        if folder and looks_like_install(Path(folder)):
            self.install_dir = Path(folder)
        # Save isolation works on the GTA Vice City User Files folder, which
        # lives under Documents, apart from the install folder.
        user_files = saves.user_files_directory()
        self.save_manager: SaveManager | None = SaveManager(user_files) if user_files else None
        # The ASI configuration from slot_data: item id -> unlock global, and
        # completion global -> location id. Captured on Connected.
        self.asi_config: dict = {}
        # Client-side goal detection, configured from slot_data on Connected.
        # hidden_packages counts received copies of the macguffin; final_mission
        # watches for the finale location being checked; hundred_percent waits
        # until no location is missing.
        self.slot_goal: str | None = None
        self.hunt_item_id: int | None = None
        self.hunt_required = 0
        self.final_location_id: int | None = None
        # The completion percentage the mod last reported, kept so a Connected
        # can republish it. The mod reports each number once, so a report during
        # a server outage is only recoverable from here.
        self.last_percentage: int | None = None
        # Hold references to fire-and-forget tasks so they are not
        # garbage-collected mid-flight.
        self._background_tasks: set[asyncio.Task] = set()
        self.bridge = AsiBridge(
            "127.0.0.1", bridge_port,
            expected_seed_hash=self.expected_seed_hash,
            on_check=self.on_bridge_check,
            on_goal_reached=self.on_bridge_goal,
            on_progress=self.on_bridge_progress,
            on_connected=self.on_bridge_connected,
            logger=logger,
        )

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        if not self.auth:
            await self.get_username()
        await self.send_connect()

    def expected_seed_hash(self) -> str | None:
        # The identity the mod stamps into its save and presents on connect.
        # Available once AP has sent RoomInfo (seed_name) and Connected (slot).
        if not self.seed_name or self.slot is None:
            return None
        slot_name = self.player_names.get(self.slot, str(self.slot))
        return protocol.seed_hash(self.seed_name, slot_name)

    def on_package(self, cmd: str, args: dict) -> None:
        # Capture the seed name from RoomInfo. CommonContext does not populate
        # it, and the seed hash the mod handshake needs is derived from it.
        if cmd == "RoomInfo":
            self.seed_name = args.get("seed_name")
        # Capture the ASI configuration from slot_data on connect, then make
        # sure the install folder is known and auto-launch the game.
        if cmd == "Connected":
            slot_data = args.get("slot_data") or {}
            self.asi_config = {
                "item_globals": slot_data.get("item_globals", {}),
                "item_effects": slot_data.get("item_effects", {}),
                "config_globals": slot_data.get("config_globals", {}),
                "completion_watch": slot_data.get("completion_watch", {}),
                "package_coords": slot_data.get("package_coords", {}),
                "pickup_layout": slot_data.get("pickup_layout", []),
                "mainland_routes": slot_data.get("mainland_routes", []),
                "content_district_globals": slot_data.get(
                    "content_district_globals", {}),
                "content_districts": slot_data.get("content_districts", []),
                # Not for the ASI: the status page needs to know whether the
                # property strands exist as items at all before it lists them.
                "enable_properties": bool(slot_data.get("enable_properties", False)),
            }
            self.slot_goal = slot_data.get("goal")
            self.final_location_id = slot_data.get("final_location_id")
            if self.slot_goal == "hidden_packages":
                self.hunt_item_id = slot_data.get("hidden_package_item_id")
                self.hunt_required = slot_data.get("hidden_packages_required", 0)
            self._schedule(self.setup_and_launch())
            # Publish the percentage the mod last reported. A report that landed
            # while the server was away went nowhere, and the mod will not repeat
            # itself until the number moves again, so the data store would keep a
            # stale one: a game that reached a hundred through a blip would leave
            # the tracker at ninety-nine for good.
            self._schedule(self._publish_percentage())
        # A new Connected or a ReceivedItems update means the mod's view is
        # stale, so push a fresh resync. The bridge no-ops if the mod is not
        # connected; it also resyncs itself on every mod (re)connect.
        if cmd in ("Connected", "ReceivedItems"):
            self._schedule(self._resync_bridge())
        # A received item (the hunt) or a newly checked location (the finale, or
        # the last check for 100 percent) can complete the goal.
        if cmd in ("Connected", "ReceivedItems", "RoomUpdate"):
            self._maybe_finish_goal()
        # A RoomUpdate is how a checked count moves without any item arriving,
        # which the resync above would not catch on its own.
        if cmd == "RoomUpdate":
            self._schedule(self._send_status())

    def _schedule(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)
        # Turn each item movement that concerns this player into an in-game
        # toast, so completing a check shows what it sent or found.
        if args.get("type") != "ItemSend" or self.is_uninteresting_item_send(args):
            return
        text = self._item_toast_text(args)
        if text:
            self._schedule(self._send_toast(text))

    def _item_toast_text(self, args: dict) -> str | None:
        item = args["item"]
        receiving = args["receiving"]
        item_name = self.item_names.lookup_in_slot(item.item, receiving)
        found_it = self.slot_concerns_self(item.player)
        got_it = self.slot_concerns_self(receiving)
        if found_it and got_it:
            return f"You found your {item_name}"
        if found_it:
            return f"You sent {item_name} to {self.player_names.get(receiving, str(receiving))}"
        if got_it:
            return f"{self.player_names.get(item.player, str(item.player))} found your {item_name}"
        return None

    async def _send_toast(self, text: str) -> None:
        if self.bridge.connected:
            await self.bridge.send_toast(text)

    def _received_item_pairs(self) -> list[tuple[int, int]]:
        return [(index, item.item) for index, item in enumerate(self.items_received)]

    async def _resync_bridge(self) -> None:
        if not self.bridge.connected:
            return
        await self.bridge.send_items(self._received_item_pairs())
        await self.bridge.send_checked(sorted(self.checked_locations))
        await self._send_status()

    async def _send_status(self) -> None:
        """What the pause menu's status page shows and only the client knows: the
        seed's own check total, the goal's progress, and how far each mission
        strand has come. The mod knows which completion globals it watches, not
        which of them this seed turned into locations, nor what its goal asks
        for."""
        if not self.bridge.connected:
            return
        if self.slot is None:
            # No AP connection yet, so there are no counts to send: zeroes would
            # reach the page as counts and read as a seed with nothing in it.
            return
        checked = len(self.checked_locations)
        total = checked + len(self.missing_locations)
        # AP's own view of the slot, not ours: a session that connects to a room
        # already finished has finished_game set with nothing left to evaluate.
        finished = self.finished_game or self._goal_reached()
        await self.bridge.send_status(
            checked, total, len(self.items_received), finished,
            self._goal_rows(), self._strand_rows(), self._finale_warp())

    def _received_name_counts(self) -> dict[str, int]:
        """How many of each item this slot has received, by name. The page shows
        progress toward things counted in items rather than in locations, and the
        names are what the mod has no table for."""
        counts: dict[str, int] = {}
        for item in self.items_received:
            name = self.item_names.lookup_in_slot(item.item, self.slot)
            counts[name] = counts.get(name, 0) + 1
        return counts

    def _goal_rows(self) -> list[list]:
        """The goal's own progress, as the page's rows. One row for what this
        seed's goal asks, plus the count when the goal is one that counts."""
        goal = self.slot_goal or "unknown"
        labels = {"final_mission": "Keep Your Friends Close",
                  "hidden_packages": "Package Fragments",
                  "hundred_percent": "Every check in the seed"}
        rows: list[list] = [["Goal", labels.get(goal, goal), bool(self.finished_game)]]
        if goal == "hidden_packages" and self.hunt_required:
            have = 0
            if self.hunt_item_id is not None:
                have = sum(1 for item in self.items_received
                           if item.item == self.hunt_item_id)
            rows.append(["Fragments", f"{have} of {self.hunt_required}",
                         have >= self.hunt_required])
        elif goal == "hundred_percent":
            checked = len(self.checked_locations)
            rows.append(["Checks left", str(len(self.missing_locations)),
                         not self.missing_locations and checked > 0])
        return rows

    def _strand_rows(self) -> list[list]:
        """How far each giver's strand has come, as one wrapped row per strand.
        The counts are received progressive items; the strand names and how many
        missions each holds come from the world's own tables, which the client can
        read directly rather than carry over the wire."""
        from .. import data
        counts = self._received_name_counts()
        strands = list(data.STORY_GIVERS)
        # The venue strands are property missions, which only exist as items when
        # that check class is on.
        if self.asi_config.get("enable_properties", False):
            strands += list(data.VENUE_STRANDS)
        rows: list[list] = []
        for strand in strands:
            total = data.progressive_item_count(strand)
            if total <= 0:
                continue
            have = min(counts.get(data.progressive_item_name(strand), 0), total)
            rows.append([strand, f"{have} of {total}", have >= total])
        return rows

    async def on_bridge_connected(self, _bridge: AsiBridge) -> None:
        # The mod just connected and was welcomed; give it its configuration
        # then the full state.
        if self.asi_config:
            await self.bridge.send_config(
                self.asi_config.get("item_globals", {}),
                self.asi_config.get("completion_watch", {}),
                self.asi_config.get("item_effects", {}),
                self.asi_config.get("config_globals", {}),
                self.asi_config.get("package_coords", {}),
                self.asi_config.get("pickup_layout", []),
                self.asi_config.get("mainland_routes", []),
                self.asi_config.get("content_district_globals", {}),
                self.asi_config.get("content_districts", []),
            )
        await self._resync_bridge()

    async def on_bridge_check(self, location: int) -> None:
        # Recorded in locations_checked BEFORE the send, and left there whatever
        # the send does. CommonContext replays that set on every Connected, so a
        # location found while the server is unreachable is reconciled on the
        # next connection instead of being lost: send_msgs can fail or the socket
        # can die mid-frame, and the mod cannot find the location again once its
        # completion global is set and a save has folded it into the baseline.
        # LocationChecks is idempotent, so replaying one the server already has
        # costs nothing. The set doubles as the per-location dedupe.
        self.locations_checked.add(location)
        await self.send_msgs([{"cmd": "LocationChecks", "locations": [location]}])

    async def on_bridge_goal(self) -> None:
        await self._finish_goal()

    async def on_bridge_progress(self, percentage: int) -> None:
        # The game's own "Percentage completed" stat. Remembered first and sent
        # second: the mod reports it once per change, so a send that goes nowhere
        # has to be repeatable from here.
        self.last_percentage = percentage
        await self._publish_percentage()

    async def _publish_percentage(self) -> None:
        # Into the AP data store, where the PopTracker pack reads it. The server
        # keeps the value, so a tracker that connects later still sees the last
        # one and the mod never has to repeat itself.
        key = self.percentage_key()
        if key is None or self.last_percentage is None:
            return
        await self.send_msgs([{
            "cmd": "Set", "key": key, "default": 0, "want_reply": False,
            "operations": [{"operation": "replace", "value": self.last_percentage}],
        }])

    def percentage_key(self) -> str | None:
        # The data store key the tracker pack reads. Team and slot are in it the
        # way the server's own read-only keys carry them, so two slots of one
        # multiworld never share a number. None until AP says which slot we are.
        if self.team is None or self.slot is None:
            return None
        return protocol.percentage_key(self.team, self.slot)

    async def _finish_goal(self) -> None:
        if self.finished_game:
            return
        # Mark finished before awaiting the send: a burst of ReceivedItems can
        # schedule this more than once, and the flag set with no await before it
        # keeps the check-and-set atomic so the goal is reported exactly once.
        self.finished_game = True
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    def _maybe_finish_goal(self) -> None:
        if not self.finished_game and self.slot is not None and self._goal_reached():
            self._schedule(self._finish_goal())

    def _finale_warp(self) -> bool:
        """Whether the mod should play the story's ending now.

        The hunt goal alone: collecting the last Package Fragment ends the game,
        so the mod warps into the ending cutscene of Keep Your Friends Close...
        wherever the player is, the way every macguffin hunt ends. The other two
        goals cannot be met before that mission has passed, so they never ask.
        Asked on every status frame rather than announced once, so a reconnect or
        a save loaded later re-arms it; the mod holds on the mission's own passed
        flag, so a game that has seen the ending never plays it twice."""
        return self.slot_goal == "hidden_packages" and self._goal_reached()

    def _goal_reached(self) -> bool:
        if self.slot_goal == "hidden_packages":
            # Enough Package Fragments received, wherever in the multiworld
            # they were found. Both halves have to have arrived: a threshold
            # missing from slot_data falls back to zero, which any count would
            # clear, and the goal now plays the ending as well as reporting
            # itself, so an absent option would end the game at connect.
            if self.hunt_item_id is None or self.hunt_required < 1:
                return False
            received = sum(1 for item in self.items_received if item.item == self.hunt_item_id)
            return received >= self.hunt_required
        if self.slot_goal == "hundred_percent":
            # Every location in the slot checked: nothing left missing.
            return bool(self.checked_locations) and not self.missing_locations
        if self.slot_goal == "final_mission":
            return self.final_location_id in self.checked_locations
        return False

    def _configured_folder(self) -> str:
        from .. import GTAViceCityWorld
        return str(GTAViceCityWorld.settings.install_folder)

    def _auto_launch_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "auto_launch_game", False))

    def _isolate_saves_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "isolate_saves", False))

    def _auto_install_mod_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "auto_install_mod", False))

    async def setup_and_launch(self) -> None:
        """On connect: isolate this seed's saves, make sure an install folder is
        known (picker on first run), install the mod, then auto-launch the game
        if that setting is on."""
        # Isolation moves save files, so it runs on the loop (serialized with
        # other connects) rather than racing in a thread; its one blocking step,
        # the tasklist check, is bounded to a few seconds.
        self._isolate_saves()
        if not self.install_dir:
            if gui_enabled:
                await self.pick_install_dir()
            else:
                logger.warning("No install folder set. Use /setfolder, or set "
                               "gta_vice_city_options -> install_folder in host.yaml.")
        if not self.install_dir:
            return
        if self._auto_install_mod_enabled():
            self.install_mod(announce_current=False)
        if not self.game_launched and self._auto_launch_enabled():
            self.launch_game()

    def install_mod(self, announce_current: bool = True) -> None:
        from .. import installer
        if not self.install_dir:
            logger.warning("No install folder set. Use /setfolder first.")
            return
        try:
            # Check first, so a current mod (or an apworld with no payload) is a
            # silent no-op and never warns about a running game needlessly.
            if installer.mod_is_current(self.install_dir):
                if announce_current:
                    logger.info("The mod is already up to date.")
                return
            if self.game_running():
                logger.warning("Close the game before installing the mod.")
                return
            for line in installer.deploy(self.install_dir):
                logger.info(line)
        except Exception as error:
            logger.error(f"Could not install the mod ({error}).")

    def uninstall_mod(self) -> None:
        """Take the mod back out of the install and bring the normal saves home
        (manual, via /uninstall). The saves come back first, and a failure there
        stops everything, so the mod is never removed while save state is in
        doubt."""
        from .. import installer
        if not self.install_dir:
            logger.warning("No install folder set. Use /setfolder first.")
            return
        if self.game_running():
            logger.warning("Close the game before uninstalling the mod.")
            return
        if self.save_manager and self.save_manager.is_isolated():
            try:
                logger.info(self.save_manager.restore())
            except Exception as error:
                logger.error(f"Could not restore your normal saves ({error}); the "
                             "uninstall stopped before touching the mod. Run "
                             "/uninstall again once that is resolved.")
                return
        try:
            removal_log = installer.remove(self.install_dir)
        except Exception as error:
            logger.error(f"Could not remove the mod ({error}).")
            return
        for line in removal_log:
            logger.info(line)
        if not removal_log:
            logger.info("No mod files found; the install was already stock.")
        if self.save_manager:
            try:
                note = self.save_manager.discard_isolation_state()
            except OSError as error:
                note = f"Could not tidy the save isolation bookkeeping: {error}"
            if note:
                logger.info(note)
        # A later connect is the full opt-in again: unlike /restore, uninstall
        # does not suspend isolation, so the setup runs whole or not at all.
        logger.info("Mod uninstall finished. Connecting to an Archipelago room "
                    "installs the mod and isolates seed saves again while "
                    "auto_install_mod and isolate_saves are on in host.yaml "
                    "(the defaults).")

    def game_running(self) -> bool:
        # The client-launched process is authoritative, but a game the player
        # started themselves counts too: swapping saves under a live game
        # corrupts state.
        if self.game_process is not None and self.game_process.poll() is None:
            return True
        return game_process_running()

    def _isolate_saves(self) -> None:
        """Swap in this seed's own save set, unless disabled. Skipped while the
        game runs, so saves are never swapped under a live game."""
        if not (self.save_manager and self._isolate_saves_enabled()):
            return
        if self.isolation_suspended:
            return
        if not self.seed_name:
            return
        already_on_seed = (
            self.save_manager.is_isolated()
            and self.save_manager.active_seed() == saves.seed_folder_name(self.seed_name))
        if self.game_running() and not already_on_seed:
            logger.warning("The game is running, so save isolation was skipped. Close it "
                           "and reconnect to isolate this seed's saves.")
            return
        try:
            logger.info(self.save_manager.isolate(self.seed_name))
        except Exception as error:
            logger.error(f"Save isolation failed ({error}); using the current saves as-is.")

    def restore_saves(self) -> None:
        if not self.save_manager:
            logger.warning("No GTA Vice City User Files folder found to restore saves in.")
            return
        if self.game_running():
            logger.warning("Close the game before restoring your normal saves.")
            return
        try:
            logger.info(self.save_manager.restore())
            # Do not re-isolate on the next reconnect this session, or the
            # restore would silently swap the normal saves back out.
            self.isolation_suspended = True
        except Exception as error:
            logger.error(f"Could not restore saves ({error}); resolve by hand.")

    async def pick_install_dir(self) -> None:
        """Open a folder picker off the event loop and save the choice."""
        loop = asyncio.get_event_loop()
        chosen = await loop.run_in_executor(
            None, Utils.open_directory,
            "Select the GTA Vice City install folder (holds gta-vc.exe)")
        if not chosen:
            logger.warning("No install folder chosen. Use /setfolder to try again, or "
                           "set gta_vice_city_options -> install_folder in host.yaml.")
            return
        if not looks_like_install(Path(chosen)):
            logger.warning(f"'{chosen}' has no gta-vc.exe, so it is not a GTA Vice City "
                           "install folder. Not saved; use /setfolder to try again.")
            return
        self.set_install_dir(chosen)
        logger.info(f"Install folder set to {self.install_dir} (saved to host.yaml).")

    def set_install_dir(self, path: str) -> None:
        self.install_dir = Path(path)
        self._save_install_folder(str(self.install_dir))

    def _save_install_folder(self, path: str) -> None:
        """Persist the install folder to host.yaml, so the player picks it once."""
        from .. import GTAViceCityWorld
        try:
            import settings as ap_settings
            current = GTAViceCityWorld.settings.install_folder
            GTAViceCityWorld.settings.install_folder = type(current)(path)
            ap_settings.get_settings().save()
        except Exception as error:
            logger.warning(f"Could not save the install folder to host.yaml ({error}); "
                           "set it there yourself to avoid picking it again.")

    def launch_game(self) -> None:
        if not self.install_dir:
            logger.warning("No install folder set. Use /setfolder first.")
            return
        executable = self.install_dir / "gta-vc.exe"
        if not executable.is_file():
            logger.error(f"gta-vc.exe not found at {executable}.")
            return
        try:
            self.game_process = subprocess.Popen([str(executable)], cwd=str(executable.parent))
            self.game_launched = True
            logger.info("Launched GTA Vice City.")
        except OSError as error:
            logger.error("Could not launch GTA Vice City: %s", error)


async def _run(context: GTAViceCityContext) -> None:
    await context.bridge.start()
    logger.info("GTA Vice City bridge listening on 127.0.0.1:%d", context.bridge.port)
    context.server_task = asyncio.create_task(server_loop(context), name="server loop")
    if gui_enabled:
        context.run_gui()
    context.run_cli()
    await context.exit_event.wait()
    await context.bridge.stop()
    await context.shutdown()


def launch(*args: str) -> None:
    async def main() -> None:
        parser = get_base_parser(description="GTA: Vice City Archipelago bridge client.")
        parser.add_argument("--bridge_port", type=int, default=DEFAULT_BRIDGE_PORT,
                            help="Localhost port the GTA Vice City mod connects to.")
        parser.add_argument("--name", default=None, help="Slot name to connect as.")
        parser.add_argument("url", nargs="?", help="Archipelago connection url.")
        parsed = parser.parse_args(args)
        # A WebHost archipelago:// link arrives as the url positional; fold it
        # into connect, name, and password.
        parsed = handle_url_arg(parsed, parser=parser)
        context = GTAViceCityContext(parsed.connect, parsed.password, parsed.bridge_port, parsed.name)
        await _run(context)

    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()


if __name__ == "__main__":
    import sys
    launch(*sys.argv[1:])
