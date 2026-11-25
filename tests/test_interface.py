import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from simulation import GUIDE, TYPES, WORLD_H, WORLD_W
from translations import tr
from main import Game
from interface import MAP, SIZE


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.game = Game(Path(temp.name) / "factory.json", language="en")

    def key(self, key, mods=0):
        self.game.event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mods))

    def click(self, pos, button=1):
        self.game.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
        self.game.event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))

    def update(self, dt, *keys):
        class KeyState:
            def __getitem__(self, key):
                return key in keys

        self.game.update(dt, KeyState())

    def test_upgrade_reports_every_shortage_without_spending(self):
        game = self.game
        game.action("new")
        pos = (2, 2)
        factory = game.factory
        factory.place(pos, "furnace", 0)
        game.inspected_tile = pos
        factory.credits = 240
        factory.player_inventory["plate"] = 1
        for language in ("ko", "en"):
            game.choose_language(language)
            game.action("upgrade")
            for label, count in (("CREDITS", 60), ("Iron plate", 1), ("Machine part", 2)):
                self.assertIn(f"{tr(label)} ×{count}", game.message)
            self.assertEqual(factory.machines[pos].level, 1)
            self.assertEqual(factory.credits, 240)
            self.assertEqual(factory.player_inventory["plate"], 1)
        factory.credits += 60
        factory.player_inventory.update({"plate": 1, "part": 2})
        game.action("upgrade")
        self.assertEqual(factory.machines[pos].level, 2)
        self.assertEqual(factory.credits, 0)

    def test_camera_controls_panning_zoom_and_bounds(self):
        self.game.action("new")
        for key, x_axis, sign in (
            (pygame.K_w, False, 1), (pygame.K_UP, False, 1),
            (pygame.K_a, True, 1), (pygame.K_LEFT, True, 1),
            (pygame.K_s, False, -1), (pygame.K_DOWN, False, -1),
            (pygame.K_d, True, -1), (pygame.K_RIGHT, True, -1),
        ):
            self.game.camera.reset()
            origin = self.game.camera.x if x_axis else self.game.camera.y
            self.update(0.05, key)
            shifted = self.game.camera.x if x_axis else self.game.camera.y
            self.assertGreater((shifted - origin) * sign, 0)
        self.game.camera.reset()
        aim = self.game.camera.rect((4, 6)).center
        self.game.camera.zoom_at(aim, 3)
        self.assertEqual(self.game.camera.tile_at(aim), (4, 6))
        for _ in range(90):
            self.game.camera.pan(1, 1, 0.3)
        self.assertTrue(self.game.camera.rect((WORLD_W - 1, WORLD_H - 1)).colliderect(MAP))
        self.assertIsNone(self.game.camera.tile_at((MAP.right + 5, MAP.centery)))

    def test_build_line_with_mouse_rotate_pause_ship_save_and_load(self):
        self.game.render()
        self.click((280, 318))  # Main menu's new factory button.
        self.game.factory.unlocked.add("ore")  # Verify the full iron line after stage 2.
        self.key(pygame.K_SPACE)
        self.update(0.5)
        self.assertEqual(self.game.factory.steps, 0)
        for tile, kind, _ in GUIDE:
            self.key(pygame.K_1 + TYPES.index(kind))
            self.click(self.game.camera.rect(tile).center)
        assembler_tile = (8, 6)
        self.click(self.game.camera.rect(assembler_tile).center)
        self.key(pygame.K_r, pygame.KMOD_SHIFT)
        self.assertEqual(self.game.factory.machines[assembler_tile].direction, 1)
        for _ in range(3):
            self.key(pygame.K_r, pygame.KMOD_SHIFT)
        self.key(pygame.K_SPACE)
        for _ in range(300):
            self.update(0.1)
        self.assertGreaterEqual(self.game.factory.warehouse_parts, 10)
        self.key(pygame.K_RETURN)
        self.assertEqual(self.game.factory.shipped_units, 10)
        self.key(pygame.K_F5)
        self.assertTrue(self.game.store_path.is_file())

        self.click(self.game.camera.rect((6, 6)).center, button=3)
        self.assertNotIn((6, 6), self.game.factory.machines)
        self.key(pygame.K_F9)
        self.assertEqual(self.game.overlay, "confirm")
        self.game.action("confirm")
        self.assertIn((6, 6), self.game.factory.machines)
        self.assertEqual(self.game.factory.shipped_units, 10)

    def test_scaled_window_panel_and_map_hit_testing(self):
        self.game.action("new")
        self.game.screen = pygame.display.set_mode((800, 520), pygame.RESIZABLE)
        self.game.render()
        view = self.game.viewport()
        to_physical = lambda p: (view.x + round(p[0] * view.width / SIZE[0]),
                                 view.y + round(p[1] * view.height / SIZE[1]))
        self.click((0, 0))
        self.assertFalse(self.game.factory.machines)
        miner = next(rect.center for rect, action in self.game.ui.buttons if action == "tool:miner")
        self.click(to_physical(miner))
        self.assertEqual(self.game.build_tool, "miner")
        self.click(to_physical(self.game.camera.rect((4, 9)).center))
        self.assertEqual(self.game.factory.machines[(4, 9)].kind, "miner")
        self.game.render()


    def test_first_launch_language_selection_and_reload(self):
        path = self.game.store_path
        self.game = Game(path)
        self.assertEqual(self.game.overlay, "language")
        self.game.render()
        self.click((500, 410))
        self.assertEqual(self.game.language, "ko")
        self.assertEqual(tr("Start a new factory"), "새 공장 시작")
        self.assertIsNone(self.game.overlay)
        self.game = Game(path)
        self.assertEqual(self.game.language, "ko")
        self.game.action("help")
        self.game.action("language")
        self.game.render()
        self.click((780, 412))
        self.assertEqual(self.game.language, "en")
        self.assertEqual(tr("Start a new factory"), "Start a new factory")


    def test_mouse_pan_and_drag_build_real_corner(self):
        game = self.game
        game.action("new")
        self.key(pygame.K_1)
        point = game.camera.rect((4, 4)).center
        game.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=point, button=2))
        origin = game.camera.x, game.camera.y
        game.event(pygame.event.Event(pygame.MOUSEMOTION, pos=(point[0]+50, point[1]+25),
                                       buttons=(0, 1, 0)))
        self.assertEqual((game.camera.x, game.camera.y), (origin[0]+50, origin[1]+25))
        game.event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=point, button=2))
        game.camera.reset()
        game.factory.place((6, 7), "storage", 0)
        game.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                       pos=game.camera.rect((4, 4)).center, button=1))
        for tile in ((6, 4), (6, 6), (6, 7)):
            game.event(pygame.event.Event(pygame.MOUSEMOTION, pos=game.camera.rect(tile).center,
                                           buttons=(1, 0, 0)))
        corner = game.factory.machines[(6, 4)]
        self.assertEqual(game.factory.belt_inputs((6, 4), corner), (2,))
        self.assertEqual(corner.direction, 1)
        game.factory.machines[(4, 4)].receive("ore")
        self.update(3.0)
        self.assertEqual(game.factory.warehouse_stock("ore"), 1)

    def test_examples_cannot_overwrite_player_save(self):
        self.game.action("new")
        self.assertTrue(self.game.save())
        before = self.game.store_path.read_bytes()
        self.game.action("advanced")
        self.assertTrue(self.game.demo)
        self.assertFalse(self.game.save())
        self.assertEqual(self.game.store_path.read_bytes(), before)


    def test_first_copper_shipment_is_available_from_the_screen_and_survives_reload(self):
        game = self.game
        game.action("new")
        game.factory.place((4, 9), "miner", 0)
        game.factory.place((5, 9), "storage", 0)
        self.update(15.0)
        game.render()
        copper = next(rect for rect, action in game.ui.buttons if action == "first:copper_ore")
        self.click(copper.center)
        self.assertTrue(game.factory.starter_shipped)
        self.assertEqual(game.factory.shipped_units, 10)
        self.assertTrue(game.save())
        game.action("load")
        self.assertTrue(game.factory.starter_shipped)
        self.assertEqual(game.factory.shipped_units, 10)


    def test_high_resolution_draws_at_viewport_size_and_preserves_mouse_controls(self):
        game = self.game
        game.action("new")
        game.screen = pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)
        game.render()
        viewport = game.viewport()
        self.assertEqual(game.ui.canvas.get_size(), (1728, 1080))
        self.assertGreater(game.ui.fonts["small"].get_height(), 14)
        miner = next(rect.center for rect, action in game.ui.buttons if action == "tool:miner")
        for point in (miner, game.camera.rect((4, 9)).center):
            self.click((viewport.x + round(point[0] * game.ui.scale_x),
                        viewport.y + round(point[1] * game.ui.scale_y)))
        self.assertEqual(game.factory.machines[(4, 9)].kind, "miner")

    def test_auto_sale_ending_and_resume_saved_game(self):
        from simulation import Machine, SALES_TARGET
        game = self.game
        game.action("new")
        factory = game.factory
        factory.starter_shipped, factory.shipped_units = True, 10
        factory.unlocked.add("automation")
        factory.total_sales = SALES_TARGET - 10
        factory.player_inventory["copper"] = 5
        factory.place((3, 4), "storage", 0)
        factory.machines[(3, 4)].storage["coal"] = 1
        for pos, kind in (((4, 4), "extractor"), ((5, 4), "seller")):
            game.render()
            button = next(rect for rect, action in game.ui.buttons if action == "tool:" + kind)
            self.click(button.center)
            self.click(game.camera.rect(pos).center)
            self.assertIsInstance(factory.machines[pos], Machine)
        self.click(game.camera.rect((4, 4)).center)
        for control in ("filter", "filter:coal"):
            game.render()
            button = next(rect for rect, action in game.ui.buttons if action == control)
            self.click(button.center)
        self.update(0.1)
        self.assertEqual(game.overlay, "ending")
        game.render()
        self.click(next(rect.center for rect, action in game.ui.buttons if action == "finish-menu"))
        self.assertTrue(game.in_menu)
        game.action("load")
        self.update(0.1)
        self.assertTrue(game.factory.ending_seen)
        self.assertIsNone(game.overlay)
        self.assertEqual(game.factory.total_sales, SALES_TARGET)

    def test_build_dock_and_preview_controls_in_both_languages(self):
        game = self.game
        game.action("new")

        def click_action(action):
            game.render()
            rect = next(rect for rect, key in game.ui.buttons if key == action)
            self.click(rect.center)

        for lang in ("ko", "en"):
            game.choose_language(lang)
            for kind in TYPES:
                click_action("tool:" + kind)
                self.assertEqual(game.build_tool, kind)
                self.assertIsNone(game.inspected_tile)
            before = game.direction
            click_action("turn-tool")
            self.assertEqual(game.direction, (before + 1) % 4)
            click_action("cancel-tool")
            self.assertIsNone(game.build_tool)
            click_action("pause-game")
            self.assertTrue(game.paused)
            click_action("pause-game")
            self.assertFalse(game.paused)

    def test_coal_fired_iron_unlock_selection_and_production(self):
        game = self.game
        game.action("new")
        factory = game.factory
        pos = (4, 4)
        factory.place(pos, "furnace", 0)
        game.inspected_tile = pos
        self.key(pygame.K_q)
        game.render()
        self.assertNotIn("apply-recipe:4", {key for _, key in game.ui.buttons})
        factory.switch_recipe(pos, 4)
        furnace = factory.machines[pos]
        self.assertEqual(furnace.recipe, 0)
        factory.unlocked.add("ore")
        game.render()
        button = next(rect for rect, key in game.ui.buttons if key == "apply-recipe:4")
        self.click(button.center)
        self.assertEqual(furnace.plan.name, "Coal-fired iron")
        furnace.inputs["ore"] = 1
        factory.step()
        self.assertEqual(furnace.craft_steps_left, 0)
        furnace.inputs["coal"] = 1
        factory.step()
        self.assertEqual(furnace.craft_steps_left, 6)
        for _ in range(6):
            factory.step()
        self.assertFalse(furnace.inputs)
        self.assertEqual(furnace.outputs, {"plate": 1})

    def test_copper_line_restarts_after_selecting_matching_recipe(self):
        game = self.game
        game.action("new")
        for x, kind in enumerate(("miner", "belt", "furnace", "storage"), start=4):
            game.action("tool:" + kind)
            self.click(game.camera.rect((x, 9)).center)
        self.update(5.0)
        pos = (6, 9)
        self.assertEqual(game.factory.incoming_items(pos), {"copper_ore"})
        self.assertEqual(game.factory.warehouse_stock("copper"), 0)
        self.click(game.camera.rect(pos).center)
        self.key(pygame.K_q)
        self.assertEqual(game.overlay, "choose-recipe")
        game.render()
        rect = next(r for r, key in game.ui.buttons if key == "apply-recipe:1")
        self.click(rect.center)
        self.assertEqual(game.factory.machines[pos].plan.product, "copper")
        self.update(5.0)
        self.assertGreater(game.factory.warehouse_stock("copper"), 0)

    def test_sales_quantities_and_early_coal_progression(self):
        game = self.game
        game.action("new")
        factory = game.factory
        factory.player_inventory.update(copper_ore=3, copper=1, coal=70)
        game.action("market")
        game.render()
        actions = {key for _, key in game.ui.buttons}
        self.assertIn("sell:copper_ore:1", actions)
        self.assertNotIn("sell:copper_ore:5", actions)
        self.assertNotIn("sell:copper:5", actions)
        self.assertIn("sell:coal:5", actions)
        self.assertNotIn("sell:ore:1", actions)
        game.action("close")
        factory.place((5, 9), "storage", 0)
        factory.deposit((5, 9), "coal", 10)
        factory.ship_starter("coal")
        game.render()
        actions = {key for _, key in game.ui.buttons}
        self.assertIn("recipe-guide:copper", actions)
        self.assertNotIn("dispatch", actions)
        pos = (4, 9)
        factory.place(pos, "furnace", 0)
        machine = factory.machines[pos]
        factory.switch_recipe(pos, 1)
        normal = factory.recipe_steps(machine)
        factory.switch_recipe(pos, 3)
        self.assertLess(factory.recipe_steps(machine), normal)
        factory.deposit(pos, "coal", 1)
        factory.deposit(pos, "copper_ore", 1)
        self.update(2.0)
        self.assertEqual(factory.warehouse_stock("copper"), 1)

    def test_walkthrough_opens_at_progress_and_all_pages_are_reachable(self):
        from tutorial import CHAPTERS
        game = self.game
        game.action("new")
        for lang in ("ko", "en"):
            game.choose_language(lang)
            game.action("tutorial")
            for index in range(len(CHAPTERS)):
                game.render()
                rect = next(rect for rect, key in game.ui.buttons if key == f"chapter:{index}")
                self.click(rect.center)
                self.assertEqual(game.tutorial_page, index)
            game.action("close")
        game.factory.starter_shipped = True
        game.action("tutorial")
        self.assertEqual(game.tutorial_page, 3)

    def test_bulk_withdraw_changes_research_availability(self):
        game = self.game
        game.action("new")
        f = game.factory
        f.starter_shipped = True
        f.place((2, 2), "storage", 0)
        f.place((3, 2), "storage", 0)
        f.machines[(2, 2)].storage.update(copper=3, coal=7)
        f.machines[(3, 2)].storage.update(coal=9)
        game.action("research-menu")
        game.render()
        self.assertNotIn("research:ore", dict((key,r) for r,key in game.ui.buttons))
        game.action("close")
        game.inspected_tile = (2, 2)
        game.render()
        self.click(next(r.center for r,k in game.ui.buttons if k == "withdraw-all"))
        game.game_action("withdraw-all")
        self.assertEqual(f.player_inventory, {"copper": 3, "coal": 7})
        self.assertEqual(f.warehouse_stock("coal"), 9)
        game.action("research-menu")
        game.render()
        self.click(next(r.center for r,k in game.ui.buttons if k == "research:ore"))
        self.assertIn("ore", f.unlocked)

    def test_fullscreen_shortcut_restores_window_size(self):
        game = self.game
        window_size = pygame.display.get_window_size()
        self.key(pygame.K_F11)
        self.assertTrue(game.fullscreen)
        game.render()
        self.assertEqual(game.ui.canvas.get_size(), game.viewport().size)
        self.key(pygame.K_F11)
        self.assertFalse(game.fullscreen)
        self.assertEqual(pygame.display.get_window_size(), window_size)


if __name__ == "__main__":
    unittest.main()
