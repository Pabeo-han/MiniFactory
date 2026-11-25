"""Launch MiniFactory with: python main.py"""

import argparse
import json
from tempfile import TemporaryDirectory
from pathlib import Path

import pygame

from simulation import SALES_TARGET, DIRS, GUIDE, ITEMS, STARTER_ORES, STARTER_QUANTITY, STEP, TECHS, TRANSFER_AMOUNTS, TYPES, Factory
from translations import set_language, tr
from tutorial import CHAPTERS, current_chapter
from example_layouts import advanced_sample
from save_game import SaveError, read_save, save_path, write_json, write_save
from interface import Camera, Interface, MAP, SIZE


class Game:
    def __init__(self, store_path: Path | None = None, *, language: str | None = None):
        self.window_size = SIZE
        self.fullscreen = False
        self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.ui = Interface()
        self.camera = Camera()
        self.store_path = store_path if store_path is not None else save_path()
        self.settings_path = self.store_path.with_name("settings.json")
        self.language = language or self.read_language()
        set_language(self.language or "en")
        pygame.display.set_caption(tr("MiniFactory - Iron Works"))
        self.factory = Factory()
        self.menu_factory = self.make_menu_factory()
        self.menu_camera = Camera()
        self.menu_camera.x, self.menu_camera.y, self.menu_camera.zoom = 215, -85, 1.68
        self.running = True
        self.in_menu = True
        self.has_session = False
        self.paused = False
        self.grid = True
        self.tutorial_page = 0
        self.guide_on = True
        self.build_tool = None
        self.direction = 0
        self.inspected_tile = None
        self.inventory_item = "ore"
        self.transfer_amount = "5"
        self.recipe_item = "plate"
        self.drag_tile = None
        self.pan_point = None
        self.demo = False
        self.overlay = None if self.language else "language"
        self.pending = None
        self.modified = False
        self.saved_step = 0
        self.message = ""
        self.fraction = 0.0
        self.menu_fraction = 0.0

    def read_language(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        language = data.get("language") if isinstance(data, dict) else None
        return language if language in ("en", "ko") else None

    def choose_language(self, language):
        self.language = language
        set_language(language)
        pygame.display.set_caption(tr("MiniFactory - Iron Works"))
        self.set_overlay(None)
        self.message = ""
        try:
            write_json(self.settings_path, {"language": language})
        except OSError:
            self.message = tr("Could not save the language preference.")

    @staticmethod
    def make_menu_factory():
        factory = Factory.sample()
        factory.credits = 5000
        for dx, dy in ((0, 6), (10, -2)):
            for (x, y), kind, direction in GUIDE:
                factory.place((x + dx, y + dy), kind, direction)
        for _ in range(135):
            factory.step()
        return factory

    @property
    def animation_fraction(self):
        return min(1, self.fraction / STEP)

    @property
    def dirty(self):
        return self.has_session and not self.demo and (
            self.modified or (bool(self.factory.machines) and self.factory.steps != self.saved_step)
        )

    def toggle_fullscreen(self):
        if self.fullscreen:
            self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        else:
            self.window_size = pygame.display.get_window_size()
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.fullscreen = not self.fullscreen
        self.drag_tile = None
        self.pan_point = None

    def viewport(self):
        ww, hh = self.screen.get_size()
        scale = min(ww / SIZE[0], hh / SIZE[1])
        width, height = max(1, round(SIZE[0] * scale)), max(1, round(SIZE[1] * scale))
        return pygame.Rect((ww - width) // 2, (hh - height) // 2, width, height)

    def logical_point(self, point):
        view = self.viewport()
        if not view.collidepoint(point):
            return -1, -1
        return ((point[0] - view.x) * SIZE[0] // view.width,
                (point[1] - view.y) * SIZE[1] // view.height)

    def open_factory(self, factory, message, *, loaded=False, guide=True, demo=False):
        self.factory = factory
        self.demo = demo
        self.drag_tile = self.pan_point = None
        self.in_menu = False
        self.ui.buttons.clear()
        self.has_session = True
        self.paused = False
        self.camera.reset()
        self.inspected_tile = None
        self.build_tool = None
        self.direction = 0
        self.inventory_item = "ore"
        self.transfer_amount = "5"
        self.recipe_item = "plate"
        self.fraction = 0
        self.guide_on = guide
        self.modified = not loaded and bool(factory.machines)
        self.saved_step = factory.steps
        self.message = message

    def save(self):
        if not self.has_session:
            return False
        if self.demo:
            self.message = tr("Example factories do not overwrite your save.")
            return False
        try:
            write_save(self.store_path, self.factory)
        except OSError:
            self.message = tr("Could not write the save file.")
            return False
        self.modified = False
        self.saved_step = self.factory.steps
        self.message = tr("Factory saved.")
        return True

    def change_session(self, action, *, confirmed=False):
        if action == "load" and not self.store_path.is_file():
            self.message = tr("No saved factory yet.")
            return
        if self.dirty and not confirmed:
            self.overlay, self.pending = "confirm", action
            self.drag_tile = None
            return
        if action == "quit":
            self.running = False
        elif action == "new":
            self.open_factory(Factory(), tr("Mine copper or coal and deliver it to a warehouse."))
        elif action == "example":
            self.open_factory(Factory.sample(), tr("The example line is running. Select a machine to inspect it."), guide=False, demo=True)
        elif action == "advanced":
            self.open_factory(advanced_sample(), tr("Advanced example: four mines feed the circuit line."), guide=False, demo=True)
            self.camera.center_on((12, 9), 0.75)
        elif action == "load":
            try:
                factory = read_save(self.store_path)
            except SaveError as error:
                self.message = str(error)
                return
            except OSError:
                self.message = tr("Could not open the save file.")
                return
            self.open_factory(factory, tr("Factory loaded."), loaded=True)

    def set_overlay(self, overlay):
        self.overlay = overlay
        self.ui.buttons.clear()

    def mark_change(self, message):
        self.message = message
        self.modified = True

    def game_action(self, action):
        if action.startswith("tool:"):
            self.build_tool = action.partition(":")[2]
            self.inspected_tile = None
        elif action == "turn-tool":
            self.direction = (self.direction + 1) % 4
        elif action == "cancel-tool":
            self.build_tool = None
        elif action == "pause-game":
            self.paused = not self.paused
        elif action.startswith("item:"):
            self.inventory_item = action.partition(":")[2]
        elif action.startswith("amount:"):
            self.transfer_amount = action.partition(":")[2]
        elif action.startswith("recipe-guide:"):
            self.recipe_item = action.partition(":")[2]
            self.set_overlay("recipes")
        elif action == "filter" and self.inspected_tile in self.factory.machines:
            if self.factory.machines[self.inspected_tile].kind in ("splitter", "extractor"):
                self.overlay = "filter"
        elif action == "guide":
            self.guide_on = not self.guide_on
        elif action.startswith("first:"):
            item = action.partition(":")[2]
            before = self.factory.starter_shipped
            self.message = self.factory.ship_starter(item)
            self.modified |= before != self.factory.starter_shipped
        elif action == "upgrade":
            machine = self.factory.machines.get(self.inspected_tile)
            before = machine.level if machine else None
            self.message = self.factory.upgrade(self.inspected_tile)
            self.modified |= bool(machine and before != machine.level)
        elif action == "dispatch":
            ready = next((item for item in STARTER_ORES
                          if self.factory.warehouse_stock(item) >= STARTER_QUANTITY), None)
            if not self.factory.starter_complete and ready:
                self.game_action(f"first:{ready}")
            elif self.factory.starter_complete and "ore" not in self.factory.unlocked:
                self.action("research-menu")
            elif not self.factory.starter_complete and self.factory.warehouse_parts < 10:
                self.message = tr("Store ten copper ore or ten coal for your first shipment.")
            else:
                before = self.factory.contract_index
                self.message = self.factory.dispatch()
                self.modified |= before != self.factory.contract_index
        elif action == "dismantle" and self.inspected_tile in self.factory.machines:
            self.mark_change(self.factory.dismantle(self.inspected_tile))
            self.inspected_tile = None
        elif self.inspected_tile in self.factory.machines:
            machine = self.factory.machines[self.inspected_tile]
            if action == "withdraw-all" and machine.kind == "storage" and machine.storage:
                self.mark_change(self.factory.withdraw_all(self.inspected_tile))
            elif action == "reserve" and machine.kind == "extractor":
                before = machine.controlled, machine.reserve
                self.message = self.factory.configure_reserve(self.inspected_tile)
                self.modified |= before != (machine.controlled, machine.reserve)
            elif action == "pause-extractor" and machine.kind == "extractor":
                machine.paused = not machine.paused
                self.modified = True
            elif action == "recipe" and machine.kind in ("furnace", "assembler", "electronics"):
                self.set_overlay("choose-recipe")
            elif action == "rotate" and machine.kind != "storage":
                self.mark_change(self.factory.rotate(self.inspected_tile))
            elif action in ("deposit", "withdraw"):
                before = self.factory.player_inventory[self.inventory_item]
                transfer = self.factory.deposit if action == "deposit" else self.factory.withdraw
                self.message = transfer(self.inspected_tile, self.inventory_item, TRANSFER_AMOUNTS[self.transfer_amount])
                self.modified |= before != self.factory.player_inventory[self.inventory_item]

    def action(self, action):
        if action == "tutorial" and self.overlay in (None, "help"):
            self.tutorial_page = current_chapter(self.factory)
            self.set_overlay("tutorial")
            self.drag_tile = self.pan_point = None
            return
        if self.overlay == "tutorial" and action.startswith("chapter:"):
            self.tutorial_page = max(0, min(len(CHAPTERS)-1, int(action.partition(":")[2])))
            self.ui.buttons.clear()
            return
        if action == "fullscreen":
            self.toggle_fullscreen()
            return
        if self.overlay:
            if self.overlay == "ending":
                if action in ("close", "resume"):
                    self.overlay = None
                elif action == "finish-menu" and self.save():
                    self.overlay = None
                    self.in_menu = True
                self.ui.buttons.clear()
                return
            if self.overlay == "choose-recipe" and action.startswith("apply-recipe:"):
                index = int(action.partition(":")[2])
                machine = self.factory.machines[self.inspected_tile]
                previous = machine.recipe
                self.message = self.factory.switch_recipe(self.inspected_tile, index)
                self.modified |= machine.recipe != previous
                self.set_overlay(None)
            elif action == "research-menu" and self.overlay == "market":
                self.set_overlay("research")
            elif action == "recipes" and self.overlay == "help":
                self.set_overlay("recipes")
            elif self.overlay == "recipes" and action.startswith("recipe-guide:"):
                self.recipe_item = action.partition(":")[2]
            elif self.overlay == "research" and action.startswith("research:"):
                item = action.partition(":")[2]
                before = self.factory.credits
                self.message = self.factory.research(item)
                self.modified |= before != self.factory.credits
            elif self.overlay == "market" and action.startswith("sell:"):
                item, _, units = action.removeprefix("sell:").partition(":")
                before = self.factory.credits
                if item in ITEMS and units in ("1", "5"):
                    self.message = self.factory.sell(item, int(units))
                self.modified |= before != self.factory.credits
            elif self.overlay == "filter" and action.startswith("filter:"):
                item = action.partition(":")[2]
                self.mark_change(self.factory.set_filter(self.inspected_tile, item))
                self.set_overlay(None)
            elif action.startswith("language:") and self.overlay == "language":
                self.choose_language(action.partition(":")[2])
            elif action == "language" and self.overlay == "help":
                self.overlay = "language"
            elif action == "close" and (self.overlay != "language" or self.language):
                self.overlay = self.pending = None
                self.ui.buttons.clear()
            elif action == "grid" and self.overlay == "help":
                self.grid = not self.grid
            elif action in ("confirm", "save_continue") and self.overlay == "confirm":
                if action == "save_continue" and (self.pending == "load" or not self.save()):
                    return
                pending = self.pending
                self.overlay = self.pending = None
                self.change_session(pending, confirmed=True)
            return
        if action in ("quit", "new", "example", "advanced", "load"):
            self.change_session(action)
        elif action == "resume":
            self.in_menu = False
            self.ui.buttons.clear()
        elif action in ("help", "language"):
            self.overlay = action
            self.drag_tile = None
        elif action in ("market", "research-menu") and not self.in_menu:
            self.overlay = "market" if action == "market" else "research"
            self.drag_tile = None
            self.ui.buttons.clear()
        elif action == "save":
            self.save()
        elif not self.in_menu:
            self.game_action(action)

    def keydown(self, key, mods):
        if key == pygame.K_F11:
            self.toggle_fullscreen()
            return
        if key == pygame.K_ESCAPE:
            if self.overlay == "language" and not self.language:
                self.running = False
            elif self.overlay:
                self.action("close")
            elif not self.in_menu and self.build_tool:
                self.build_tool = None
                self.drag_tile = None
            elif not self.in_menu:
                self.in_menu = True
                self.ui.buttons.clear()
                self.drag_tile = None
                self.message = ""
            else:
                self.action("quit")
            return
        if self.overlay:
            if key == pygame.K_m and self.overlay == "market":
                self.action("close")
            if key in (pygame.K_TAB, pygame.K_F1) and self.overlay == "help":
                self.action("close")
            return
        shortcuts = {
            pygame.K_TAB: "help", pygame.K_F1: "help",
            pygame.K_F5: "save", pygame.K_F9: "load",
        }
        if key in shortcuts:
            self.action(shortcuts[key])
        elif not self.in_menu:
            if key == pygame.K_SPACE:
                self.paused = not self.paused
            elif key == pygame.K_HOME:
                self.camera.reset()
            elif key == pygame.K_r:
                if mods & pygame.KMOD_SHIFT:
                    self.action("rotate")
                else:
                    self.direction = (self.direction + 1) % 4
            elif pygame.K_0 <= key <= pygame.K_9:
                self.action(f"tool:{TYPES[(key - pygame.K_1) % 10]}")
            else:
                game_keys = {
                    pygame.K_g: "guide", pygame.K_q: "recipe", pygame.K_f: "deposit",
                    pygame.K_t: "withdraw", pygame.K_RETURN: "dispatch",
                    pygame.K_u: "upgrade", pygame.K_m: "market", pygame.K_y: "research-menu",
                }
                if key in game_keys:
                    self.action(game_keys[key])

    def build(self, tile):
        if not self.build_tool:
            return False
        was_occupied = tile in self.factory.machines
        message = self.factory.place(tile, self.build_tool, self.direction)
        self.message = message
        if was_occupied or tile not in self.factory.machines:
            return False
        self.mark_change(message)
        self.inspected_tile = tile
        return True

    def click(self, point, button):
        action = self.ui.action_at(point) if button == 1 else None
        if action:
            self.action(action)
        elif not self.in_menu and not self.overlay:
            destination = self.ui.minimap_tile(point)
            if destination is not None and button == 1:
                self.camera.center_on(destination, self.camera.zoom)
                return
            if button == 2 and MAP.collidepoint(point):
                self.pan_point = point
                self.drag_tile = None
                return
            tile = self.camera.tile_at(point)
            if tile is None:
                return
            if button == 1 and tile in self.factory.machines:
                self.inspected_tile = tile
            elif button == 1 and self.build(tile) and self.build_tool == "belt":
                self.drag_tile = tile
                self.drag_built = {tile}
            elif button == 3 and tile in self.factory.machines:
                self.mark_change(self.factory.dismantle(tile))
                if self.inspected_tile == tile:
                    self.inspected_tile = None

    def drag(self, point):
        tile = self.camera.tile_at(point)
        if tile is None:
            self.drag_tile = None
            return
        current = self.drag_tile
        tx, ty = tile
        while current != tile:
            x, y = current
            dx, dy = tx - x, ty - y
            step = ((1 if dx > 0 else -1), 0) if abs(dx) >= abs(dy) else (0, (1 if dy > 0 else -1))
            direction = DIRS.index(step)
            dest = x + step[0], y + step[1]
            if dest in self.factory.machines:
                if dest not in self.drag_built:
                    self.mark_change(self.factory.rotate_to(current, direction))
                self.drag_tile = None
                return
            old_direction = self.direction
            self.direction = direction
            built = self.build(dest)
            self.direction = old_direction
            if not built:
                self.drag_tile = None
                return
            self.factory.rotate_to(current, direction)
            self.drag_built.add(dest)
            current = dest
        self.drag_tile = current

    def event(self, event):
        if event.type == pygame.QUIT:
            self.change_session("quit")
        elif event.type == pygame.KEYDOWN:
            self.keydown(event.key, event.mod)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.click(self.logical_point(event.pos), event.button)
        elif event.type in (pygame.MOUSEBUTTONUP, pygame.WINDOWFOCUSLOST):
            self.drag_tile = None
            self.pan_point = None
        elif event.type == pygame.MOUSEMOTION and self.pan_point is not None:
            point = self.logical_point(event.pos)
            if not event.buttons[1] or self.overlay or point == (-1, -1):
                self.pan_point = None
            else:
                self.camera.x += point[0] - self.pan_point[0]
                self.camera.y += point[1] - self.pan_point[1]
                self.camera.clamp()
                self.pan_point = point
        elif event.type == pygame.MOUSEMOTION and self.drag_tile is not None:
            if not event.buttons[0] or self.build_tool != "belt" or self.overlay:
                self.drag_tile = None
            else:
                self.drag(self.logical_point(event.pos))
        elif event.type == pygame.MOUSEWHEEL and not self.in_menu and not self.overlay:
            point = self.logical_point(pygame.mouse.get_pos())
            if MAP.collidepoint(point) and event.y:
                self.camera.zoom_at(point, -event.y if event.flipped else event.y)

    def check_ending(self):
        if (not self.in_menu and not self.demo and self.factory.total_sales >= SALES_TARGET
                and not self.factory.ending_seen):
            self.factory.ending_seen = True
            self.modified = True
            self.set_overlay("ending")
            self.drag_tile = self.pan_point = None

    def update(self, dt, keys):
        self.check_ending()
        if self.overlay:
            return
        if self.in_menu:
            self.menu_fraction += dt
            while self.menu_fraction >= STEP:
                self.menu_factory.step()
                self.menu_fraction -= STEP
            return
        horizontal = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        vertical = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])
        if horizontal or vertical:
            self.camera.pan(horizontal, vertical, dt)
        if not self.paused:
            self.fraction += dt
            while self.fraction >= STEP:
                self.factory.step()
                self.fraction -= STEP
                self.check_ending()
                if self.overlay:
                    break

    def render(self):
        view = self.viewport()
        canvas = self.ui.render(self, self.logical_point(pygame.mouse.get_pos()), view.size)
        self.screen.fill((9, 15, 17))
        self.screen.blit(canvas, view.topleft)
        pygame.display.flip()

    def run(self):
        self.render()
        while self.running:
            dt = min(0.2, self.clock.tick(60) / 1000)
            for event in pygame.event.get():
                self.event(event)
            if self.running:
                self.update(dt, pygame.key.get_pressed())
                self.render()


def smoke_test(report: Path):
    """Verify that the packaged game can render, produce, and save."""
    with TemporaryDirectory(prefix="minifactory-test-") as folder:
        game = Game(Path(folder) / "factory.json", language="en")
        game.render()
        game.action("example")
        game.demo = False  # Permit saving into the smoke test's temporary directory.
        for _ in range(300):
            game.factory.step()
        game.render()
        if game.factory.warehouse_parts < 10:
            raise RuntimeError("The example factory did not produce ten parts.")
        game.action("dispatch")
        if game.factory.shipped_units != 10 or not game.save():
            raise RuntimeError("Dispatch or JSON save failed.")
        game.action("load")
        if game.message != tr("Factory loaded.") or game.factory.shipped_units != 10:
            raise RuntimeError("JSON verification failed.")
        game.choose_language("ko")
        game.action("advanced")
        for _ in range(1000):
            game.factory.step()
        game.inspected_tile = (17, 10)
        game.render()
        if game.factory.warehouse_stock("steel") < 8 or game.factory.warehouse_stock("circuit") < 10:
            raise RuntimeError("The circuit factory did not fill its contracts.")
    report.write_text(
        f"PASS: pygame-ce {pygame.version.ver}, English/Korean render, basic and circuit production, shipment, JSON round-trip\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description="MiniFactory iron works")
    parser.add_argument("--demo", action="store_true", help="Start with a working example.")
    parser.add_argument("--smoke-test", type=Path, metavar="REPORT",
                        help="Verify rendering, production and JSON using a temporary save.")
    args = parser.parse_args()
    pygame.init()
    try:
        if args.smoke_test:
            smoke_test(args.smoke_test)
            return
        game = Game()
        if args.demo:
            game.overlay = None
            game.action("example")
        game.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
