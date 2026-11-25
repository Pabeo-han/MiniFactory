"""Preset demonstrating the complete circuit supply chain."""

from collections import Counter

from simulation import BUILD_MATERIALS, ORDERS, TECHS, Factory


def advanced_sample() -> Factory:
    # First three contracts are complete so this example can ship steel and circuits.
    factory = Factory(credits=8500, contract_index=3, unlocked=set(TECHS), shipped_units=sum(order[1] for order in ORDERS[:3]))
    layout = [
        ((4, 6), "miner", 0), ((5, 6), "belt", 0), ((6, 6), "furnace", 0),
        ((7, 6), "belt", 0), ((8, 6), "belt", 1),
        *[((8, y), "belt", 1) for y in range(7, 10)],
        *[((x, 10), "belt", 0) for x in range(8, 14)],
        ((14, 10), "press", 0), ((15, 10), "belt", 0), ((16, 10), "belt", 0),
        ((12, 4), "miner", 0), ((13, 4), "furnace", 0), ((14, 4), "belt", 0),
        ((15, 4), "drawer", 0), ((16, 4), "belt", 0), ((17, 4), "belt", 1),
        *[((17, y), "belt", 1) for y in range(5, 10)],
        ((5, 13), "miner", 0), ((6, 13), "belt", 0), ((7, 13), "furnace", 0),
        *[((x, 13), "belt", 0) for x in range(8, 17)],
        ((9, 14), "miner", 0), *[((x, 14), "belt", 0) for x in range(10, 17)],
        ((17, 14), "belt", 3), ((17, 13), "forge", 3), ((17, 12), "splitter", 3),
        ((18, 12), "storage", 0), ((17, 11), "belt", 3),
        ((17, 10), "electronics", 0), ((18, 10), "belt", 0), ((19, 10), "storage", 0),
    ]
    for _, kind, _ in layout:
        factory.player_inventory.update(Counter(BUILD_MATERIALS.get(kind, {})))
    for pos, kind, direction in layout:
        factory.place(pos, kind, direction)
    factory.switch_recipe((13, 4))
    return factory
