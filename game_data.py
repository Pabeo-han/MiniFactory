"""Equipment, recipes, prices and progression for MiniFactory."""

from dataclasses import dataclass
from functools import cache

# Build-menu order also defines the ten original keyboard shortcuts.
EQUIPMENT = {
    "belt": ("Conveyor", 20), "miner": ("Miner", 120), "furnace": ("Furnace", 160),
    "assembler": ("Assembler", 220), "storage": ("Warehouse", 100),
    "splitter": ("Splitter", 50), "press": ("Gear press", 120), "drawer": ("Wire drawer", 150),
    "forge": ("Alloy forge", 220), "electronics": ("Circuit maker", 280),
    "extractor": ("Warehouse extractor", 100), "seller": ("Auto seller", 150),
}
TYPES = tuple(EQUIPMENT)
LABELS = {kind: spec[0] for kind, spec in EQUIPMENT.items()}
COST = {kind: spec[1] for kind, spec in EQUIPMENT.items()}
ITEM_LABELS = {
    "ore": "Iron ore", "plate": "Iron plate", "part": "Machine part",
    "copper_ore": "Copper ore", "copper": "Copper ingot", "coal": "Coal",
    "gear": "Gear", "wire": "Copper wire", "steel": "Steel", "circuit": "Circuit",
    "quartz": "Quartz", "silicon": "Silicon", "module": "Control module",
}
ITEMS = tuple(ITEM_LABELS)
BUILD_MATERIALS = {
    "extractor": {"copper": 2}, "seller": {"copper": 3},
    "splitter": {"plate": 2}, "press": {"plate": 4}, "drawer": {"plate": 4, "copper": 2},
    "forge": {"plate": 6, "coal": 3}, "electronics": {"gear": 2, "wire": 4, "steel": 2},
}
TRANSPORT = ("belt", "splitter")
INPUT_LIMIT = 6  # Per material.
OUTPUT_LIMIT = 4
STORAGE_LIMIT = 80
BELT_TIME = 3
START_CREDITS = 1000
ORDERS = (("part", 10, 1200), ("part", 25, 3000), ("part", 50, 6000),
          ("steel", 8, 800), ("circuit", 10, 9000), ("silicon", 12, 2400))
UPGRADE_COST = 300
UPGRADE_MATERIALS = {"plate": 2, "part": 2}
MAX_LEVEL = 5
TRANSFER_AMOUNTS = {"1": 1, "5": 5, "10": 10, "all": None}
UPGRADE_TECH = {3: "processing", 4: "automation", 5: "precision"}
TECH_NAMES = {
    "ore": "Iron mining",
    "processing": "Advanced processing", "automation": "Factory automation research",
    "precision": "Precision engineering", "quartz": "Quartz mining",
}
TECHS = {
    "ore": (200, {"copper": 3}, ""),
    "processing": (350, {"plate": 6, "gear": 2}, "ore"),
    "automation": (550, {"wire": 6, "steel": 3}, "processing"),
    "precision": (800, {"circuit": 4}, "automation"),
    "quartz": (600, {"circuit": 2}, ""),
}
STARTER_ORES = ("copper_ore", "coal")
MINING_TECH = ("ore", "quartz")
STARTER_QUANTITY = 10
STARTER_REWARD = 450
SALES_TARGET = 500_000
RESERVES = (0, 25, 50, 100)
SHOP_SELL = {
    "ore": 10, "plate": 30, "part": 95, "copper_ore": 10, "copper": 28, "coal": 10,
    "gear": 85, "wire": 45, "steel": 80, "circuit": 800, "quartz": 35, "silicon": 150,
    "module": 3000,
}


@dataclass(frozen=True)
class Recipe:
    name: str
    inputs: dict[str, int]
    product: str
    steps: int
    required_tech: str = ""


RECIPES = {
    "miner": (
        Recipe("Iron mining", {}, "ore", 9),
        Recipe("Copper mining", {}, "copper_ore", 9),
        Recipe("Coal mining", {}, "coal", 10),
        Recipe("Quartz mining", {}, "quartz", 12),
    ),
    "furnace": (
        Recipe("Iron smelting", {"ore": 1}, "plate", 12),
        Recipe("Copper smelting", {"copper_ore": 1}, "copper", 12),
        Recipe("Silicon refining", {"quartz": 1, "coal": 1}, "silicon", 20),
        Recipe("Coal-fired copper", {"copper_ore": 1, "coal": 1}, "copper", 6),
        Recipe("Coal-fired iron", {"ore": 1, "coal": 1}, "plate", 6, "ore"),
    ),
    "assembler": (
        Recipe("Standard parts", {"plate": 2}, "part", 18),
        Recipe("Ore-assisted parts", {"plate": 1, "ore": 1}, "part", 14),
    ),
    "press": (Recipe("Gear pressing", {"plate": 2}, "gear", 15),),
    "drawer": (Recipe("Wire drawing", {"copper": 1}, "wire", 11),),
    "forge": (Recipe("Steelmaking", {"plate": 1, "coal": 1}, "steel", 17),),
    "electronics": (Recipe("Circuit assembly", {"gear": 1, "wire": 2, "steel": 1}, "circuit", 22),
                    Recipe("Module assembly", {"circuit": 2, "silicon": 1, "steel": 1}, "module", 32)),
}


@cache
def recipe_chain(product: str) -> tuple:
    """Return prerequisites in production order, including alternate final recipes."""
    result = []
    seen = set()

    def collect(item):
        if item in seen:
            return
        seen.add(item)
        options = [(kind, plan) for kind, plans in RECIPES.items() for plan in plans
                   if plan.product == item]
        selected = options if item == product else options[:1]
        for _, plan in selected:
            for ingredient in plan.inputs:
                collect(ingredient)
        result.extend(selected)

    collect(product)
    return tuple(result)
