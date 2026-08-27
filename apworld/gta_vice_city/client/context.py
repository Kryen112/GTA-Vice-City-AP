"""The Archipelago-facing half of the bridge client.

Subclasses CommonContext to speak the real AP protocol against a hosted seed,
and hosts the AsiBridge that the GTA: Vice City mod connects to. It bridges the
two: AP received-items and checked-locations resync down to the mod, and mod
check, goal and progress events up to AP. DeathLink crosses it in both
directions, gated here rather than in the mod, since the option is slot_data.
The protocol and framing live in bridge.py and protocol.py, which are tested
headless; this module is the live wiring, verified against a real server and
game.

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
from NetUtils import ClientStatus, NetworkItem

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

    def _cmd_deathlink(self, state: str = "") -> None:
        """Turn DeathLink on or off for this session, whatever the seed rolled.
        Usage: /deathlink [on | off | seed]. Bare flips it, and 'seed' hands it
        back to the seed's own option."""
        wanted = state.strip().lower()
        if wanted in ("on", "true", "1"):
            self.ctx.death_link_override = True
        elif wanted in ("off", "false", "0"):
            self.ctx.death_link_override = False
        elif wanted == "seed":
            self.ctx.death_link_override = None
        elif not wanted:
            self.ctx.death_link_override = not self.ctx.death_link_enabled
        else:
            self.output("Usage: /deathlink [on | off | seed]")
            return
        self.ctx.refresh_death_link()
        source = ("the seed's own option" if self.ctx.death_link_override is None
                  else "your override for this session")
        self.output(f"DeathLink is {'on' if self.ctx.death_link_enabled else 'off'} "
                    f"({source}).")

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
        # CommonContext keeps `tags` as a CLASS attribute, so update_death_link
        # would otherwise add DeathLink to the set every context in this process
        # shares. An instance copy keeps this session's tags this session's.
        self.tags = set(self.tags)
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
        # Whether DeathLink is on, and the two answers it is worked out from: the
        # seed's own option, from slot_data on Connected, and a /deathlink the
        # player asked for, which wins while it is set so a reconnect re-reading
        # slot_data cannot undo it. None means follow the seed.
        #
        # This is the gate for both directions: the mod reports every wasted state
        # and obeys every kill it is sent, because it has no copy of the option
        # and a save's own state must never be what decides.
        self.death_link_enabled = False
        self.death_link_from_seed = False
        self.death_link_override: bool | None = None
        # Client-side goal detection, configured from slot_data on Connected.
        # hidden_packages counts received copies of the macguffin; final_mission
        # watches for the finale location being checked; hundred_percent waits
        # until no location is missing.
        self.slot_goal: str | None = None
        # Locations outside the 100 percent goal, from slot_data on connect. A
        # seed generated before that field sends none, which is the old
        # behaviour of counting every location.
        self.goal_uncounted_locations: set[int] = set()
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
            on_applied=self.on_bridge_applied,
            on_progress=self.on_bridge_progress,
            on_death=self.on_bridge_death,
            on_connected=self.on_bridge_connected,
            logger=logger,
        )

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        if not self.auth:
            await self.get_username()
        await self.send_connect()

    def make_gui(self) -> type:
        """Name the client window after the game. kvui builds the rest of the
        title around base_title, appending the Archipelago version and the
        server the client is connected to."""
        from kvui import GameManager

        class GTAViceCityManager(GameManager):
            base_title = "Archipelago GTA Vice City Client"

        return GTAViceCityManager

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
            # The tag has to be added AFTER the Connect, because the option
            # arrives in the reply to it: send_connect carries whatever tags are
            # set at the time, so a slot with DeathLink on is tagged by the
            # ConnectUpdate update_death_link sends here, one frame later.
            self.death_link_from_seed = bool(slot_data.get("death_link", False))
            self.refresh_death_link()
            self.slot_goal = slot_data.get("goal")
            self.goal_uncounted_locations = set(
                slot_data.get("goal_uncounted_locations", []))
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
        # Turn each item movement OUT of this slot into an in-game toast, so
        # completing a check shows what it sent. Nothing this slot RECEIVES is
        # toasted here: an item arrives on the server's clock and lands in game on
        # the mod's grant pacer, which is minutes behind it on a slot holding
        # everything at once, so the row belongs to the landing and the mod says
        # when that happens. on_bridge_applied is the other half.
        if args.get("type") != "ItemSend" or self.is_uninteresting_item_send(args):
            return
        if self.slot_concerns_self(args["receiving"]):
            return
        segments = self._item_toast_segments(args["item"], args["receiving"])
        if segments:
            self._schedule(self._send_toast(segments))

    def _item_color(self, flags: int, own_item_name: str | None) -> str:
        """The colour an item's name draws in, from its classification flags.

        Archipelago's own priority, from NetUtils.py's `_handle_item_name`:
        progression, then useful, then trap, then filler. Deliberately not the
        trap-first order some worlds use, because a colour that disagrees with the
        client window and the tracker is worse than an emphasis that is slightly
        wrong.

        `own_item_name` is set only for an item WE receive, and recovers the class
        of a cheat-sent one: `/send` and `!getitem` build a NetworkItem whose
        flags default to 0, so every one of our own items would otherwise read as
        filler. ItemClassification shares the network flag bits, so the looked-up
        classification feeds the same test. An item we merely route onward keeps
        relying on flags, since this table is only ever ours.
        """
        # Imported here rather than at module scope, the way the strand rows reach
        # data: items pulls in BaseClasses, and the client should not need the
        # whole world imported to open a socket.
        from .. import items
        if not flags & 0b111 and own_item_name in items.ITEM_CLASSIFICATIONS:
            flags = int(items.ITEM_CLASSIFICATIONS[own_item_name])
        if flags & 0b001:
            return protocol.TOAST_PROGRESSION
        if flags & 0b010:
            return protocol.TOAST_USEFUL
        if flags & 0b100:
            return protocol.TOAST_TRAP
        return protocol.TOAST_FILLER

    def _item_toast_segments(self, item: NetworkItem,
                             receiving: int) -> list[tuple[str, str]] | None:
        """One item movement as the coloured segments the in-game stack draws.

        Takes the movement's two halves rather than a print_json packet, because
        both toast paths compose through here: a send is read off the packet the
        server printed, and a landing is read off the received-items list at the
        index the mod reports, where no packet exists.

        Modelled on the Harry Potter 2 world's own toasts, which is the closest
        prior art in the multiworld, with one deliberate difference: it names our
        slot and this says "You". The word still draws in the own-slot magenta, so
        the role survives the second-person wording, and a single-player game
        addressing its player reads better than one addressing a slot name.

        The whole movement is ONE line, location included: two lines cost twice the
        band and, drawn one under the other, a location read as though it belonged
        to the row below it. A movement with no location is a cheat-sent item, and
        then there is nothing to name.
        """
        item_name = self.item_names.lookup_in_slot(item.item, receiving)
        found_it = self.slot_concerns_self(item.player)
        got_it = self.slot_concerns_self(receiving)
        # "You" carries the colour Archipelago gives a player their own name in, so
        # the second-person wording keeps the role rather than dropping it.
        you = ("You", protocol.TOAST_OWN_SLOT)
        item_segment = (item_name,
                        self._item_color(item.flags, item_name if got_it else None))
        if found_it and got_it:
            segments = [you, (" found your ", protocol.TOAST_CONNECTIVE),
                        item_segment]
        elif found_it:
            segments = [
                you, (" sent ", protocol.TOAST_CONNECTIVE), item_segment,
                (" to ", protocol.TOAST_CONNECTIVE),
                (self._player_name(receiving), protocol.TOAST_OTHER_SLOT),
            ]
        elif got_it:
            segments = [
                you, (" received ", protocol.TOAST_CONNECTIVE),
                item_segment, (" from ", protocol.TOAST_CONNECTIVE),
                (self._player_name(item.player), protocol.TOAST_OTHER_SLOT),
            ]
        else:
            return None
        # The location is the finder's, so it is looked up in the finder's slot.
        location = ""
        if item.location > 0:
            location = self.location_names.lookup_in_slot(item.location, item.player) or ""
        if location:
            segments += [(" (", protocol.TOAST_CONNECTIVE),
                         (location, protocol.TOAST_LOCATION),
                         (")", protocol.TOAST_CONNECTIVE)]
        return segments

    def _player_name(self, slot: int) -> str:
        return self.player_names.get(slot, str(slot))

    async def on_bridge_applied(self, index: int) -> None:
        """One received item has landed in game, so the player gets its row now.

        This is the whole reason the row is not posted when the item arrives. The
        mod hands grants over at a paced rate, one every 250 ms and sixteen to any
        five seconds, so a release the server delivers in one packet takes the game
        the better part of a minute to actually apply. A row posted on arrival names an
        ability the player cannot use yet and is long gone by the time they can.

        The mod reports the position in the list this client sent it, which is the
        position in items_received, so the row is composed from that entry rather
        than from a print_json packet: the packet may never have existed at all,
        since Archipelago replays ReceivedItems on connect but never replays
        PrintJSON, which is why items that arrived while the game was closed used
        to reach the player in silence.
        """
        if self.slot is None:
            return
        if index < 0 or index >= len(self.items_received):
            # The mod's list came from this client, so a report past its end means
            # the two have diverged: a reconnect rebuilt items_received while a
            # report from the session before it was still in flight. The resync
            # realigns the index space, but the mod has already marked that index
            # reported and only a game boundary clears that, so this row is gone
            # rather than replayed. Dropped anyway: a wrong row naming whatever
            # item happens to sit at that index is worse than no row.
            logger.debug("dropping an applied report for unknown index %d", index)
            return
        segments = self._item_toast_segments(self.items_received[index], self.slot)
        if segments:
            await self._send_toast(segments)

    async def _send_toast(self, segments: list[tuple[str, str]]) -> None:
        if self.bridge.connected:
            await self.bridge.send_toast(segments)

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
            # The same count the goal uses, so the page cannot report checks left
            # that the goal is not waiting for.
            outstanding = set(self.missing_locations) - self.goal_uncounted_locations
            checked = len(self.checked_locations)
            rows.append(["Checks left", str(len(outstanding)),
                         not outstanding and checked > 0])
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

    def refresh_death_link(self) -> None:
        """Work out whether DeathLink is on and tell the server. Called on every
        Connected and on /deathlink, so the tag always says what this session
        actually does."""
        self.death_link_enabled = (self.death_link_from_seed
                                   if self.death_link_override is None
                                   else self.death_link_override)
        self._schedule(self.update_death_link(self.death_link_enabled))

    def on_deathlink(self, data: dict) -> None:
        """A linked player died, so Tommy dies too.

        Not queued for a game that is not there. A death happens to a player who
        is playing, so one that arrives with no mod connected is stale by the
        time a game could act on it, unlike a location, which is a permanent fact
        about the slot and is replayed until it lands. The mod defers it through
        a cutscene and drops it if Tommy is already dying, which is the only
        deferral either side does.
        """
        super().on_deathlink(data)
        if not self.death_link_enabled:
            # The server routes a bounce only to a tagged client, so the option
            # being off here means the tag outlived it, which nothing else covers.
            return
        if not self.bridge.connected:
            logger.info("DeathLink: no game is connected, so the death is dropped.")
            return
        self._schedule(self._deliver_death(str(data.get("source") or "another world")))

    async def _deliver_death(self, source: str) -> None:
        # The toast goes first, so the line naming who killed Tommy is on screen
        # before the frame that kills him rather than after the respawn.
        await self.bridge.send_toast([
            ("DeathLink", protocol.TOAST_TRAP),
            (" from ", protocol.TOAST_CONNECTIVE),
            (source, protocol.TOAST_OTHER_SLOT),
        ])
        await self.bridge.send_death_link(source)

    async def on_bridge_death(self) -> None:
        """Tommy was wasted in game, so every linked slot dies with him.

        The mod reports every wasted state and the option is read here, so a seed
        with DeathLink off drops the report. Nothing else here suppresses one: the
        mod never reports a death it caused itself, which is what keeps two linked
        slots from killing each other forever, so a window on this side could only
        swallow a real death.
        """
        if not self.death_link_enabled or self.slot is None:
            return
        await self.send_death(f"{self._player_name(self.slot)} was wasted in Vice City.")

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
            # Every location the GAME's own percentage counts, checked. Classes
            # the stat never counted sit outside this goal, so waiting on them
            # would hold it for checks the seed does not need: with the ambient
            # pickups on that is 110, and one that cannot be collected would hold
            # the goal forever.
            outstanding = set(self.missing_locations) - self.goal_uncounted_locations
            return bool(self.checked_locations) and not outstanding
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
        # A failed install stops the launch. Starting the game anyway would run
        # it on whatever script is in the folder, which is a game that sends no
        # checks and takes no items, and the refusal that explains why would be
        # a line above a window the player is already looking away from.
        installed = True
        if self._auto_install_mod_enabled():
            installed = self.install_mod(announce_current=False)
        if installed and not self.game_launched and self._auto_launch_enabled():
            self.launch_game()

    def install_mod(self, announce_current: bool = True) -> bool:
        """Puts the mod in the game folder. True when it is there afterwards.

        The answer gates the game launch: a game started on a script the mod
        never patched sends no checks and reads to the player as a mod that does
        not work, which is a worse thing to be handed than the refusal.
        """
        from .. import installer
        if not self.install_dir:
            logger.warning("No install folder set. Use /setfolder first.")
            return False
        try:
            # Check first, so a current mod (or an apworld with no payload) is a
            # silent no-op and never warns about a running game needlessly.
            if installer.mod_is_current(self.install_dir):
                if announce_current:
                    logger.info("The mod is already up to date.")
                return True
            if self.game_running():
                logger.warning("Close the game before installing the mod.")
                return False
            for line in installer.deploy(self.install_dir):
                logger.info(line)
        except installer.InstallRefused as refusal:
            # The refusal carries the whole message: what was found and what to
            # do about it. Logged as it stands, since rewording it here would be
            # a second place saying the same thing differently.
            logger.error(str(refusal))
            return False
        except Exception as error:
            logger.error(f"Could not install the mod ({error}).")
            return False
        return True

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
        # Asked here as well as at install time, because the two are reachable
        # apart: with auto_install_mod off, and on /play, nothing installs and
        # the build would go unexamined. Launching a game the mod cannot attach
        # to is the silent failure the check exists to end, whichever way the
        # launch was asked for.
        from .. import installer
        try:
            installer.require_supported_game_build(self.install_dir)
        except installer.GameBuildRefused as refusal:
            logger.error(str(refusal))
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
