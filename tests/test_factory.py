import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from simulation import (
    BELT_TIME, BUILD_MATERIALS, GUIDE, MINERALS, OUTPUT_LIMIT, RECIPES,
    STORAGE_LIMIT, TECHS, UPGRADE_COST, UPGRADE_MATERIALS, Factory,
)
from example_layouts import advanced_sample
from simulation import upgrade_cost
from save_game import SaveError, read_save, write_save


def advance(factory, count):
    for _ in range(count):
        factory.step()


def material_total(factory):
    weights = {"ore": 1, "plate": 1, "part": 2}
    total = sum(weights[item] * count for item, count in factory.player_inventory.items())
    total += 2 * factory.shipped_units
    for machine in factory.machines.values():
        for stock in (machine.inputs, machine.outputs, machine.storage):
            total += sum(weights[item] * count for item, count in stock.items())
        if machine.craft_steps_left:
            total += sum(weights[item] * count for item, count in machine.plan.inputs.items())
    return total


class FactoryTests(unittest.TestCase):
    def test_build_rotate_and_recover(self):
        factory = Factory()
        factory.place((1, 1), "miner", 0)
        self.assertEqual(factory.credits, 1000)
        factory.place((1, 1), "belt", 0)
        factory.machines[(1, 1)].outputs["ore"] = 1
        factory.place((1, 1), "storage", 0)
        self.assertEqual(factory.machines[(1, 1)].kind, "belt")
        self.assertEqual(factory.credits, 980)
        factory.rotate((1, 1))
        self.assertEqual(factory.machines[(1, 1)].direction, 1)
        factory.dismantle((1, 1))
        factory.dismantle((1, 1))
        self.assertEqual(factory.credits, 1000)
        self.assertEqual(factory.player_inventory["ore"], 1)
        factory.credits = 1
        factory.place((1, 1), "belt", 0)
        self.assertFalse(factory.machines)
        self.assertEqual(factory.credits, 1)

    def test_turn_moves_only_one_tile_per_step(self):
        factory = Factory()
        for pos, direction in (((1, 1), 0), ((2, 1), 1), ((2, 2), 0)):
            factory.place(pos, "belt", direction)
        factory.place((3, 2), "storage", 0)
        factory.machines[(1, 1)].outputs["ore"] = 1
        factory.step()
        self.assertEqual(factory.machines[(2, 1)].outputs["ore"], 1)
        advance(factory, BELT_TIME - 1)
        self.assertFalse(factory.machines[(2, 2)].outputs)
        factory.step()
        self.assertEqual(factory.machines[(2, 2)].outputs["ore"], 1)
        advance(factory, BELT_TIME)
        self.assertEqual(factory.machines[(3, 2)].storage["ore"], 1)
        self.assertEqual(material_total(factory), 1)

    def test_wrong_input_side_and_material(self):
        factory = Factory()
        factory.place((4, 4), "furnace", 0)
        factory.place((5, 4), "belt", 2)
        factory.place((3, 4), "belt", 0)
        front, west = factory.machines[(5, 4)], factory.machines[(3, 4)]
        front.outputs["ore"], west.outputs["part"] = 1, 1
        advance(factory, 8)
        self.assertEqual(material_total(factory), 3)
        self.assertFalse(factory.machines[(4, 4)].inputs)
        self.assertEqual(front.outputs["ore"], 1)
        self.assertEqual(west.outputs["part"], 1)
        west.outputs.clear()
        west.outputs["ore"] = 1
        factory.step()
        self.assertEqual(factory.machines[(4, 4)].inputs["ore"], 1)

    def test_copper_from_west_and_coal_from_south_reach_storage(self):
        factory = Factory()
        for pos, kind, direction in (
            ((3, 4), "belt", 0), ((4, 5), "belt", 3), ((4, 4), "furnace", 0), ((5, 4), "storage", 0)
        ):
            factory.place(pos, kind, direction)
        factory.switch_recipe((4, 4), 3)
        factory.machines[(3, 4)].outputs["copper_ore"] = 1
        factory.machines[(4, 5)].outputs["coal"] = 1
        self.assertEqual(factory.incoming_items((4, 4)), {"copper_ore", "coal"})
        advance(factory, 30)
        self.assertEqual(factory.warehouse_stock("copper"), 1)
        for direction in range(4):
            furnace = factory.machines[(4, 4)]
            furnace.direction = direction
            for side in range(4):
                self.assertEqual(furnace.accepts("coal", side), side != direction)

    def test_two_inputs_take_turns_at_merge(self):
        factory = Factory()
        for pos, kind, direction in (((3, 4), "belt", 0), ((4, 3), "belt", 1), ((4, 4), "storage", 0)):
            factory.place(pos, kind, direction)
        west, north, warehouse = (factory.machines[pos] for pos in ((3, 4), (4, 3), (4, 4)))
        west.outputs["ore"] = north.outputs["plate"] = 1
        factory.step()
        self.assertEqual(dict(warehouse.storage), {"ore": 1})
        west.outputs["ore"] = 1
        factory.step()
        self.assertEqual(dict(warehouse.storage), {"ore": 1, "plate": 1})
        self.assertEqual(west.outputs["ore"], 1)

    def test_recipe_cancel_and_dismantle_return_materials(self):
        factory = Factory()
        pos = (4, 4)
        factory.place(pos, "assembler", 0)
        factory.player_inventory["plate"] = 3
        factory.deposit(pos, "plate")
        factory.step()
        self.assertEqual(factory.machines[pos].inputs["plate"], 1)
        factory.switch_recipe(pos)
        self.assertEqual(factory.player_inventory["plate"], 2)
        advance(factory, 30)
        self.assertFalse(factory.machines[pos].outputs)
        factory.player_inventory["ore"] = 1
        factory.deposit(pos, "ore")
        factory.step()
        self.assertTrue(factory.machines[pos].craft_steps_left)
        factory.dismantle(pos)
        self.assertEqual(dict(factory.player_inventory), {"plate": 3, "ore": 1})

    def test_two_feeder_assembly_line(self):
        factory = Factory.sample()
        for pos, kind, direction in (
            ((5, 5), "miner", 0), ((6, 5), "belt", 0),
            ((7, 5), "belt", 0), ((8, 5), "belt", 1),
        ):
            factory.place(pos, kind, direction)
        factory.switch_recipe((8, 6))
        advance(factory, 300)
        self.assertGreaterEqual(factory.warehouse_parts, 10)
        self.assertEqual(factory.machines[(8, 6)].recipe, 1)

    def test_warehouse_backpressure_and_restart(self):
        factory = Factory.sample()
        advance(factory, 3000)
        self.assertEqual(factory.warehouse_parts, STORAGE_LIMIT)
        self.assertEqual(factory.machines[(8, 6)].outputs["part"], OUTPUT_LIMIT)
        self.assertLessEqual(factory.machines[(4, 6)].outputs["ore"], OUTPUT_LIMIT)
        before = material_total(factory)
        factory.withdraw((10, 6), "part")
        self.assertEqual(material_total(factory), before)
        self.assertEqual(factory.warehouse_parts, STORAGE_LIMIT - 5)
        advance(factory, 200)
        self.assertEqual(factory.warehouse_parts, STORAGE_LIMIT)

    def test_conservation_and_contracts(self):
        factory = Factory.sample()
        for required, reward in ((10, 1200), (25, 3000), (50, 6000)):
            for _ in range(1200):
                mined = factory.machines[GUIDE[0][0]].craft_steps_left == 1
                before = material_total(factory)
                factory.step()
                self.assertEqual(material_total(factory), before + mined)
            self.assertGreaterEqual(factory.warehouse_parts, required)
            before = material_total(factory)
            credits = factory.credits
            stock = factory.warehouse_parts
            factory.dispatch()
            self.assertEqual(material_total(factory), before)
            self.assertEqual(factory.warehouse_parts, stock - required)
            self.assertEqual(factory.credits, credits + reward)
        self.assertEqual(factory.shipped_units, 85)

    def test_advanced_construction_and_upgrade_charge_materials_and_money(self):
        factory = Factory()
        pos = (2, 3)
        factory.place(pos, "press", 0)
        self.assertNotIn(pos, factory.machines)
        self.assertEqual(factory.credits, 1000)
        factory.player_inventory.update(BUILD_MATERIALS["press"])
        factory.place(pos, "press", 0)
        self.assertEqual(factory.machines[pos].kind, "press")
        self.assertFalse(factory.player_inventory)
        before = factory.credits
        factory.upgrade(pos)
        self.assertEqual(factory.credits, before)
        factory.player_inventory.update(UPGRADE_MATERIALS)
        factory.upgrade(pos)
        self.assertEqual(factory.credits, before - UPGRADE_COST)
        self.assertFalse(factory.player_inventory)
        self.assertEqual(factory.machines[pos].level, 2)
        self.assertLess(factory.recipe_steps(factory.machines[pos]), RECIPES["press"][0].steps)
        factory.upgrade(pos)
        self.assertEqual(factory.credits, before - UPGRADE_COST)

    def test_splitter_alternates_and_skips_a_full_exit(self):
        factory = Factory()
        factory.player_inventory.update(BUILD_MATERIALS["splitter"])
        for pos, kind in (((2, 2), "splitter"), ((3, 2), "storage"), ((2, 3), "storage")):
            factory.place(pos, kind, 0)
        split = factory.machines[(2, 2)]
        for _ in range(4):
            split.receive("copper_ore")
            advance(factory, BELT_TIME)
        east = factory.machines[(3, 2)]
        south = factory.machines[(2, 3)]
        self.assertEqual((east.storage["copper_ore"], south.storage["copper_ore"]), (2, 2))
        east.storage["coal"] = STORAGE_LIMIT - 2
        split.receive("copper_ore")
        advance(factory, BELT_TIME)
        self.assertEqual((east.storage["copper_ore"], south.storage["copper_ore"]), (2, 3))
        self.assertFalse(split.outputs)

    def test_advanced_sample_processes_all_three_minerals_into_contracts(self):
        factory = advanced_sample()
        self.assertEqual({m.plan.product for m in factory.machines.values() if m.kind == "miner"},
                         {"ore", "copper_ore", "coal"})
        advance(factory, 1000)
        self.assertGreaterEqual(factory.warehouse_stock("steel"), 8)
        self.assertGreaterEqual(factory.warehouse_stock("circuit"), 10)
        factory.dispatch()
        factory.dispatch()
        self.assertEqual(factory.contract_index, 5)
        self.assertEqual(factory.shipped_units, 103)


    def test_filtered_splitter_never_uses_the_other_exit_when_blocked(self):
        factory = Factory()
        factory.player_inventory.update(BUILD_MATERIALS["splitter"])
        for pos, kind in (((2, 2), "splitter"), ((3, 2), "storage"), ((2, 3), "storage")):
            factory.place(pos, kind, 0)
        splitter = factory.machines[(2, 2)]
        east = factory.machines[(3, 2)]
        south = factory.machines[(2, 3)]
        factory.set_filter((2, 2), "ore")
        splitter.receive("copper_ore")
        advance(factory, BELT_TIME)
        self.assertEqual(east.storage["copper_ore"], 1)
        south.storage["coal"] = STORAGE_LIMIT
        splitter.receive("ore")
        advance(factory, BELT_TIME + 4)
        self.assertEqual(splitter.outputs["ore"], 1)
        self.assertEqual(east.storage["ore"], 0)
        south.storage.clear()
        factory.step()
        self.assertEqual(south.storage["ore"], 1)

    def test_all_starter_ores_are_available_and_pay_only_one_first_bonus(self):
        for deposit, ore in (((4, 9), "copper_ore"), ((11, 8), "coal")):
            with self.subTest(ore=ore):
                factory = Factory()
                x, y = deposit
                factory.place(deposit, "miner", 0)
                factory.place((x + 1, y), "storage", 0)
                self.assertEqual(factory.machines[deposit].plan.product, ore)
                before = factory.credits
                advance(factory, 140)
                stock = factory.warehouse_stock(ore)
                self.assertGreaterEqual(stock, 10)
                factory.ship_starter(ore)
                self.assertTrue(factory.starter_complete)
                self.assertEqual(factory.shipped_units, 10)
                self.assertEqual(factory.warehouse_stock(ore), stock - 10)
                self.assertEqual(factory.credits, before + 450)
                factory.ship_starter(ore)
                self.assertEqual(factory.credits, before + 450)

    def test_selling_only_charges_carried_stock(self):
        factory = Factory.sample()
        advance(factory, 300)
        stock = factory.warehouse_stock("part")
        before = factory.credits
        factory.sell("part", 5)
        self.assertEqual(factory.credits, before)
        self.assertEqual(factory.warehouse_stock("part"), stock)
        factory.withdraw((10, 6), "part")
        factory.sell("part", 5)
        self.assertEqual(factory.credits, before + 475)

    def test_quartz_research_and_silicon_refining(self):
        factory = advanced_sample()
        factory.unlocked.remove("quartz")
        factory.player_inventory["circuit"] = 2
        factory.research("quartz")
        self.assertIn("quartz", factory.unlocked)
        self.assertEqual(factory.player_inventory["circuit"], 0)
        for pos, kind in (((45, 13), "miner"), ((46, 13), "furnace"), ((47, 13), "storage")):
            factory.place(pos, kind, 0)
        factory.switch_recipe((46, 13))
        factory.switch_recipe((46, 13))
        factory.player_inventory["coal"] = 3
        factory.deposit((46, 13), "coal")
        advance(factory, 100)
        self.assertEqual(factory.warehouse_stock("silicon"), 3)


    def test_iron_research_needs_first_shipment_and_own_copper_ingots(self):
        factory = Factory()
        iron = (4, 6)
        factory.place(iron, "miner", 0)
        self.assertNotIn(iron, factory.machines)
        factory.player_inventory["copper"] = 3
        factory.research("ore")
        self.assertNotIn("ore", factory.unlocked)
        factory.place((5, 9), "storage", 0)
        factory.machines[(5, 9)].storage["copper_ore"] = 10
        factory.ship_starter("copper_ore")
        factory.research("ore")
        self.assertIn("ore", factory.unlocked)
        self.assertEqual(factory.player_inventory["copper"], 0)
        factory.place(iron, "miner", 0)
        self.assertEqual(factory.machines[iron].plan.product, "ore")

    def test_level_five_warehouse_capacity_transfer_and_save(self):
        factory = Factory(credits=5000, unlocked=set(TECHS))
        pos = (2, 2)
        factory.place(pos, "storage", 0)
        warehouse = factory.machines[pos]
        for target in range(2, 6):
            _, materials = upgrade_cost(warehouse)
            factory.player_inventory.update(materials)
            factory.upgrade(pos)
            self.assertEqual(warehouse.capacity, 80 * target)
        factory.player_inventory["ore"] = 460
        factory.deposit(pos, "ore", None)
        self.assertTrue(warehouse.full)
        self.assertFalse(warehouse.accepts("coal", 0))
        self.assertEqual(factory.player_inventory["ore"], 60)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "factory.json"
            write_save(path, factory)
            factory = read_save(path)
        factory.withdraw(pos, "ore", 10)
        self.assertEqual(factory.warehouse_stock("ore"), 390)
        factory.withdraw(pos, "ore", None)
        self.assertEqual(factory.warehouse_stock("ore"), 0)
        self.assertEqual(factory.player_inventory["ore"], 460)

    def test_higher_upgrades_require_their_research(self):
        factory = Factory(credits=5000)
        pos = (2, 2)
        factory.place(pos, "belt", 0)
        machine = factory.machines[pos]
        _, materials = upgrade_cost(machine)
        factory.player_inventory.update(materials)
        factory.upgrade(pos)
        _, materials = upgrade_cost(machine)
        factory.player_inventory.update(materials)
        factory.upgrade(pos)
        self.assertEqual(machine.level, 2)
        _, research_materials, _ = TECHS["processing"]
        factory.player_inventory.update(research_materials)
        factory.starter_shipped = True
        factory.unlocked.add("ore")
        factory.research("processing")
        factory.upgrade(pos)
        self.assertEqual(machine.level, 3)
        self.assertEqual(machine.belt_delay, 2)


class SaveTests(unittest.TestCase):
    def test_round_trip_mid_batch_with_non_ascii_path(self):
        factory = Factory.sample()
        advance(factory, 300)
        factory.dispatch()
        factory.player_inventory.update(UPGRADE_MATERIALS)
        factory.upgrade((6, 6))
        factory.withdraw((10, 6), "part")
        factory.switch_recipe((8, 6))
        factory.player_inventory["ore"] = 2
        factory.deposit((8, 6), "ore")
        factory.player_inventory["plate"] += 2
        factory.deposit((8, 6), "plate")
        factory.step()
        self.assertGreater(factory.machines[(8, 6)].craft_steps_left, 0)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "공장 & 저장" / "factory.json"
            write_save(path, factory)
            restored = read_save(path)
            factory.arrivals.clear()
            self.assertEqual(restored, factory)
            advance(restored, 250)
            advance(factory, 250)
            self.assertEqual(restored, factory)

    def test_old_save_gets_new_deposits_with_original_equipment(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "factory.json"
            factory = Factory.sample()
            write_save(path, factory)
            state = json.loads(path.read_text(encoding="utf-8"))
            state["version"] = 1
            state["credits"] //= 10
            state["deposits"] = [pos for pos in state["deposits"] if tuple(pos) not in MINERALS]
            for entry in state["machines"]:
                del entry["level"]
                del entry["branch"]
            path.write_text(json.dumps(state), encoding="utf-8")
            self.assertEqual(read_save(path), factory)

    def test_splitter_state_and_upgraded_advanced_machines_round_trip(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "factory.json"
            factory = advanced_sample()
            advance(factory, 200)
            factory.player_inventory.update(UPGRADE_MATERIALS)
            factory.upgrade((17, 10))
            factory.set_filter((17, 12), "steel")
            write_save(path, factory)
            factory.arrivals.clear()
            self.assertEqual(read_save(path), factory)

    def test_failed_replacement_keeps_previous_save(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "factory.json"
            previous = Factory.sample()
            write_save(path, previous)
            with patch("save_game.os.replace", side_effect=PermissionError("locked file")):
                with self.assertRaises(PermissionError):
                    write_save(path, Factory())
            self.assertEqual(read_save(path), previous)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_invalid_machine_direction_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "factory.json"
            write_save(path, Factory.sample())
            state = json.loads(path.read_text(encoding="utf-8"))
            state["machines"][0]["direction"] = 99
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(SaveError):
                read_save(path)

    def test_unknown_version_and_empty_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "factory.json"
            with self.assertRaises(FileNotFoundError):
                read_save(path)
            path.touch()
            with self.assertRaises(SaveError):
                read_save(path)
            path.write_text('{"version": 99}', encoding="utf-8")
            with self.assertRaisesRegex(SaveError, "Unsupported"):
                read_save(path)


if __name__ == "__main__":
    unittest.main()
