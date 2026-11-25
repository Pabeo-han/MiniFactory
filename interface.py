"""Canvas, camera, and interface rendering for MiniFactory."""

import math
from collections import Counter
from pathlib import Path
from functools import lru_cache

import pygame

from game_data import recipe_chain
from tutorial import CHAPTERS, current_chapter
from translations import tr

from graphics import connected_belt, ITEM_COLORS, PALETTE, draw_sprite, ground_sprite, item_sprite, machine_sprite
from simulation import (
    SALES_TARGET, COST, INPUT_LIMIT, ITEMS, ITEM_LABELS, LABELS, ORDERS, OUTPUT_LIMIT, STEP,
    BUILD_MATERIALS, MAX_LEVEL, RECIPES, SHOP_SELL, STARTER_ORES, STARTER_QUANTITY, STARTER_REWARD, STORAGE_LIMIT, TECHS, TECH_NAMES, TRANSFER_AMOUNTS, TRANSPORT, TYPES,
    UPGRADE_TECH, WORLD_H, WORLD_W, DIRS, material_list, upgrade_cost,
)

SIZE = (1280, 800)
MAP = pygame.Rect(16, 150, 901, 454)
MINIMAP = pygame.Rect(MAP.right - 140, MAP.top + 10, 130, 87)
BASE = 43
PANEL_X, PANEL_W = 933, 327
BG = (219, 224, 222)
PANEL = (249, 248, 242)
RAISED = (232, 237, 231)
LINE = (156, 171, 163)
TEXT = (27, 49, 48)
MUTED = (69, 91, 87)
AMBER = (143, 78, 11)
MINT = (12, 111, 94)
RED = (161, 52, 40)
ARROWS = ("→", "↓", "←", "↑")


class Camera:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x, self.y, self.zoom = MAP.x + 5.0, MAP.y + 5.0, 1.0

    @property
    def tile(self):
        return BASE * self.zoom

    def clamp(self):
        # Keep at least three tiles visible when panning to the map edge.
        span = self.tile * 3
        self.x = max(MAP.left + span - WORLD_W * self.tile, min(self.x, MAP.right - span))
        self.y = max(MAP.top + span - WORLD_H * self.tile, min(self.y, MAP.bottom - span))

    def pan(self, horizontal, vertical, dt):
        length = math.hypot(horizontal, vertical) or 1
        speed = 425 * dt / length
        self.x -= speed * horizontal
        self.y -= speed * vertical
        self.clamp()

    def center_on(self, pos, zoom):
        self.zoom = zoom
        self.x = MAP.centerx - (pos[0] + 0.5) * self.tile
        self.y = MAP.centery - (pos[1] + 0.5) * self.tile
        self.clamp()

    def tile_at(self, point):
        if not MAP.collidepoint(point):
            return None
        x = math.floor((point[0] - self.x) / self.tile)
        y = math.floor((point[1] - self.y) / self.tile)
        if 0 <= x < WORLD_W and 0 <= y < WORLD_H:
            return x, y
        return None

    def zoom_at(self, point, steps):
        x, y = point
        world_x, world_y = (x - self.x) / self.tile, (y - self.y) / self.tile
        self.zoom = max(0.45, min(2.2, self.zoom * 1.1 ** max(-20, min(20, steps))))
        self.x, self.y = x - world_x * self.tile, y - world_y * self.tile
        self.clamp()

    def rect(self, pos):
        x, y = pos
        left = round(self.x + x * self.tile)
        top = round(self.y + y * self.tile)
        right = round(self.x + (x + 1) * self.tile)
        bottom = round(self.y + (y + 1) * self.tile)
        return pygame.Rect(left, top, right - left, bottom - top)


class Interface:
    def __init__(self):
        self.canvas = None
        self.buttons = []
        self.resize(SIZE)

    def resize(self, size):
        if self.canvas is not None and self.canvas.get_size() == size:
            return
        self.canvas = pygame.Surface(size)
        self.scale_x = size[0] / SIZE[0]
        self.scale_y = size[1] / SIZE[1]
        self.text_image.cache_clear()
        self.shades = {}
        assets = Path(__file__).resolve().parent / "assets"
        normal = assets / "FactorySans-Regular.otf"
        bold = assets / "FactorySans-Bold.otf"
        self.fonts = {
            name: pygame.font.Font(path, max(1, round(size * self.scale_y)))
            for name, path, size in (
                ("tiny", normal, 12), ("small", normal, 14), ("body", normal, 17),
                ("bold", bold, 17), ("title", bold, 30), ("hero", bold, 52),
                ("mono", normal, 14),
            )
        }

    @lru_cache(maxsize=640)
    def text_image(self, message, color, font):
        return self.fonts[font].render(message, True, color)

    def text(self, message, x, y, color=TEXT, font="body", width=None):
        message = tr(str(message))
        width = round(width * self.scale_x) if width else None
        if width and self.fonts[font].size(message)[0] > width:
            while message and self.fonts[font].size(message + "…")[0] > width:
                message = message[:-1]
            message += "…"
        self.canvas.blit(self.text_image(message, color, font), self.pixel_point((x, y)))

    def pixel_point(self, point):
        return round(point[0] * self.scale_x), round(point[1] * self.scale_y)

    def pixel_rect(self, rect):
        x, y, width, height = rect
        left, top = self.pixel_point((x, y))
        right, bottom = self.pixel_point((x + width, y + height))
        return pygame.Rect(left, top, max(0, right - left), max(0, bottom - top))

    def stroke(self, width):
        return max(1, round(width * self.scale_y)) if width else 0

    def rect(self, color, rect, width=0, *, border_radius=0):
        pygame.draw.rect(self.canvas, color, self.pixel_rect(rect), self.stroke(width),
                         border_radius=self.stroke(border_radius))

    def line(self, color, start, end, width=1):
        pygame.draw.line(self.canvas, color, self.pixel_point(start), self.pixel_point(end),
                         self.stroke(width))

    def circle(self, color, center, radius):
        pygame.draw.circle(self.canvas, color, self.pixel_point(center), self.stroke(radius))

    def sprite(self, sprite, rect):
        draw_sprite(self.canvas, sprite, self.pixel_rect(rect))

    def shade(self, color):
        if color not in self.shades:
            shade = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA)
            shade.fill(color)
            self.shades[color] = shade
        self.canvas.blit(self.shades[color], (0, 0))

    def box(self, rect, fill=PANEL, border=LINE, radius=8):
        self.rect(fill, rect, border_radius=radius)
        if border:
            self.rect(border, rect, 1, border_radius=radius)

    def bar(self, rect, fraction, color=MINT, background=RAISED):
        self.rect(background, rect, border_radius=3)
        if fraction > 0:
            rect = pygame.Rect(rect)
            rect.width = min(rect.width, max(1, round(rect.width * fraction)))
            self.rect(color, rect, border_radius=3)

    def button(self, rect, title, action, mouse, *, enabled=True, accent=False):
        rect = pygame.Rect(rect)
        hover = enabled and rect.collidepoint(mouse)
        fill = (23, 104, 89) if accent else RAISED
        if hover:
            fill = (17, 79, 68) if accent else (212, 225, 217)
        self.box(rect, fill if enabled else PANEL, MINT if accent and enabled else LINE, 6)
        foreground = (251, 252, 243) if accent and enabled else TEXT if enabled else MUTED
        glyph = self.text_image(tr(title), foreground, "small")
        self.canvas.blit(glyph, glyph.get_rect(center=self.pixel_point(rect.center)))
        if enabled:
            self.buttons.append((rect, action))

    def action_at(self, point):
        return next((action for rect, action in reversed(self.buttons) if rect.collidepoint(point)), None)

    def render(self, app, mouse, size=SIZE):
        self.resize(size)
        self.buttons.clear()
        self.canvas.fill(BG)
        if app.in_menu:
            self.draw_menu(app, mouse)
        else:
            self.draw_header(app, mouse)
            self.draw_map(app, mouse)
            self.draw_minimap(app)
            self.draw_guidance(app, mouse)
            self.draw_build_cost(app, mouse)
            self.draw_inspector(app, mouse)
            self.draw_contract(app, mouse)
            self.draw_inventory(app, mouse)
            self.draw_toolbar(app, mouse)
            self.text(app.message, 22, 777, MINT, "small", width=1236)
        if app.overlay:
            self.buttons.clear()
            self.draw_overlay(app, mouse)
        return self.canvas

    def draw_header(self, app, mouse):
        dark, brass = (26, 54, 52), (255, 198, 103)
        self.rect(dark, (0, 0, SIZE[0], 78))
        self.rect(brass, (0, 75, SIZE[0], 3))
        self.sprite(machine_sprite("assembler"), pygame.Rect(19, 13, 48, 48))
        self.text("MiniFactory", 76, 11, PANEL, "title")
        self.text("Factory automation", 78, 47, (177, 211, 193), "small")
        factory = app.factory
        for x, label, value in ((267, "CREDITS", factory.credits),
                                (424, "EQUIPMENT", len(factory.machines)),
                                (550, tr("Sales / {goal:,}", goal=SALES_TARGET), factory.total_sales)):
            self.line((74, 99, 90), (x - 14, 15), (x - 14, 62))
            self.text(label, x, 11, (201, 220, 209), "tiny")
            self.text(f"{value:,}", x, 31, brass if x == 267 else PANEL, "bold")
        self.bar((550, 59, 193, 5), factory.total_sales / SALES_TARGET, brass, (76, 98, 86))
        self.button((795, 21, 125, 35), "Research [Y]", "research-menu", mouse,
                    accent=any(not factory.research_error(t) for t in TECHS))
        self.button((930, 21, 145, 35), "Sales desk [M]", "market", mouse)
        self.button((1092, 21, 169, 35), "Resume [Space]" if app.paused else "Pause [Space]",
                    "pause-game", mouse)

    def draw_map(self, app, mouse, *, menu=False):
        camera = app.menu_camera if menu else app.camera
        factory = app.menu_factory if menu else app.factory
        view = pygame.Rect(0, 0, *SIZE) if menu else MAP
        self.rect((182, 188, 181), view)
        self.canvas.set_clip(self.pixel_rect(view))
        phase = factory.steps % 6
        left = max(0, math.floor((view.left - camera.x) / camera.tile))
        right = min(WORLD_W, math.ceil((view.right - camera.x) / camera.tile))
        top = max(0, math.floor((view.top - camera.y) / camera.tile))
        bottom = min(WORLD_H, math.ceil((view.bottom - camera.y) / camera.tile))
        for y in range(top, bottom):
            for x in range(left, right):
                pos = (x, y)
                rect = camera.rect(pos)
                if not rect.colliderect(view):
                    continue
                variant = (x * 7 + y * 11 + x * y) % 4
                self.sprite(ground_sprite(factory.mineral_at(pos), variant, app.grid), rect)
                machine = factory.machines.get(pos)
                if machine is None:
                    continue
                moving = phase if machine.kind in TRANSPORT and machine.cooldown else 0
                if machine.kind == "belt":
                    sprite = connected_belt(machine.direction, factory.belt_inputs(pos, machine), moving)
                else:
                    sprite = machine_sprite(machine.kind, machine.direction, bool(machine.craft_steps_left), moving)
                self.sprite(sprite, rect)
                if not menu and machine.kind in ("furnace", "assembler", "electronics"):
                    mismatched = factory.incoming_items(pos).difference(machine.plan.inputs)
                    if mismatched:
                        badge = max(12, min(23, rect.width // 2))
                        self.box((rect.left, rect.top, badge, badge), RED, PANEL, 3)
                        self.text("!", rect.left + badge//3, rect.top-2, PANEL, "small")
                if machine.kind == "splitter" and machine.filter_item:
                    badge = max(7, rect.width // 4)
                    self.sprite(item_sprite(machine.filter_item),
                                pygame.Rect(rect.right - badge, rect.y, badge, badge))
                if machine.kind not in TRANSPORT and machine.outputs:
                    item = next(iter(machine.outputs))
                    side = max(7, rect.width // 4)
                    self.sprite(item_sprite(item), pygame.Rect(rect.right - side, rect.y, side, side))
                if not menu and machine.kind == "storage" and machine.full:
                    radius = max(5, rect.width // 7)
                    center = rect.right - radius, rect.top + radius
                    self.circle(RED, center, radius)
                    self.line((255, 249, 237),
                                     (center[0], center[1] - 3), (center[0], center[1] + 1), 2)
                    self.circle((255, 249, 237), (center[0], center[1] + 3), 1)
                if machine.kind in RECIPES and machine.craft_steps_left and rect.width >= 29:
                    self.bar((rect.x + 5, rect.bottom - 5, rect.width - 10, 3),
                             1 - machine.craft_steps_left / max(machine.craft_steps_left, factory.recipe_steps(machine)), PALETTE[machine.kind], INK_MAP)
        alpha = min(1, app.menu_fraction / STEP) if menu else app.animation_fraction
        for pos, machine in factory.machines.items():
            if machine.kind not in TRANSPORT or not machine.outputs:
                continue
            rect = camera.rect(pos)
            item = next(iter(machine.outputs))
            arrival = factory.arrivals.get(pos)
            center = pygame.Vector2(rect.center)
            if arrival:
                source, _ = arrival
                center = pygame.Vector2(camera.rect(source).center).lerp(center, alpha)
            side = max(8, round(camera.tile * 0.32))
            cargo = pygame.Rect(0, 0, side, side)
            cargo.center = round(center.x), round(center.y)
            if cargo.colliderect(view):
                self.sprite(item_sprite(item), cargo)
        if not menu:
            if app.guide_on and not any(m.kind == "miner" for m in factory.machines.values()):
                for pos in factory.deposits:
                    rect = camera.rect(pos)
                    if factory.mineral_at(pos) in STARTER_ORES and rect.colliderect(MAP):
                        self.rect(MINT, rect.inflate(-5, -5), 2)
            if app.inspected_tile in factory.machines:
                self.rect(MINT, camera.rect(app.inspected_tile), 2)
            hover = None if MINIMAP.collidepoint(mouse) else camera.tile_at(mouse)
            if hover is not None:
                rect = camera.rect(hover)
                if hover in factory.machines:
                    self.rect(TEXT, rect, 1)
                elif app.build_tool:
                    blocked = factory.placement_error(hover, app.build_tool)
                    self.draw_ghost(rect, app.build_tool, app.direction, 145, RED if blocked else MINT)
        self.canvas.set_clip(None)
        if not menu:
            self.rect(LINE, MAP, 1)
            tile = camera.tile_at(mouse)
            coordinates = f"   {tile[0] + 1:02},{tile[1] + 1:02}" if tile is not None else ""
            self.box((MAP.x + 10, MAP.y + 10, 130, 27), PANEL, LINE, 4)
            self.text(f"{camera.zoom * 100:3.0f}%{coordinates}", MAP.x + 19, MAP.y + 13, TEXT, "mono")
            hovered = factory.machines.get(tile)
            if hovered and hovered.kind in ("furnace", "assembler", "electronics") and not MINIMAP.collidepoint(mouse):
                wrong = sorted(factory.incoming_items(tile).difference(hovered.plan.inputs))
                if wrong:
                    cargo = ", ".join(tr(ITEM_LABELS[item]) for item in wrong)
                    info = tr("Incoming {cargo} · Making {product} · Click machine, then Q",
                              cargo=cargo, product=tr(ITEM_LABELS[hovered.plan.product]))
                    self.box((MAP.x+10, MAP.bottom-37, MAP.width-20, 31), PANEL, RED, 4)
                    self.text(info, MAP.x+21, MAP.bottom-33, RED, "small", width=MAP.width-40)
            elif hovered and hovered.kind == "storage" and not MINIMAP.collidepoint(mouse):
                count = hovered.storage.total()
                self.box((MAP.x + 10, MAP.bottom - 35, 520, 28), PANEL, LINE, 4)
                contents = material_list(hovered.storage)
                self.text(f"{tr('Capacity {count} / {limit}', count=count, limit=hovered.capacity)}  {contents}",
                          MAP.x + 21, MAP.bottom - 33, RED if hovered.full else TEXT, "small", width=496)
            elif tile is not None and tile not in factory.machines and not MINIMAP.collidepoint(mouse):
                mineral = factory.mineral_at(tile)
                issue = factory.placement_error(tile, app.build_tool) if app.build_tool else ""
                locked = mineral in TECHS and mineral not in factory.unlocked
                label = issue or (tr("Deposit: {item}", item=tr(ITEM_LABELS[mineral])) if mineral else "")
                if locked and not issue:
                    label = tr("Research {item} mining first [M].", item=tr(ITEM_LABELS[mineral]))
                if label:
                    self.box((MAP.x + 10, MAP.bottom - 35, 500, 26), BG, LINE, 4)
                    self.text(label, MAP.x + 21, MAP.bottom - 34, RED if issue else TEXT, "small", width=475)

    @staticmethod
    def minimap_tile(point):
        if MINIMAP.collidepoint(point):
            return ((point[0] - MINIMAP.x) * WORLD_W // MINIMAP.width,
                    (point[1] - MINIMAP.y) * WORLD_H // MINIMAP.height)
        return None

    def draw_minimap(self, app):
        self.box(MINIMAP, (35, 55, 53), LINE, 3)
        scale_x, scale_y = MINIMAP.width / WORLD_W, MINIMAP.height / WORLD_H
        for x, y in app.factory.deposits:
            item = app.factory.mineral_at((x, y))
            color = ITEM_COLORS[item]
            if item in TECHS and item not in app.factory.unlocked:
                color = tuple(value // 2 for value in color)
            self.rect(color, (MINIMAP.x + int(x * scale_x),
                                                 MINIMAP.y + int(y * scale_y), 2, 2))
        camera = app.camera
        viewport = pygame.Rect(MINIMAP.x + (MAP.left - camera.x) / camera.tile * scale_x,
                               MINIMAP.y + (MAP.top - camera.y) / camera.tile * scale_y,
                               MAP.width / camera.tile * scale_x, MAP.height / camera.tile * scale_y)
        self.rect(MINT, viewport.clip(MINIMAP), 1)

    def draw_guidance(self, app, mouse):
        factory = app.factory
        if not app.guide_on:
            self.box((MAP.x, 90, MAP.width, 56), PANEL, LINE, 5)
            self.text("Factory floor", MAP.x+15, 95, TEXT, "bold")
            self.text("Middle drag to pan · Wheel to zoom", MAP.x+15, 120, MUTED, "tiny")
            self.button((MAP.right-153, 102, 142, 31), "Show guide [G]", "guide", mouse)
            return
        kinds = {machine.kind for machine in factory.machines.values()}
        full = sum(machine.full
                   for machine in factory.machines.values() if machine.kind == "storage")
        shipment_ready = not factory.starter_complete and any(
            factory.warehouse_stock(item) >= STARTER_QUANTITY for item in STARTER_ORES)
        if shipment_ready:
            title, hint = "Ship your first ore", "Choose an ore in the contract panel to claim your first reward."
        elif full:
            title = "Warehouse full"
            hint = "Withdraw stock or add a warehouse so belts can move again."
        elif factory.starter_complete:
            page = current_chapter(factory)
            title, _, instructions = CHAPTERS[page]
            line = 0
            if page == 3 and "furnace" in kinds:
                line = 1
            elif page == 4 and factory.player_inventory["copper"] >= 3:
                line = 2
            elif page == 7 and "extractor" in kinds:
                line = 2 if "seller" in kinds else 1
            hint = instructions[line][app.language == "ko"]
        elif "miner" not in kinds:
            title, hint = "Build a miner", "Select a miner below. Place it on copper or coal."
        elif "storage" not in kinds:
            title, hint = "Add a warehouse", "Place a warehouse beyond the miner's output arrow. Add belts if needed."
        elif factory.warehouse_parts >= ORDERS[0][1]:
            title, hint = "Ship machine parts", "Your machine parts are ready to ship from the contract panel."
        else:
            connected = False
            wrong_direction = False
            for pos, machine in factory.machines.items():
                if machine.kind != "miner" or machine.plan.product not in STARTER_ORES:
                    continue
                item = machine.plan.product
                pending = [(pos, machine)]
                seen = {pos}
                while pending:
                    position, sender = pending.pop()
                    for direction in sender.routes(item):
                        dx, dy = DIRS[direction]
                        target = position[0] + dx, position[1] + dy
                        receiver = factory.machines.get(target)
                        if not receiver or target in seen:
                            continue
                        if not receiver.input_direction_ok((direction + 2) % 4):
                            wrong_direction |= receiver.kind in TRANSPORT
                        elif receiver.kind == "storage":
                            connected = True
                        elif receiver.kind in TRANSPORT:
                            seen.add(target)
                            pending.append((target, receiver))
            if connected:
                title, hint = "Collect ten ore", "A shipment uses one ore type. Its total appears in the contract panel."
            elif wrong_direction:
                title, hint = "Belt facing the wrong way", "A nearby belt faces the miner or the previous belt. Rotate it with Shift+R."
            else:
                title, hint = "Connect the output", "Connect the miner's output arrow to storage and check belt directions."
        red = bool(full) and not shipment_ready
        self.box((MAP.x, 90, MAP.width, 56), PANEL, LINE, 4)
        self.rect(RED if red else MINT, (MAP.x, 90, 5, 56), border_radius=2)
        self.text(title, MAP.x + 16, 95, RED if red else MINT, "bold")
        self.text(hint, MAP.x + 16, 119, TEXT, "small", width=671)
        self.button((MAP.right-266, 95, 137, 23), "Step-by-step guide", "tutorial", mouse)
        self.button((MAP.right - 122, 95, 112, 23), "Hide guide [G]", "guide", mouse)

    def draw_build_cost(self, app, mouse):
        x, y = PANEL_X, 545
        self.box((x, y, PANEL_W, 137), PANEL, LINE, 5)
        if not app.build_tool:
            self.text("Construction", x + 14, y + 10, font="bold")
            self.text("Select a machine in the build menu.", x + 14, y + 38, MUTED, "small")
            return
        kind = app.build_tool
        factory = app.factory
        self.text(tr("Build: {machine}", machine=tr(LABELS[kind])), x + 14, y + 8, font="bold", width=285)
        self.text("Owned / needed", x + 14, y + 34, MUTED, "tiny")
        entries = [("CREDITS", factory.credits, COST[kind], None)]
        entries.extend((ITEM_LABELS[item], factory.player_inventory[item], count, item)
                       for item, count in BUILD_MATERIALS.get(kind, {}).items())
        for i, (label, have, needed, item) in enumerate(entries):
            top = y + 53 + i * 18
            color = RED if have < needed else MINT
            if have < needed:
                self.rect((250, 229, 218), (x + 8, top, PANEL_W - 16, 18), border_radius=3)
            if item:
                self.sprite(item_sprite(item), pygame.Rect(x + 12, top, 17, 17))
            self.text(label, x + 33, top, TEXT, "tiny", width=91)
            self.text(f"{have:,}/{needed:,}", x + 119, top - 1, color, "small", width=185 if not item else 67)
            if item and have < needed:
                self.text(tr("Stock {count}", count=factory.warehouse_stock(item)),
                          x + 184, top, MUTED, "tiny", width=76)
                self.button((x + 259, top - 1, 55, 17), "Recipe", f"recipe-guide:{item}", mouse)

    def draw_ghost(self, rect, kind, direction, alpha, border):
        target = self.pixel_rect(rect)
        ghost = pygame.transform.smoothscale(machine_sprite(kind, direction), target.size)
        ghost.set_alpha(alpha)
        self.canvas.blit(ghost, target)
        self.rect(border, rect.inflate(-3, -3), 2)
        if kind not in ("storage", "seller"):
            cx, cy = rect.center
            for side in range(4):
                is_output = side == direction or kind == "splitter" and side == (direction + 1) % 4
                has_input = kind != "miner" and (side == (direction + 2) % 4 or
                            kind not in ("splitter", "extractor") and not is_output)
                if not (is_output or has_input):
                    continue
                dx, dy = DIRS[side]
                distance = rect.width * 0.40
                self.text(ARROWS[side if is_output else (side + 2) % 4],
                          int(cx + dx * distance) - 7, int(cy + dy * distance) - 10,
                          border if is_output else TEXT, "small")

    def draw_inspector(self, app, mouse):
        x = PANEL_X
        self.box((x, 90, PANEL_W, 284))
        self.text("EQUIPMENT", x + 15, 104, MUTED, "tiny")
        machine = app.factory.machines.get(app.inspected_tile)
        if machine is None and app.build_tool:
            kind = app.build_tool
            self.sprite(machine_sprite(kind, app.direction), pygame.Rect(x+13, 130, 91, 91))
            self.text(LABELS[kind], x+110, 144, TEXT, "bold", width=207)
            self.text(tr("Output {arrows}", arrows=ARROWS[app.direction]) if kind not in ("storage","seller")
                      else "Any side in", x+110, 181, MINT, "small")
            factory = app.factory
            issue = ""
            if kind == "seller" and "automation" not in factory.unlocked:
                issue = tr("Research {tech} first.", tech=tr(TECH_NAMES["automation"]))
            elif kind == "extractor" and not factory.starter_complete:
                issue = tr("Complete the first shipping contract.")
            elif factory.credits < COST[kind] or any(factory.player_inventory[k] < n for k,n in BUILD_MATERIALS.get(kind, {}).items()):
                issue = tr("Check the construction costs below.")
            self.text(issue or "Click an empty tile to build.", x+15, 237, AMBER if issue else MINT, "small", width=297)
            self.button((x+15, 303, 146, 40), "Rotate build [R]", "turn-tool", mouse)
            self.button((x+168, 303, 142, 40), "Cancel", "cancel-tool", mouse)
            return
        if machine is None:
            self.text("Inspect a machine", x + 16, 135, font="bold")
            self.text("Click a placed machine to view it.", x + 16, 163, MUTED, "small")
            for i, item in enumerate(("ore", "copper_ore", "coal")):
                left = x + 17 + i * 100
                self.sprite(item_sprite(item), pygame.Rect(left, 208, 17, 17))
                self.text(ITEM_LABELS[item], left + 22, 206, TEXT, "small", width=76)
            self.text("Place miners on colored mineral deposits.", x + 16, 246, MUTED, "small")
            self.text("Furnaces accept inputs from the back and both sides.", x + 16, 270, MUTED, "small")
            self.button((x + 15, 326, PANEL_W - 30, 32), "Toggle on-screen guide [G]", "guide", mouse)
            return
        color = PALETTE[machine.kind]
        self.sprite(machine_sprite(machine.kind, machine.direction), pygame.Rect(x + 15, 128, 37, 37))
        self.text(LABELS[machine.kind], x + 61, 125, TEXT, "bold")
        if machine:
            self.text(tr("Lv. {level}", level=machine.level), x + 267, 129, MINT, "small")
        arrows = " ".join(ARROWS[d] for d in machine.output_directions)
        heading = tr("Any side in") if machine.kind in ("storage", "seller") else tr("Output {arrows}", arrows=arrows)
        self.text(tr("Tile {x}, {y} / {heading}", x=app.inspected_tile[0] + 1, y=app.inspected_tile[1] + 1, heading=heading),
                  x + 61, 148, MUTED, "small")
        if machine.kind == "storage":
            self.text(tr("Capacity {count} / {limit}", count=machine.storage.total(), limit=machine.capacity),
                      x + 16, 174, font="small")
            if not machine.storage:
                self.text("Empty", x+16, 207, MUTED, "body")
            for i, item in enumerate(k for k in ITEMS if machine.storage[k]):
                left = x + 16 + (i // 7) * 150
                yy = 194 + i % 7 * 16
                self.text(ITEM_LABELS[item], left, yy, TEXT, "small", width=112)
                self.text(machine.storage[item], left + 116, yy, MUTED, "small")
            self.bar((x + 16, 312, PANEL_W - 32, 4), machine.storage.total() / machine.capacity)
            self.button((x+15, 327, 190, 32), "Take all items", "withdraw-all", mouse,
                        enabled=bool(machine.storage), accent=bool(machine.storage))
            self.button((x + 211, 327, 100, 32), "Dismantle", "dismantle", mouse)
            return
        outgoing = next(iter(machine.outputs), None)
        if machine.kind == "extractor":
            self.text(app.factory.extractor_status(app.inspected_tile, machine), x + 16, 181, AMBER, "small", width=295)
            name = tr(ITEM_LABELS[machine.filter_item]) if machine.filter_item else tr("Choose an item to extract")
            self.button((x + 15, 210, 295, 31), name, "filter", mouse)
            reserve = tr("Keep {count} in storage", count=machine.reserve) if machine.controlled else tr("Install control module ×1")
            self.button((x + 15, 248, 295, 31), reserve, "reserve", mouse)
            self.button((x + 15, 286, 295, 31), "Resume extraction" if machine.paused else "Pause extraction", "pause-extractor", mouse)
        elif machine.kind == "seller":
            self.text("Sells arriving items from any side.", x + 16, 184, MINT, "small")
            self.text(tr("Sales revenue {value} / {goal}", value=app.factory.total_sales, goal=SALES_TARGET),
                      x + 16, 218, TEXT, "small")
        elif machine.kind in TRANSPORT:
            cargo = tr(ITEM_LABELS[outgoing]) if outgoing else tr("Empty")
            self.text(tr("Cargo: {item}", item=cargo), x + 16, 183, TEXT if outgoing else MUTED, "small")
            if machine.kind == "splitter":
                if machine.filter_item:
                    self.text(tr("Filter: {item}", item=tr(ITEM_LABELS[machine.filter_item])),
                              x + 16, 207, MINT, "small")
                else:
                    self.text("Rear input; alternates between open exits.", x + 16, 207, MUTED, "small")
                self.button((x + 15, 296, PANEL_W - 30, 27), "Change filter", "filter", mouse)
            else:
                self.text("Receives from the rear and either side.", x + 16, 207, MUTED, "small")
            if outgoing:
                for row, direction in enumerate(machine.routes(outgoing)):
                    status = app.factory.output_status(app.inspected_tile, direction, outgoing)
                    self.text(f"{ARROWS[direction]}  {status}", x + 16, 233 + 24 * row, AMBER, "small")
        else:
            plan = machine.plan
            duration = app.factory.recipe_steps(machine) / 10
            self.text(tr("{recipe} / {seconds:.1f}s", recipe=tr(plan.name), seconds=duration),
                      x + 16, 175, MINT, "small")
            recipe = (material_list(plan.inputs) + " → " if plan.inputs else "") + tr(ITEM_LABELS[plan.product])
            self.text(recipe, x + 16, 197, MUTED, "tiny", width=293)
            if plan.inputs:
                stock = "  ".join(f"{tr(ITEM_LABELS[item])} {machine.inputs[item]}/{count}" for item, count in plan.inputs.items())
                self.text(stock, x + 16, 221, font="tiny", width=293)
            self.text(tr("Output stock {count}/{limit}", count=machine.outputs.total(), limit=OUTPUT_LIMIT),
                      x + 16, 243, font="small")
            if outgoing:
                status = app.factory.output_status(app.inspected_tile, machine.direction, outgoing)
                self.text(status, x + 140, 244, AMBER, "tiny", width=169)
            if machine.craft_steps_left:
                status = "Working"
                progress = 1 - machine.craft_steps_left / max(machine.craft_steps_left, app.factory.recipe_steps(machine))
            elif machine.outputs.total() >= OUTPUT_LIMIT:
                status, progress = "Output full", 1
            else:
                status, progress = "Ready" if not plan.inputs else "Waiting for input", 0
            self.text(status, x + 16, 268, AMBER if status == "Output full" else MUTED, "tiny")
            self.bar((x + 128, 275, PANEL_W - 145, 5), progress, color)
            if machine.kind in ("furnace", "assembler", "electronics"):
                mismatch = app.factory.incoming_items(app.inspected_tile).difference(plan.inputs)
                title = "Input mismatch · Choose recipe [Q]" if mismatch else "Choose recipe [Q]"
                self.button((x + 15, 296, PANEL_W - 30, 27), title, "recipe", mouse, accent=bool(mismatch))
        self.button((x + 15, 327, 142, 32), "Rotate [Shift+R]", "rotate", mouse)
        self.button((x + 168, 327, 143, 32), "Dismantle", "dismantle", mouse)

    def draw_contract(self, app, mouse):
        x = PANEL_X
        factory = app.factory
        self.box((x, 386, PANEL_W, 147))

        if not factory.starter_complete and factory.warehouse_parts < ORDERS[0][1]:
            self.text("First shipment · tutorial", x+16, 396, MINT, "bold")
            self.text(tr("+{credits} credits", credits=STARTER_REWARD), x + 215, 397, AMBER, "tiny")
            for i, item in enumerate(STARTER_ORES):
                top = 422 + i * 32
                stock = factory.warehouse_stock(item)
                self.text(ITEM_LABELS[item], x + 16, top + 3, TEXT, "small", width=105)
                self.text(f"{min(stock, STARTER_QUANTITY)}/{STARTER_QUANTITY}", x + 124, top + 3, MUTED, "small")
                self.button((x + 192, top, 117, 28), "Ship ore", f"first:{item}", mouse,
                            enabled=stock >= STARTER_QUANTITY, accent=stock >= STARTER_QUANTITY)
            return
        if factory.starter_complete and "ore" not in factory.unlocked:
            cost, ingredients, _ = TECHS["ore"]
            need = ingredients["copper"]
            self.text("Next step · Unlock iron", x+16, 396, MINT, "bold")
            self.text(tr("Carry copper ingots: {have}/{need}", have=factory.player_inventory["copper"], need=need),
                      x+16, 423, TEXT, "bold")
            self.text(tr("Research costs {cost} cr · Warehouse stock {stock}", cost=cost,
                         stock=factory.warehouse_stock("copper")), x+16, 450, MUTED, "small")
            self.text("Add coal for faster copper smelting.", x+16, 473, AMBER, "small")
            self.button((x+15, 498, 143, 27), "Copper recipes", "recipe-guide:copper", mouse)
            self.button((x+165, 498, 146, 27), "Research [Y]", "research-menu", mouse, accent=not factory.research_error("ore"))
            return
        self.text("Optional shipment", x+16, 395, MINT, "bold")
        if factory.contract_index < len(ORDERS):
            item, amount, reward = ORDERS[factory.contract_index]
            stock = factory.warehouse_stock(item)
            self.text(f"{tr(ITEM_LABELS[item])}  {min(stock, amount)} / {amount}", x + 16, 424, font="bold", width=203)
            self.text(tr("+{credits} credits", credits=reward), x + 220, 428, AMBER, "small")
            self.bar((x + 16, 457, PANEL_W - 32, 6), stock / amount)
            self.button((x+15, 479, 86, 34), "Recipe", f"recipe-guide:{item}", mouse)
            self.button((x + 106, 479, PANEL_W - 121, 34), "Ship from warehouses [Enter]", "dispatch", mouse,
                        enabled=stock >= amount, accent=True)
        else:
            self.text("All contracts shipped", x + 16, 428, MINT, "bold")

    def draw_inventory(self, app, mouse):
        x, y = MAP.x, 684
        self.box((x, y, MAP.width, 92), PANEL, LINE, 6)
        factory = app.factory
        machine = factory.machines.get(app.inspected_tile)
        local = machine is not None and machine.kind == "storage"
        warehouses = (machine,) if local else (m for m in factory.machines.values() if m.kind == "storage")
        inventory = Counter()
        limit = full = 0
        for warehouse in warehouses:
            inventory.update(warehouse.storage)
            limit += warehouse.capacity
            full += warehouse.full
        used = inventory.total()
        self.text("This warehouse / carried" if local else "Stock / carried", x+10, y+3, TEXT, "small", width=179)
        self.text(tr("Capacity {count} / {limit}", count=used, limit=limit), x+197, y+4, MUTED, "small")
        if full:
            self.text(tr("Full: {count}", count=full), x+334, y+5, RED, "small")
        can_load = machine and (machine.kind == "storage" or machine.kind in RECIPES and machine.kind != "miner")
        for i, amount in enumerate(TRANSFER_AMOUNTS):
            self.button((x + 421 + 42*i, y + 2, 40, 23), "All" if amount == "all" else amount,
                        f"amount:{amount}", mouse, accent=amount == app.transfer_amount)
        self.button((x+600, y+2, 133, 23), "Insert [F]", "deposit", mouse, enabled=can_load)
        self.button((x+739, y+2, 152, 23), "Withdraw [T]", "withdraw", mouse,
                    enabled=machine and machine.kind == "storage")
        for i, item in enumerate(ITEMS):
            left, top = x + 7 + i % 7 * 127, y + 29 + i // 7 * 31
            selected = item == app.inventory_item
            rect = pygame.Rect(left, top, 124, 29)
            stock = inventory[item]
            fill = (208, 242, 215) if stock else (254, 239, 198) if factory.player_inventory[item] else (224, 228, 224)
            self.box(rect, fill, TEXT if selected else fill, 3)
            self.sprite(item_sprite(item), pygame.Rect(left+2, top+2, 26, 26))
            self.text(ITEM_LABELS[item], left+32, top-2, TEXT, "tiny", width=90)
            self.text(f"{stock:,} / {factory.player_inventory[item]:,}", left+32, top+11, MINT, "tiny", width=90)
            self.buttons.append((rect, f"item:{item}"))

    def draw_toolbar(self, app, mouse):
        for i, kind in enumerate(TYPES):
            rect = pygame.Rect(MAP.x + 75*i, 610, 73, 68)
            selected = kind == app.build_tool
            hovered = rect.collidepoint(mouse)
            fill = (208, 232, 219) if selected else RAISED if hovered else PANEL
            self.box(rect, fill, MINT if selected else LINE, 5)
            self.sprite(machine_sprite(kind, app.direction if selected else 0),
                        pygame.Rect(rect.centerx-19, rect.y+2, 38, 38))
            if i < 10:
                self.text((i+1)%10, rect.x+4, rect.y+1, MUTED, "tiny")
            locked = (kind == "seller" and "automation" not in app.factory.unlocked
                      or kind == "extractor" and not app.factory.starter_complete)
            self.text(LABELS[kind], rect.x+4, rect.y+36, TEXT, "tiny", width=66)
            self.text("Locked" if locked else tr("{credits} cr", credits=COST[kind]),
                      rect.x+4, rect.y+50, AMBER if locked else MINT, "tiny")
            if selected:
                self.rect(MINT, (rect.x+4, rect.bottom-3, 65, 3))
            self.buttons.append((rect, f"tool:{kind}"))
            if hovered:
                self.box((MAP.x+8, MAP.bottom-36, 470, 29), PANEL, MINT, 4)
                tip = tr(LABELS[kind]) + "   ·   " + tr("{credits} cr", credits=COST[kind])
                materials = material_list(BUILD_MATERIALS.get(kind, {}))
                self.text(tip + ("   +   " + materials if materials else ""), MAP.x+19, MAP.bottom-33,
                          TEXT, "small", width=449)
        x = PANEL_X
        machine = app.factory.machines.get(app.inspected_tile)
        eligible = bool(machine and machine.level < MAX_LEVEL)
        if eligible:
            target = machine.level + 1
            cost, materials = upgrade_cost(machine)
            rows = list(app.factory.cost_rows(cost, materials))
            tech = UPGRADE_TECH.get(target)
            ready = all(have >= needed for _, have, needed in rows) and (not tech or tech in app.factory.unlocked)
            self.button((x, 685, PANEL_W, 25), tr("Upgrade to level {level} [U]", level=target),
                        "upgrade", mouse, accent=ready)
            width = PANEL_W // len(rows)
            for index, (label, have, needed) in enumerate(rows):
                left = x + index * width
                short = needed - have
                color = RED if short > 0 else MINT
                self.text(label, left + 3, 710, TEXT, "tiny", width=width-5)
                amount = f"{have:,}/{needed:,}"
                if short > 0:
                    amount += " · " + tr("Need {count}", count=short)
                self.text(amount, left + 3, 727, color, "tiny", width=width-5)
            if tech and tech not in app.factory.unlocked:
                effect = tr("Research {tech} first.", tech=tr(TECH_NAMES[tech]))
            elif machine.kind == "storage":
                effect = tr("Capacity {before} → {after}", before=machine.capacity, after=STORAGE_LIMIT * target)
            elif machine.kind in ("extractor", "seller"):
                effect = tr("Transfer {before:.2f}s → {after:.2f}s",
                            before=(6 - machine.level) * STEP, after=(6 - target) * STEP)
            elif machine.kind in TRANSPORT:
                effect = tr("Transfer {before:.2f}s → {after:.2f}s",
                            before=machine.belt_delay * STEP, after=(machine.belt_delay - 0.5) * STEP)
            else:
                effect = tr("Cycle {before:.1f}s → {after:.1f}s",
                            before=app.factory.recipe_steps(machine) * STEP,
                            after=app.factory.recipe_steps(machine, target) * STEP)
            self.text(effect, x + 16, 360, AMBER if tech and tech not in app.factory.unlocked else MINT, "tiny", width=296)
        else:
            self.text("Maximum level reached." if machine else "Select a machine to upgrade.",
                      x + 10, 699, MUTED, "small")
        for i, (label, action) in enumerate((("Save [F5]", "save"), ("Load [F9]", "load"), ("Help [Tab]", "help"))):
            self.button((x + i * 110, 747, 105, 27), label, action, mouse)

    def draw_menu(self, app, mouse):
        self.draw_map(app, mouse, menu=True)
        self.shade((14, 34, 31, 66))
        x = 62
        self.rect((28, 56, 52), (0, 0, 532, SIZE[1]))
        self.rect((239, 187, 97), (532, 0, 5, SIZE[1]))
        self.sprite(machine_sprite("assembler"), pygame.Rect(88, 66, 78, 78))
        self.text("MiniFactory", x + 27, 150, PANEL, "hero")
        self.text("Build an iron works and ship machine parts.", x + 30, 233, (202, 223, 208), "body")
        self.box((630, 575, 572, 156), PANEL, LINE, 8)
        self.text("Starter line", 652, 587, MINT, "bold")
        for i, kind in enumerate(("miner", "belt", "storage")):
            left = 651 + i * 182
            self.sprite(machine_sprite(kind), pygame.Rect(left+37, 615, 69, 69))
            self.text(LABELS[kind], left+28, 687, TEXT, "body", width=138)
            if i < 2:
                self.text("→", left+137, 634, AMBER, "title")
        choices = [
            ("Start a new factory", "new", True),
            ("Open a working example", "example", True),
            ("Open the circuit factory example", "advanced", True),
            ("Load saved factory", "load", app.store_path.is_file()),
            ("Controls and settings", "help", True),
        ]
        if app.has_session:
            choices.insert(0, ("Resume factory", "resume", True))
        for i, (label, action, enabled) in enumerate(choices):
            self.button((x + 30, 282 + i * 52, 397, 42), label, action, mouse, enabled=enabled, accent=i == 0)
        self.button((x + 30, 604, 118, 42), "Exit", "quit", mouse)
        self.text(app.message, x + 31, 665, PANEL, "small", width=397)

    def draw_market(self, app, mouse):
        x, y = 163, 86
        self.box((x, y, 954, 628), PANEL, LINE, 12)
        self.text("Sales desk", x + 25, y + 15, font="title")
        self.text(tr("{credits} cr", credits=app.factory.credits), x + 730, y + 30, AMBER, "bold")
        self.text("Trades use player inventory. Withdraw goods from a warehouse first.", x + 26, y + 75,
                  MUTED, "small")
        for i, item in enumerate(ITEMS):
            left, top = x + 25 + i // 7 * 454, y + 115 + i % 7 * 42
            self.box((left, top, 442, 38), RAISED)
            self.sprite(item_sprite(item), pygame.Rect(left + 5, top + 4, 29, 29))
            self.text(ITEM_LABELS[item], left + 35, top + 8, font="small", width=138)
            self.text(app.factory.player_inventory[item], left + 170, top + 8, MUTED, "small", width=35)
            for offset_x, amount in ((211, 1), (326, 5)):
                missing = amount - app.factory.player_inventory[item]
                rect = pygame.Rect(left + offset_x, top + 4, 107, 30)
                if missing <= 0:
                    self.button(rect, tr("Sell {count} · +{price}", count=amount, price=SHOP_SELL[item] * amount),
                                f"sell:{item}:{amount}", mouse, accent=True)
                else:
                    self.box(rect, (220, 224, 220), None, 5)
                    label = tr("Need {count} more", count=missing)
                    glyph = self.text_image(label, MUTED, "small")
                    self.canvas.blit(glyph, glyph.get_rect(center=self.pixel_point(rect.center)))
        self.button((x + 25, y + 433, 280, 43), "Research [Y]", "research-menu", mouse,
                    accent=any(not app.factory.research_error(t) for t in TECHS))
        self.text(app.message, x + 26, y + 520, MINT, "small", width=902)
        self.button((x + 25, y + 563, 904, 38), "Close [Esc]", "close", mouse, accent=True)

    def draw_research(self, app, mouse):
        x, y = 232, 98
        self.box((x, y, 816, 604), PANEL, LINE, 12)
        self.text("Research", x + 25, y + 13, font="title")
        descriptions = (
            "Stage 2 · unlocks iron deposits",
            "Unlocks level 3 upgrades",
            "Unlocks auto sellers and level 4 upgrades",
            "Unlocks level 5 upgrades",
            "Unlocks quartz deposits for silicon",
        )
        for i, (tech, (cost, materials, prerequisite)) in enumerate(TECHS.items()):
            top = y + 69 + i * 87
            self.box((x + 22, top, 772, 78), RAISED)
            self.text(TECH_NAMES[tech], x + 35, top + 4, font="bold")
            self.text(descriptions[i], x + 35, top + 29, MINT, "tiny")
            charge = tr("{credits} cr", credits=cost)
            self.text(f"{charge} + {material_list(materials)}", x + 35, top + 43, MUTED, "tiny", width=500)
            unlocked = tech in app.factory.unlocked
            error = app.factory.research_error(tech)
            status = "Researched" if unlocked else "Unavailable" if error else "Start research"
            self.button((x+567, top+11, 209, 32), status, f"research:{tech}", mouse,
                        enabled=not error, accent=not error)
            if error and not unlocked:
                self.text(error, x+34, top+59, AMBER, "tiny", width=733)
        self.text(app.message, x + 24, y + 513, TEXT, "small", width=771)
        self.button((x + 22, y + 550, 772, 36), "Close [Esc]", "close", mouse)

    def draw_recipes(self, app, mouse):
        x, y = 210, 105
        self.box((x, y, 860, 590), PANEL, LINE, 12)
        self.text("Recipe book", x + 25, y + 13, font="title")
        for i, item in enumerate(ITEMS):
            left = x + 24 + i % 4 * 203
            top = y + 73 + i // 4 * 42
            self.button((left, top, 194, 36), ITEM_LABELS[item], f"recipe-guide:{item}", mouse,
                        accent=app.recipe_item == item)
        for i, (kind, recipe) in enumerate(recipe_chain(app.recipe_item)):
            top = y + 240 + i * 25
            self.box((x + 24, top, 804, 24), RAISED)
            inputs = material_list(recipe.inputs) or tr("Place the miner on the matching deposit.")
            output = tr(ITEM_LABELS[recipe.product])
            self.text(LABELS[kind], x + 36, top + 5, MINT, "small", width=152)
            self.text(f"{inputs} → {output}", x + 191, top + 5, TEXT, "small", width=622)
        self.button((x + 24, y + 546, 804, 31), "Close [Esc]", "close", mouse)

    def draw_filter(self, app, mouse):
        x, y = 310, 187
        self.box((x, y, 660, 426), PANEL, LINE, 12)
        extractor = app.factory.machines[app.inspected_tile].kind == "extractor"
        self.text("Choose an item to extract" if extractor else "Splitter filter", x + 24, y + 18, font="title")
        self.text("Place a warehouse behind the extractor" if extractor else "Matching items turn right. All other items go straight.", x + 24, y + 70,
                  MUTED, "small")
        machine = app.factory.machines[app.inspected_tile]
        for i, item in enumerate(ITEMS):
            left, top = x + 24 + 208 * (i % 3), y + 98 + (i // 3) * 45
            self.button((left, top, 196, 42), tr(ITEM_LABELS[item]), f"filter:{item}", mouse,
                        accent=machine.filter_item == item)
        self.button((x + 24, y + 328, 300, 44), "Clear filter", "filter:", mouse)
        self.button((x + 336, y + 328, 300, 44), "Close [Esc]", "close", mouse)

    def draw_recipe_picker(self, app, mouse):
        machine = app.factory.machines[app.inspected_tile]
        incoming = app.factory.incoming_items(app.inspected_tile)
        x, y = 215, 65
        self.box((x, y, 850, 664), PANEL, LINE, 12)
        self.text("Choose recipe [Q]", x+25, y+17, TEXT, "title")
        cargo = ", ".join(tr(ITEM_LABELS[k]) for k in sorted(incoming)) or tr("Empty")
        self.text(tr("At the input: {cargo}", cargo=cargo), x+26, y+74, TEXT, "body", width=792)
        for index, plan in enumerate(RECIPES[machine.kind]):
            top = y + 100 + index * 90
            active = index == machine.recipe
            matches = bool(incoming) and incoming.issubset(plan.inputs)
            self.box((x+21, top, 808, 85), (224, 239, 227) if matches else RAISED, MINT if matches else LINE, 6)
            self.sprite(item_sprite(plan.product), pygame.Rect(x+31, top+18, 57, 57))
            self.text(ITEM_LABELS[plan.product], x+98, top+8, TEXT, "bold")
            self.text(tr(plan.name) + f" · {plan.steps * STEP:.1f}s", x+98, top+36, MUTED, "small", width=191)
            for n, (item, amount) in enumerate(plan.inputs.items()):
                left = x+290+117*n
                self.sprite(item_sprite(item), pygame.Rect(left, top+12, 33, 33))
                self.text(f"×{amount}", left+36, top+19, TEXT, "bold")
                self.text(ITEM_LABELS[item], left, top+53, MUTED, "small", width=110)
            if matches:
                self.text("Matches incoming cargo", x+98, top+61, MINT, "tiny", width=188)
            locked = plan.required_tech and plan.required_tech not in app.factory.unlocked
            label = "Research iron mining" if locked else "Already selected" if active else "Use recipe"
            self.button((x+653, top+20, 157, 41), label, f"apply-recipe:{index}", mouse,
                        enabled=not (active or locked), accent=matches and not active and not locked)
        self.text("Changing returns unfinished batch materials to you.", x+26, y+551, MUTED, "small")
        self.button((x+22, y+597, 806, 43), "Close [Esc]", "close", mouse)

    def draw_overlay(self, app, mouse):
        self.shade((7, 13, 16, 185))
        if app.overlay == "tutorial":
            page = app.tutorial_page
            title, machines, instructions = CHAPTERS[page]
            self.box((130, 100, 1020, 600), PANEL, LINE, 12)
            self.text("Step-by-step guide", 158, 124, TEXT, "title")
            for i, (name, _, _) in enumerate(CHAPTERS):
                self.button((156, 194+i*49, 230, 41), f"{i+1}. {tr(name)}", f"chapter:{i}", mouse, accent=i == page)
            self.text(f"{page+1} / {len(CHAPTERS)}   {tr(title)}", 419, 194, MINT, "bold")
            for i, kind in enumerate(machines):
                left = 417 + i*157
                self.sprite(machine_sprite(kind), pygame.Rect(left+12, 237, 66, 66))
                self.text(LABELS[kind], left, 311, TEXT, "small", width=150)
            for i, pair in enumerate(instructions):
                words = pair[app.language == "ko"].split()
                lines = [f"{i+1}."]
                for word in words:
                    candidate = lines[-1] + " " + word
                    if self.fonts["small"].size(candidate)[0] > 695*self.scale_x:
                        lines.append(word)
                    else:
                        lines[-1] = candidate
                for row, line in enumerate(lines):
                    self.text(line, 419, 367+i*61+row*20, TEXT, "small")
            self.button((419, 572, 310, 44), "Close [Esc]", "close", mouse)
            self.button((747, 572, 350, 44), "Next step", f"chapter:{page+1}", mouse,
                        enabled=page+1 < len(CHAPTERS), accent=True)
            return
        if app.overlay == "choose-recipe":
            self.draw_recipe_picker(app, mouse)
            return
        if app.overlay == "ending":
            self.box((340, 227, 600, 305), PANEL, LINE, 12)
            self.text("Factory goal reached", 373, 259, MINT, "title")
            self.text(tr("Sales revenue {value} / {goal}", value=app.factory.total_sales, goal=SALES_TARGET), 373, 336, TEXT, "bold")
            self.text(app.message, 373, 382, MUTED, "small", width=532)
            self.button((373, 439, 250, 47), "Keep building", "resume", mouse, accent=True)
            self.button((641, 439, 265, 47), "Save and return to menu", "finish-menu", mouse)
            return
        if app.overlay == "research":
            self.draw_research(app, mouse)
            return
        if app.overlay == "recipes":
            self.draw_recipes(app, mouse)
            return
        if app.overlay == "market":
            self.draw_market(app, mouse)
            return
        if app.overlay == "filter":
            self.draw_filter(app, mouse)
            return
        if app.overlay == "language":
            x, y = 372, 268
            self.box((x, y, 536, 250), PANEL, LINE, 13)
            self.text("언어 선택", x + 24, y + 17, font="title")
            self.text("Choose your language", x + 24, y + 65, MUTED, "body")
            self.button((x + 24, y + 116, 236, 54), "한국어", "language:ko", mouse, accent=True)
            self.button((x + 276, y + 116, 236, 54), "English", "language:en", mouse)
            if app.language:
                self.button((x + 24, y + 190, 488, 36), "Close [Esc]", "close", mouse)
            return
        if app.overlay == "help":
            x, y = 287, 93
            self.box((x, y, 706, 614), PANEL, LINE, 13)
            self.text("Controls and settings", x + 26, y + 20, font="title")
            controls = (
                ("Left click", "Build or inspect an occupied tile. Drag to place conveyors."),
                ("Right click", "Dismantle and recover materials and credits."),
                ("1–9, 0 / R / Shift+R", "Select tool / rotate preview / rotate inspected machine."),
                ("Middle drag / wheel", "Pan / zoom at cursor. Home resets the camera."),
                ("Space / Esc / M", "Pause / cancel building or open menu / shop."),
                ("F5 / F9 / G", "Save / load / toggle the on-screen guide."),
                ("Q / F / T / U", "Change recipe / load / take / upgrade selected machine."),
            )
            for i, (key, label) in enumerate(controls):
                yy = y + 83 + 34 * i
                self.text(key, x + 27, yy, MINT, "small")
                self.text(label, x + 237, yy, font="small")
            self.line(LINE, (x + 26, y + 332), (x + 680, y + 332))
            self.text("Starter line", x + 27, y + 351, font="bold")
            self.text("Miner → belts → warehouse → first shipment → furnace",
                      x + 27, y + 384, AMBER, "small")
            self.text("Copper and coal are available first. Research iron after the first shipment.",
                      x + 27, y + 411, MUTED, "small")
            self.text("Withdraw finished materials from warehouses to build advanced machines.",
                      x + 27, y + 438, MUTED, "small")
            self.button((x+359, y+453, 320, 32), "Step-by-step guide", "tutorial", mouse)
            self.button((x + 27, y + 453, 320, 32), "Recipe book", "recipes", mouse, accent=True)
            self.button((x + 27, y + 493, 213, 37), "Hide tile grid" if app.grid else "Show tile grid", "grid", mouse)
            self.button((x + 249, y + 493, 190, 37), "Language / 언어", "language", mouse)
            self.button((x + 464, y + 493, 215, 37), "Windowed [F11]" if app.fullscreen else "Fullscreen [F11]",
                        "fullscreen", mouse)
            self.button((x + 27, y + 548, 652, 39), "Close [Esc]", "close", mouse, accent=True)
            return
        x, y = 379, 302
        self.box((x, y, 522, 193), PANEL, LINE, 12)
        self.text("Unsaved factory", x + 22, y + 18, font="title")
        self.text("Continuing discards changes since the last save.", x + 22, y + 71, MUTED, "small")
        self.button((x + 22, y + 124, 144, 41), "Cancel", "close", mouse)
        if app.pending != "load":
            self.button((x + 178, y + 124, 143, 41), "Save and continue", "save_continue", mouse)
        self.button((x + 333, y + 124, 166, 41), "Discard and continue", "confirm", mouse, accent=True)
        if app.message and app.message == tr("Could not write the save file."):
            self.text(app.message, x + 22, y + 99, RED, "tiny", width=475)


INK_MAP = (17, 31, 29)
