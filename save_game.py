"""One local JSON save slot, written by atomic replacement."""

import json
import os
import sys
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from translations import tr

from simulation import (
    BELT_TIME, INPUT_LIMIT, ITEMS, ORDERS, OUTPUT_LIMIT, RECIPES,
    RESERVES, DEPOSITS, TECHS, STARTER_QUANTITY, MAX_LEVEL, MINER_RECIPE, TRANSPORT, TYPES, Factory, Machine, in_world,
)

VERSION = 7
BUFFERS = ("inputs", "outputs", "storage")


class SaveError(ValueError):
    """A save version or state cannot be loaded."""


def save_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / "MiniFactory" / "factory.json"


def write_save(path: Path, factory: Factory) -> None:
    state = {
        "version": VERSION,
        "credits": factory.credits,
        "revenue": factory.total_sales,
        "ending_seen": factory.ending_seen,
        "dispatched": factory.shipped_units,
        "order": factory.contract_index,
        "upgraded": factory.upgraded,
        "steps": factory.steps,
        "starter_shipped": factory.starter_shipped,
        "unlocked": sorted(factory.unlocked),
        "deposits": sorted(factory.deposits),
        "player": dict(factory.player_inventory),
        "machines": [
            {
                "position": pos,
                "kind": machine.kind,
                "direction": machine.direction,
                "recipe": machine.recipe,
                "remaining": machine.craft_steps_left,
                "cooldown": machine.cooldown,
                "next_input": machine.next_input,
                "branch": machine.branch,
                "transport_phase": machine.transport_phase,
                "level": machine.level,
                "filter_item": machine.filter_item,
                "reserve": machine.reserve, "controlled": machine.controlled, "paused": machine.paused,
                **{name: dict(getattr(machine, name)) for name in BUFFERS},
            }
            for pos, machine in sorted(factory.machines.items())
        ],
    }
    write_json(path, state)


def write_json(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # Close before replacing so Windows releases the open file handle.
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(state, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def integer_in(value, low: int, high: int | None = None) -> bool:
    return type(value) is int and value >= low and (high is None or value <= high)


def validate_buffers(machine: Machine) -> None:
    if machine.kind in TRANSPORT:
        valid = not machine.storage and not machine.inputs and machine.outputs.total() <= 1
        valid = valid and (machine.cooldown == 0 or bool(machine.outputs))
    elif machine.kind in ("seller", "extractor"):
        valid = not any((machine.inputs, machine.outputs, machine.storage))
    elif machine.kind == "storage":
        valid = not machine.inputs and not machine.outputs and machine.storage.total() <= machine.capacity
    else:
        plan = machine.plan
        valid_outputs = {p.product for p in RECIPES[machine.kind]} if machine.kind != "miner" else {plan.product}
        valid = not machine.storage and set(machine.outputs) <= valid_outputs
        valid = valid and machine.outputs.total() + bool(machine.craft_steps_left) <= OUTPUT_LIMIT
        valid = valid and all(
            item in plan.inputs and qty <= INPUT_LIMIT for item, qty in machine.inputs.items()
        )
    if not valid:
        raise SaveError(tr("Invalid machine inventory."))


def read_position(value):
    if (not isinstance(value, list) or len(value) != 2
            or not all(integer_in(coordinate, 0) for coordinate in value)
            or not in_world(tuple(value))):
        raise SaveError(tr("Invalid tile coordinates."))
    return tuple(value)


def read_stock(value) -> Counter:
    if not isinstance(value, dict) or any(
        item not in ITEMS or not integer_in(count, 1) for item, count in value.items()
    ):
        raise SaveError(tr("Invalid inventory."))
    return Counter(value)


def read_machine(data, mineral: str) -> Machine:
    kind = data.get("kind")
    direction = data.get("direction")
    recipe = data.get("recipe")
    craft_steps_left = data.get("remaining")
    cooldown = data.get("cooldown")
    next_input = data.get("next_input")
    branch = data.get("branch", 0)
    level = data.get("level", 1)
    transport_phase = data.get("transport_phase", 0)
    filter_item = data.get("filter_item", "")
    if filter_item != "" and (kind not in ("splitter", "extractor") or filter_item not in ITEMS):
        raise SaveError(tr("Invalid splitter filter."))
    if not (kind in TYPES and integer_in(direction, 0, 3) and integer_in(next_input, 0, 3)):
        raise SaveError(tr("Invalid machine type or direction."))
    plans = RECIPES.get(kind, ())
    if not integer_in(recipe, 0, max(0, len(plans) - 1)):
        raise SaveError(tr("Invalid machine recipe."))
    max_steps = plans[recipe].steps if plans else 0
    if not (integer_in(craft_steps_left, 0, max_steps)
            and integer_in(cooldown, 0, 5 if kind in ("extractor", "seller") else BELT_TIME if kind in TRANSPORT else 0)
            and integer_in(branch, 0, int(kind == "splitter"))
            and integer_in(level, 1, MAX_LEVEL)
            and integer_in(transport_phase, 0, int(kind in TRANSPORT))
            and (kind != "miner" or MINER_RECIPE.get(mineral) == recipe)):
        raise SaveError(tr("Invalid machine timing or terrain."))
    reserve = data.get("reserve", 0)
    controlled = data.get("controlled", False)
    paused = data.get("paused", False)
    if (not integer_in(reserve, 0) or reserve not in RESERVES or type(controlled) is not bool
            or type(paused) is not bool or (reserve and not controlled)
            or ((controlled or paused) and kind != "extractor")):
        raise SaveError(tr("Invalid machine record."))
    stocks = {name: read_stock(data.get(name)) for name in BUFFERS}
    machine = Machine(kind, direction, recipe, craft_steps_left, cooldown, next_input,
                      branch=branch, level=level, transport_phase=transport_phase, filter_item=filter_item, reserve=reserve, controlled=controlled, paused=paused, **stocks)
    validate_buffers(machine)
    return machine


def read_save(path: Path) -> Factory:
    try:
        with path.open(encoding="utf-8") as file:
            state = json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(tr("No saved factory yet.")) from None
    except (ValueError, RecursionError) as error:
        raise SaveError(tr("Unreadable JSON save file.")) from error

    if not isinstance(state, dict) or not integer_in(state.get("version"), 1, VERSION):
        raise SaveError(tr("Unsupported save version."))
    credits, shipped_units, order, upgraded, steps = (
        state.get(name) for name in ("credits", "dispatched", "order", "upgraded", "steps")
    )
    if not (integer_in(credits, 0) and integer_in(shipped_units, 0)
            and integer_in(order, 0, len(ORDERS)) and type(upgraded) is bool
            and integer_in(steps, 0)):
        raise SaveError(tr("Invalid factory progress."))
    starter_shipped = state.get("starter_shipped", False)
    if (type(starter_shipped) is not bool or
            shipped_units != sum(amount for _, amount, _ in ORDERS[:order]) + STARTER_QUANTITY * starter_shipped
            or (upgraded and not order)):
        raise SaveError(tr("Invalid contract progress."))

    deposit_data, machines = state.get("deposits"), state.get("machines")
    if not isinstance(deposit_data, list) or not isinstance(machines, list):
        raise SaveError(tr("Invalid factory layout."))
    deposits = frozenset(read_position(pos) for pos in deposit_data)
    unlock_data = state.get("unlocked", [])
    known_research = set(TECHS) | {"copper_ore", "coal"} if state["version"] < 4 else TECHS
    if not isinstance(unlock_data, list) or any(
        not isinstance(item, str) or item not in known_research for item in unlock_data
    ):
        raise SaveError(tr("Invalid research data."))
    unlocked = set(unlock_data).intersection(TECHS)
    if state["version"] < 5:
        unlocked.add("ore")
    if state["version"] < 3:
        deposits = deposits.union(DEPOSITS)
    total_sales = state.get("revenue", 0)
    ending_seen = state.get("ending_seen", False)
    if not integer_in(total_sales, 0) or type(ending_seen) is not bool:
        raise SaveError(tr("Invalid factory progress."))
    if state["version"] < 7:
        credits *= 10
        ending_seen = False  # The new sales milestone has its own ending.
    factory = Factory(deposits, total_sales=total_sales, ending_seen=ending_seen, player_inventory=read_stock(state.get("player")), credits=credits,
                      shipped_units=shipped_units, contract_index=order, upgraded=upgraded, steps=steps,
                      starter_shipped=starter_shipped, unlocked=unlocked)
    for entry in machines:
        if not isinstance(entry, dict):
            raise SaveError(tr("Invalid machine record."))
        pos = read_position(entry.get("position"))
        if pos in factory.machines:
            raise SaveError(tr("More than one machine occupies a tile."))
        mineral = factory.mineral_at(pos)
        machine = read_machine(entry, mineral)
        if state["version"] < 3 and machine.kind == "miner" and mineral in TECHS:
            unlocked.add(mineral)
        factory.machines[pos] = machine
    return factory
