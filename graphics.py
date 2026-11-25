"""Industrial machine artwork and tile-based map rendering."""

from functools import lru_cache
from pathlib import Path
from random import Random

import pygame

PALETTE = {
    "belt": (109, 173, 202),
    "miner": (247, 183, 84),
    "furnace": (244, 132, 93),
    "assembler": (179, 153, 239),
    "storage": (113, 217, 174),
    "splitter": (113, 215, 229),
    "press": (229, 185, 105),
    "drawer": (228, 145, 112),
    "forge": (162, 182, 204),
    "electronics": (114, 219, 166),
    "extractor": (77, 172, 185), "seller": (217, 173, 73),
}
ITEM_COLORS = {
    "ore": (232, 163, 97), "plate": (199, 220, 224), "part": (111, 235, 178),
    "copper_ore": (230, 112, 86), "copper": (245, 164, 124), "coal": (166, 163, 185),
    "gear": (236, 193, 117), "wire": (245, 154, 111), "steel": (163, 192, 231),
    "circuit": (121, 229, 156), "quartz": (209, 169, 231), "silicon": (112, 174, 213),
}
ASSETS = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=64)
def load_sprite(group, name):
    return pygame.image.load(ASSETS / group / f"{name}.png")


def item_sprite(item):
    return load_sprite("items", item)


@lru_cache(maxsize=128)
def machine_sprite(kind, direction=0, active=False, phase=0):
    sprite = load_sprite("machines", kind)
    if active and kind not in ("storage", "belt", "splitter"):
        sprite = sprite.copy()
        pygame.draw.circle(sprite, (20, 47, 41), (27, 130), 10)
        pygame.draw.circle(sprite, (109, 250, 165), (27, 130), 5)
    return pygame.transform.rotate(sprite, -90 * direction) if kind != "storage" else sprite


@lru_cache(maxsize=96)
def ground_sprite(deposit, variant, grid):
    sprite = pygame.Surface((64, 64))
    rng = Random(191 + variant)
    base = ((197, 188, 173), (206, 197, 182), (201, 191, 177), (194, 185, 172))[variant]
    sprite.fill(base)
    for _ in range(510):
        x, y = rng.randrange(64), rng.randrange(64)
        shade = rng.randint(-18, 13)
        color = tuple(channel + shade for channel in base)
        pygame.draw.circle(sprite, color, (x, y), rng.choice((1, 1, 2)))
    if variant in (1, 3):
        pygame.draw.lines(sprite, (158, 148, 132), False,
                          [(0, 42), (9, 43), (15, 38), (25, 40), (33, 31), (45, 30)])
    if grid:
        pygame.draw.line(sprite, (155, 147, 133), (0, 0), (63, 0))
        pygame.draw.line(sprite, (155, 147, 133), (0, 1), (0, 63))
        pygame.draw.line(sprite, (217, 207, 191), (1, 1), (63, 1))
    if deposit:
        light = ITEM_COLORS[deposit]
        dark = tuple(int(c * (0.36 if deposit == "coal" else 0.56)) for c in light)
        for x, y in ((11, 14), (42, 12), (35, 35), (15, 42), (51, 49)):
            x += rng.randrange(-3, 4)
            y += rng.randrange(-3, 4)
            size = rng.randrange(6, 12)
            points = [(x-size, y+2), (x-size//2, y-size), (x+size//2, y-size),
                      (x+size, y+1), (x+size//2, y+size), (x-size//2, y+size//2)]
            pygame.draw.polygon(sprite, (123, 109, 92), [(px+2, py+3) for px, py in points])
            pygame.draw.polygon(sprite, dark, points)
            pygame.draw.polygon(sprite, light, [points[0], points[1], points[2], (x+2, y), (x-2, y+1)])
            pygame.draw.line(sprite, tuple((c + 240) // 2 for c in light), points[1], points[2])
    return sprite


@lru_cache(maxsize=768)
def scaled_sprite(sprite, size):
    return pygame.transform.smoothscale(sprite, size)


def draw_sprite(surface, sprite, rect):
    surface.blit(scaled_sprite(sprite, rect.size), rect)


@lru_cache(maxsize=256)
def connected_belt(direction, inputs, phase=0):
    sprite = pygame.Surface((64, 64), pygame.SRCALPHA)
    directions = ((1, 0), (0, 1), (-1, 0), (0, -1))
    ends = ((63, 32), (32, 63), (0, 32), (32, 0))
    center = (32, 32)
    paths = (*inputs, direction)
    for color, width in (((28, 29, 29), 34), ((109, 105, 94), 30), ((55, 54, 51), 22)):
        pygame.draw.circle(sprite, color, center, width // 2)
        for side in paths:
            pygame.draw.line(sprite, color, center, ends[side], width)
    for side in paths:
        dx, dy = directions[side]
        for distance in range(8 + phase % 3 * 2, 33, 10):
            x, y = 32 + dx * distance, 32 + dy * distance
            pygame.draw.line(sprite, (74, 70, 63), (x - dy * 10, y + dx * 10), (x + dy * 10, y - dx * 10), 2)
        sign = 1 if side == direction else -1
        x, y = 32 + dx * 20, 32 + dy * 20
        pygame.draw.lines(sprite, (247, 191, 79), False,
                          [(x - sign * dx * 4 + dy * 6, y - sign * dy * 4 - dx * 6),
                           (x + sign * dx * 4, y + sign * dy * 4),
                           (x - sign * dx * 4 - dy * 6, y - sign * dy * 4 + dx * 6)], 3)
    return sprite
