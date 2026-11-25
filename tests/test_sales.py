import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from simulation import Factory, Machine, SHOP_SELL
from save_game import read_save, write_save


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.factory = Factory(starter_shipped=True, shipped_units=10)
        self.warehouse = Machine("storage", 0)
        self.extractor = Machine("extractor", 0, filter_item="coal")
        self.factory.machines.update({
            (2, 2): self.warehouse, (3, 2): self.extractor, (4, 2): Machine("seller", 0),
        })

    def reload(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "factory.json"
            write_save(path, self.factory)
            return read_save(path)

    def test_auto_seller_requires_automation_research(self):
        factory = self.factory
        factory.player_inventory["copper"] = 5
        factory.place((5, 5), "extractor", 0)
        before = factory.credits
        factory.place((6, 5), "seller", 0)
        self.assertNotIn((6, 5), factory.machines)
        self.assertEqual(factory.credits, before)
        factory.unlocked.add("processing")
        factory.player_inventory.update(wire=6, steel=3)
        factory.research("automation")
        factory.place((6, 5), "seller", 0)
        self.assertEqual(factory.machines[(6, 5)].kind, "seller")

    def test_old_ending_gets_new_target_and_wallet_conversion_once(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "factory.json"
            write_save(path, self.factory)
            state = json.loads(path.read_text())
            state.update(version=6, ending_seen=True, revenue=7500, credits=55)
            path.write_text(json.dumps(state))
            loaded = read_save(path)
            self.assertFalse(loaded.ending_seen)
            self.assertEqual((loaded.credits, loaded.total_sales), (550, 7500))
            write_save(path, loaded)
            self.assertEqual(read_save(path), loaded)

    def test_shared_stock_preserves_reserve_and_records_sales_once(self):
        self.warehouse.storage.update(coal=73, ore=3)
        self.extractor.controlled, self.extractor.reserve = True, 50
        self.factory.machines[(2, 3)] = Machine("extractor", 1, filter_item="coal", controlled=True, reserve=50)
        self.factory.machines[(2, 4)] = Machine("seller", 2)
        for _ in range(200):
            self.factory.step()
        self.assertEqual(self.warehouse.storage, {"coal": 50, "ore": 3})
        self.assertEqual(self.factory.total_sales, 230)
        self.assertEqual(self.reload().total_sales, 230)

    def test_blocked_and_paused_extractors_keep_stock(self):
        self.warehouse.storage["coal"] = 3
        self.extractor.paused = True
        self.factory.step()
        self.extractor.paused = False
        del self.factory.machines[(4, 2)]
        self.factory.step()
        self.assertEqual(self.factory.total_sales, 0)
        self.assertEqual(self.warehouse.storage["coal"], 3)

    def test_module_install_cycle_and_dismantle_refund(self):
        self.factory.player_inventory["module"] = 1
        for expected in (0, 25, 50, 0):
            self.factory.configure_reserve((3, 2))
            self.assertEqual(self.extractor.reserve, expected)
        self.warehouse.level = 2
        for expected in (25, 50, 100):
            self.factory.configure_reserve((3, 2))
            self.assertEqual(self.extractor.reserve, expected)
        self.assertEqual(self.reload().machines[(3, 2)].reserve, 100)
        self.factory.dismantle((3, 2))
        self.assertEqual(self.factory.player_inventory["module"], 1)

    def test_recipe_switch_keeps_finished_stock_loadable(self):
        machine = self.factory.machines[(5, 2)] = Machine("furnace", 0)
        machine.outputs["plate"] = 2
        self.factory.switch_recipe((5, 2))
        self.assertEqual(self.reload().machines[(5, 2)].outputs, {"plate": 2})

    def test_module_production_and_manual_sales(self):
        machine = self.factory.machines[(7, 2)] = Machine("electronics", 0)
        self.factory.switch_recipe((7, 2))
        machine.inputs.update(circuit=2, steel=1, silicon=1)
        for _ in range(40):
            self.factory.step()
        self.factory.dismantle((7, 2))
        self.factory.sell("module", 1)
        self.assertEqual(self.factory.total_sales, SHOP_SELL["module"])
