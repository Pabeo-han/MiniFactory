"""Game rules independent of pygame. One simulation step is 0.1 seconds."""

from collections import Counter
from dataclasses import dataclass, field

from game_data import (
    BELT_TIME, BUILD_MATERIALS, COST, INPUT_LIMIT, ITEMS, ITEM_LABELS, LABELS, MAX_LEVEL,
    MINING_TECH, ORDERS, OUTPUT_LIMIT, RECIPES, RESERVES, SALES_TARGET, SHOP_SELL,
    START_CREDITS, STARTER_ORES, STARTER_QUANTITY, STARTER_REWARD, STORAGE_LIMIT,
    TECH_NAMES, TECHS, TRANSFER_AMOUNTS, TRANSPORT, TYPES, UPGRADE_COST,
    UPGRADE_MATERIALS, UPGRADE_TECH, Recipe,
)
from translations import tr

Position = tuple[int, int]
WORLD_W, WORLD_H = 60, 40
STEP = 0.1
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
def material_list(stock: dict) -> str:
    return ", ".join(f"{tr(ITEM_LABELS[item])} ×{count}" for item, count in stock.items())


# Place a miner on the highlighted ground. Deposits are infinite.
DEPOSITS = frozenset({
    (3, 5), (4, 5), (5, 5), (3, 6), (4, 6), (4, 7),
    (4, 12), (5, 12), (5, 13), (6, 13), (5, 14),
    (14, 4), (15, 3), (15, 4), (16, 4), (16, 5),
    (17, 12), (18, 11), (18, 12), (19, 12),
    (24, 6), (24, 7), (25, 7), (26, 7), (25, 8),
    (23, 16), (24, 16), (25, 16), (24, 17),
})
NEW_MINERALS = {
    "copper_ore": {(4, 9), (5, 9), (6, 9), (5, 10), (12, 4), (13, 4), (13, 5),
                   (20, 15), (21, 15), (21, 16)},
    "coal": {(11, 8), (12, 8), (12, 9), (13, 9), (8, 13), (9, 13), (9, 14),
             (22, 5), (23, 5), (22, 6)},
}
NEW_MINERALS["copper_ore"].update({(29, 9), (30, 9), (31, 9), (30, 10), (29, 28), (30, 28)})
NEW_MINERALS["coal"].update({(35, 22), (36, 22), (36, 23), (37, 23), (49, 27)})
NEW_MINERALS["quartz"] = {(45, 13), (46, 13), (46, 14), (47, 14), (47, 13), (53, 31), (54, 31)}
MINERALS = {pos: item for item, positions in NEW_MINERALS.items() for pos in positions}
DEPOSITS = DEPOSITS.union(MINERALS, {(31, 17), (32, 17), (32, 18), (47, 25), (48, 25), (48, 26), (25, 31), (26, 31)})
MINER_RECIPE = {recipe.product: i for i, recipe in enumerate(RECIPES["miner"])}
GUIDE = (
    ((4, 6), "miner", 0), ((5, 6), "belt", 0), ((6, 6), "furnace", 0),
    ((7, 6), "belt", 0), ((8, 6), "assembler", 0), ((9, 6), "belt", 0),
    ((10, 6), "storage", 0),
)


def offset(pos: Position, direction: int) -> Position:
    dx, dy = DIRS[direction]
    return pos[0] + dx, pos[1] + dy


def in_world(pos: Position) -> bool:
    x, y = pos
    return 0 <= x < WORLD_W and 0 <= y < WORLD_H


@dataclass
class Machine:
    kind: str
    direction: int
    recipe: int = 0
    craft_steps_left: int = 0
    cooldown: int = 0
    next_input: int = 0
    inputs: Counter = field(default_factory=Counter)
    outputs: Counter = field(default_factory=Counter)
    storage: Counter = field(default_factory=Counter)
    branch: int = 0
    level: int = 1
    transport_phase: int = 0
    filter_item: str = ''
    controlled: bool = False
    reserve: int = 0
    paused: bool = False

    @property
    def plan(self) -> Recipe:
        return RECIPES[self.kind][self.recipe]

    @property
    def capacity(self) -> int:
        return STORAGE_LIMIT * self.level

    @property
    def full(self) -> bool:
        return self.kind == "storage" and self.storage.total() >= self.capacity

    @property
    def belt_delay(self) -> float:
        return (7 - self.level) / 2

    def input_direction_ok(self, side: int) -> bool:
        if self.kind == "extractor":
            return False
        if self.kind in ("storage", "seller"):
            return True
        if self.kind == "splitter":
            return side == (self.direction + 2) % 4
        return self.kind != "miner" and side != self.direction

    def accepts(self, item: str, side: int) -> bool:
        if not self.input_direction_ok(side):
            return False
        if self.kind == "seller":
            return self.cooldown == 0
        if self.kind in TRANSPORT:
            return not self.outputs
        if self.kind == "storage":
            return not self.full
        return self.has_room(item)

    def routes(self, item: str):
        if self.kind == "splitter" and self.filter_item:
            turn = int(item == self.filter_item)
            return ((self.direction + turn) % 4,)
        return self.output_directions

    @property
    def output_directions(self):
        if self.kind == "splitter":
            return ((self.direction + self.branch) % 4, (self.direction + 1 - self.branch) % 4)
        return (self.direction,)

    def has_room(self, item: str) -> bool:
        return item in self.plan.inputs and self.inputs[item] < INPUT_LIMIT

    def receive(self, item: str) -> None:
        if self.kind in TRANSPORT:
            self.outputs[item] = 1
            delay = 7 - self.level
            self.cooldown = (delay + self.transport_phase) // 2
            self.transport_phase = 1 - self.transport_phase
        elif self.kind == "storage":
            self.storage[item] += 1
        else:
            self.inputs[item] += 1


def upgrade_cost(machine: Machine) -> tuple[int, dict[str, int]]:
    level = machine.level
    if level == 1 and machine.kind in ("storage", *TRANSPORT):
        return 200, {"part": 2}
    if level == 1:
        return UPGRADE_COST, UPGRADE_MATERIALS
    return (
        (450, {"gear": 3, "part": 3}),
        (650, {"steel": 4, "part": 4}),
        (900, {"circuit": 3, "part": 5}),
    )[level - 2]


def remove_units(stock: Counter, item: str, count: int) -> None:
    stock[item] -= count
    if not stock[item]:
        del stock[item]


@dataclass
class Factory:
    deposits: frozenset[Position] = DEPOSITS
    machines: dict[Position, Machine] = field(default_factory=dict)
    player_inventory: Counter = field(default_factory=Counter)
    credits: int = START_CREDITS
    shipped_units: int = 0
    contract_index: int = 0
    upgraded: bool = False
    steps: int = 0
    starter_shipped: bool = False
    unlocked: set[str] = field(default_factory=set)
    total_sales: int = 0
    ending_seen: bool = False
    arrivals: dict[Position, tuple[Position, str]] = field(default_factory=dict)

    def mineral_at(self, pos: Position) -> str:
        return MINERALS.get(pos, "ore") if pos in self.deposits else ""

    def placement_error(self, pos: Position, kind: str) -> str:
        if not in_world(pos):
            return tr("Outside the factory.")
        if pos in self.machines:
            return tr("Tile occupied. Rotate or dismantle the existing machine.")
        if kind == "miner" and pos not in self.deposits:
            return tr("A miner must be placed on a mineral deposit.")
        mineral = self.mineral_at(pos)
        if kind == "miner" and mineral in TECHS and mineral not in self.unlocked:
            return tr("Research {item} mining first [M].", item=tr(ITEM_LABELS[mineral]))
        if kind in ("extractor", "seller") and not self.starter_complete:
            return tr("Complete the first shipping contract.")
        if kind == "seller" and "automation" not in self.unlocked:
            return tr("Research {tech} first.", tech=tr(TECH_NAMES["automation"]))
        return self.cost_error(COST[kind], BUILD_MATERIALS.get(kind, {}))

    def cost_rows(self, cost, materials):
        """Each row contains a label, carried amount and required amount."""
        yield "CREDITS", self.credits, cost
        for item, needed in materials.items():
            yield ITEM_LABELS[item], self.player_inventory[item], needed

    def cost_error(self, cost, materials):
        missing = [f"{tr(label)} ×{needed - have}" for label, have, needed
                   in self.cost_rows(cost, materials) if have < needed]
        return tr("Short by: {items}", items=", ".join(missing)) if missing else ""

    def pay(self, cost, materials):
        self.credits -= cost
        for item, count in materials.items():
            remove_units(self.player_inventory, item, count)

    def place(self, pos: Position, kind: str, direction: int) -> str:
        error = self.placement_error(pos, kind)
        if error:
            return error
        recipe = MINER_RECIPE[self.mineral_at(pos)] if kind == "miner" else 0
        self.machines[pos] = Machine(kind, direction, recipe)
        self.pay(COST[kind], BUILD_MATERIALS.get(kind, {}))
        return tr("Built {machine}.", machine=tr(LABELS[kind]))

    def dismantle(self, pos: Position) -> str:
        machine = self.machines.pop(pos, None)
        if machine is None:
            return tr("No machine on this tile.")
        self.arrivals.pop(pos, None)
        self.player_inventory.update(machine.inputs)
        self.player_inventory.update(machine.outputs)
        self.player_inventory.update(machine.storage)
        if machine.controlled:
            self.player_inventory["module"] += 1
        if machine.craft_steps_left:
            self.player_inventory.update(machine.plan.inputs)
        refund = COST[machine.kind]
        self.credits += refund
        self.player_inventory.update(BUILD_MATERIALS.get(machine.kind, {}))
        return tr("Dismantled {machine}. +{cost} credits. Materials recovered.",
                  machine=tr(LABELS[machine.kind]), cost=refund)

    def rotate(self, pos: Position) -> str:
        machine = self.machines[pos]
        if machine.kind == "storage":
            return tr("Warehouses receive from all four sides.")
        machine.direction = (machine.direction + 1) % 4
        return tr("Rotated {machine}.", machine=tr(LABELS[machine.kind]))

    def rotate_to(self, pos: Position, direction: int) -> str:
        machine = self.machines[pos]
        machine.direction = direction
        return tr("Rotated {machine}.", machine=tr(LABELS[machine.kind]))

    def incoming_items(self, pos: Position) -> set[str]:
        """Cargo at adjacent outputs that actually face a valid input on this tile."""
        receiver = self.machines[pos]
        incoming = set()
        for side in range(4):
            if not receiver.input_direction_ok(side):
                continue
            start = offset(pos, side)
            sender = self.machines.get(start)
            if not sender:
                continue
            item = next(iter(sender.outputs), None)
            if sender.kind == "extractor" and not sender.paused and sender.filter_item:
                warehouse = self.source_warehouse(start, sender)
                if warehouse and warehouse.storage[sender.filter_item] > sender.reserve:
                    item = sender.filter_item
            if item and (side + 2) % 4 in sender.routes(item):
                incoming.add(item)
        return incoming

    def switch_recipe(self, pos: Position, index: int | None = None) -> str:
        machine = self.machines[pos]
        if len(RECIPES.get(machine.kind, ())) < 2 or machine.kind == "miner":
            return tr("This machine has no alternate recipe.")
        plans = RECIPES[machine.kind]
        if index is None:
            available = [i for i, plan in enumerate(plans) if not plan.required_tech or plan.required_tech in self.unlocked]
            index = next((i for i in available if i > machine.recipe), available[0])
        if index == machine.recipe:
            return tr("Already selected")
        if not 0 <= index < len(plans):
            raise ValueError("Unknown recipe index")
        tech = plans[index].required_tech
        if tech and tech not in self.unlocked:
            return tr("Research {tech} first.", tech=tr(TECH_NAMES[tech]))
        was_working = machine.craft_steps_left > 0
        if was_working:
            self.player_inventory.update(machine.plan.inputs)
            machine.craft_steps_left = 0
        machine.recipe = index
        for item, count in tuple(machine.inputs.items()):
            if item not in machine.plan.inputs:
                self.player_inventory[item] += count
                del machine.inputs[item]
        message = "Recipe set to {recipe}. Active batch materials recovered." if was_working else "Recipe set to {recipe}."
        return tr(message, recipe=tr(machine.plan.name))

    def withdraw(self, pos: Position, item: str, amount: int | None = 5) -> str:
        machine = self.machines[pos]
        if machine.kind != "storage" or machine.storage[item] == 0:
            return tr("That item is not in this warehouse.")
        stock = machine.storage[item]
        count = stock if amount is None else max(0, min(amount, stock))
        if not count:
            return tr("That item is not in this warehouse.")
        remove_units(machine.storage, item, count)
        self.player_inventory[item] += count
        return tr("Took {item} ×{count} from the warehouse.", item=tr(ITEM_LABELS[item]), count=count)

    def withdraw_all(self, pos: Position) -> str:
        warehouse = self.machines[pos]
        if warehouse.kind != "storage" or not warehouse.storage:
            return tr("No warehouse stock to withdraw.")
        count = warehouse.storage.total()
        self.player_inventory.update(warehouse.storage)
        warehouse.storage.clear()
        return tr("Moved {count} items to carried inventory.", count=count)

    def deposit(self, pos: Position, item: str, amount: int | None = 5) -> str:
        machine = self.machines[pos]
        if machine.kind == "storage":
            stock, room = machine.storage, machine.capacity - machine.storage.total()
        elif machine.kind in RECIPES and machine.has_room(item):
            stock, room = machine.inputs, INPUT_LIMIT - machine.inputs[item]
        else:
            return tr("This machine cannot accept that material.")
        available = min(self.player_inventory[item], room)
        count = available if amount is None else min(amount, available)
        if count <= 0:
            return tr("No material in your inventory or no free space.")
        remove_units(self.player_inventory, item, count)
        stock[item] += count
        return tr("Loaded {item} ×{count}.", item=tr(ITEM_LABELS[item]), count=count)

    def research_error(self, mineral: str) -> str:
        if mineral in self.unlocked:
            return tr("Already researched.")
        cost, materials, prerequisite = TECHS[mineral]
        if not self.starter_complete:
            return tr("Complete the first shipping contract.")
        if prerequisite and prerequisite not in self.unlocked:
            return tr("Research {tech} first.", tech=tr(TECH_NAMES[prerequisite]))
        return self.cost_error(cost, materials)

    def research(self, mineral: str) -> str:
        error = self.research_error(mineral)
        if error:
            return error
        cost, materials, _ = TECHS[mineral]
        self.pay(cost, materials)
        self.unlocked.add(mineral)
        return tr("Research complete: {tech}.", tech=tr(TECH_NAMES[mineral]))

    def sell(self, item: str, quantity: int) -> str:
        name = tr(ITEM_LABELS[item])
        if quantity <= 0 or self.player_inventory[item] < quantity:
            return tr("Take this item out of a warehouse first.")
        remove_units(self.player_inventory, item, quantity)
        credits = self.record_sale(item, quantity)
        return tr("Sold {item} ×{count} for {credits} credits.", item=name, count=quantity, credits=credits)

    def record_sale(self, item: str, quantity: int) -> int:
        income = SHOP_SELL[item] * quantity
        self.credits += income
        self.total_sales += income
        return income

    def source_warehouse(self, pos, machine):
        source = self.machines.get(offset(pos, (machine.direction + 2) % 4))
        return source if source and source.kind == "storage" else None

    def extractor_status(self, pos, machine):
        if machine.paused:
            return tr("Extraction paused")
        if not machine.filter_item:
            return tr("Choose an item to extract")
        source = self.source_warehouse(pos, machine)
        if not source:
            return tr("Place a warehouse behind the extractor")
        if not source.storage[machine.filter_item]:
            return tr("Waiting for warehouse stock")
        if source.storage[machine.filter_item] <= machine.reserve:
            return tr("Reserve reached")
        return self.output_status(pos, machine.direction, machine.filter_item)

    def configure_reserve(self, pos):
        machine = self.machines[pos]
        if not machine.controlled:
            if not self.player_inventory["module"]:
                return tr("Requires one carried control module")
            remove_units(self.player_inventory, "module", 1)
            machine.controlled = True
        else:
            source = self.source_warehouse(pos, machine)
            options = [n for n in RESERVES if n != 100 or source and source.capacity >= n]
            machine.reserve = next((n for n in options if n > machine.reserve), 0)
        return tr("Keep {count} in storage", count=machine.reserve)

    @property
    def starter_complete(self) -> bool:
        return self.starter_shipped or self.contract_index > 0

    def ship_starter(self, item: str) -> str:
        if self.starter_complete or item not in STARTER_ORES:
            return tr("First shipment already complete.")
        if self.warehouse_stock(item) < STARTER_QUANTITY:
            return tr("Warehouses need {item} ×{count}.",
                      item=tr(ITEM_LABELS[item]), count=STARTER_QUANTITY)
        self.remove_warehouse_stock(item, STARTER_QUANTITY)
        self.starter_shipped = True
        self.shipped_units += STARTER_QUANTITY
        self.credits += STARTER_REWARD
        return tr("First shipment complete. +{credits} credits.", credits=STARTER_REWARD)

    def set_filter(self, pos: Position, item: str) -> str:
        machine = self.machines[pos]
        machine.filter_item = item
        return tr("Filter: {item}", item=tr(ITEM_LABELS[item])) if item else tr("Filter cleared.")

    def warehouse_stock(self, item: str) -> int:
        return sum(m.storage[item] for m in self.machines.values() if m.kind == "storage")

    @property
    def warehouse_parts(self) -> int:
        return self.warehouse_stock("part")

    def remove_warehouse_stock(self, item: str, amount: int) -> None:
        pending = amount
        for _, machine in sorted(self.machines.items()):
            if machine.kind != "storage" or not machine.storage[item]:
                continue
            count = min(pending, machine.storage[item])
            remove_units(machine.storage, item, count)
            pending -= count
            if not pending:
                break

    def dispatch(self) -> str:
        if self.contract_index == len(ORDERS):
            return tr("All contracts completed.")
        item, amount, reward = ORDERS[self.contract_index]
        if self.warehouse_stock(item) < amount:
            return tr("Warehouses need {item} ×{count}.", item=tr(ITEM_LABELS[item]), count=amount)
        self.remove_warehouse_stock(item, amount)
        self.contract_index += 1
        self.shipped_units += amount
        self.credits += reward
        if self.contract_index == len(ORDERS):
            return tr("Final contract shipped. +{reward} credits.", reward=reward)
        return tr("Shipped {item} ×{count}. +{reward} credits.",
                  item=tr(ITEM_LABELS[item]), count=amount, reward=reward)

    def upgrade(self, pos: Position) -> str:
        machine = self.machines.get(pos)
        if machine is None:
            return tr("Select a machine to upgrade.")
        if machine.level >= MAX_LEVEL:
            return tr("Maximum level reached.")
        target = machine.level + 1
        tech = UPGRADE_TECH.get(target)
        cost, materials = upgrade_cost(machine)
        error = self.cost_error(cost, materials)
        if tech and tech not in self.unlocked:
            research = tr("Research {tech} first.", tech=tr(TECH_NAMES[tech]))
            return f"{research}  {error}".strip()
        if error:
            return error
        self.pay(cost, materials)
        machine.level = target
        return tr("{machine} upgraded to level {level}.", machine=tr(LABELS[machine.kind]), level=target)

    def belt_inputs(self, pos: Position, machine: Machine):
        sides = []
        for side in range(4):
            if not machine.input_direction_ok(side):
                continue
            neighbor = self.machines.get(offset(pos, side))
            if neighbor and neighbor.kind not in ("storage", "seller") and (side + 2) % 4 in neighbor.output_directions:
                sides.append(side)
        return tuple(sides) or ((machine.direction + 2) % 4,)

    def output_status(self, pos: Position, direction: int, item: str) -> str:
        receiver = self.machines.get(offset(pos, direction))
        if receiver is None:
            return tr("No connected machine")
        side = (direction + 2) % 4
        if not receiver.input_direction_ok(side):
            return tr("Input faces another way")
        if receiver.accepts(item, side):
            return tr("Ready to transfer")
        if receiver.kind in RECIPES and item not in receiver.plan.inputs:
            return tr("Material does not match recipe")
        return tr("Next machine is full")

    def craft(self, machine: Machine) -> None:
        plan = machine.plan
        if machine.craft_steps_left > 0:
            machine.craft_steps_left -= 1
            if machine.craft_steps_left == 0:
                machine.outputs[plan.product] += 1
            return
        # A batch reserves one slot in this machine's output buffer at start.
        if machine.outputs.total() >= OUTPUT_LIMIT:
            return
        if not all(machine.inputs[item] >= count for item, count in plan.inputs.items()):
            return
        for item, count in plan.inputs.items():
            remove_units(machine.inputs, item, count)
        machine.craft_steps_left = self.recipe_steps(machine)

    def recipe_steps(self, machine: Machine, level: int | None = None) -> int:
        steps = machine.plan.steps
        if self.upgraded and machine.kind != "miner":
            steps = (steps * 3 + 3) // 4
        factor = (100, 75, 62, 50, 38)[(level or machine.level) - 1]
        return (steps * factor + 99) // 100

    def transfer_proposals(self):
        # Gather moves against the same state. One receiver takes at most one
        # item per step, and a belt cannot send an item it just received.
        proposals: dict[Position, list[tuple[Position, str, int]]] = {}
        for pos, sender in self.machines.items():
            if sender.cooldown:
                continue
            if sender.kind == "extractor":
                item = sender.filter_item
                warehouse = self.source_warehouse(pos, sender)
                if sender.paused or not item or not warehouse or warehouse.storage[item] <= sender.reserve:
                    continue
            elif sender.outputs:
                item = next(iter(sender.outputs))
            else:
                continue
            for direction in sender.routes(item):
                target = offset(pos, direction)
                receiver = self.machines.get(target)
                side = (direction + 2) % 4
                if receiver is not None and receiver.accepts(item, side):
                    proposals.setdefault(target, []).append((pos, item, side))
                    break
        return proposals

    def transfer_items(self):
        for target, candidates in self.transfer_proposals().items():
            receiver = self.machines[target]
            source, item, side = min(candidates, key=lambda move: (move[2] - receiver.next_input) % 4)
            sender = self.machines[source]
            if sender.kind == "extractor":
                warehouse = self.source_warehouse(source, sender)
                # Another extractor can withdraw from the same warehouse this tick.
                if warehouse.storage[item] <= sender.reserve:
                    continue
                remove_units(warehouse.storage, item, 1)
                sender.cooldown = 6 - sender.level
            else:
                remove_units(sender.outputs, item, 1)
            if sender.kind == "splitter":
                sent_direction = (side + 2) % 4
                sender.branch = 1 - int(sent_direction != sender.direction)
            if receiver.kind == "seller":
                self.record_sale(item, 1)
                receiver.cooldown = 6 - receiver.level
            else:
                receiver.receive(item)
            receiver.next_input = (side + 1) % 4
            self.arrivals[target] = (source, item)

    def step(self) -> None:
        self.steps += 1
        self.arrivals.clear()
        for machine in self.machines.values():
            if machine.kind in RECIPES:
                self.craft(machine)
            elif machine.cooldown:
                machine.cooldown -= 1
        self.transfer_items()

    @classmethod
    def sample(cls) -> "Factory":
        factory = cls(unlocked={"ore"})
        for pos, kind, direction in GUIDE:
            factory.place(pos, kind, direction)
        return factory
