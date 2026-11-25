"""Playable progression guide. Each chapter has an action, a check, and a recovery hint."""

# title, machines shown in the guide, instructions (English, Korean)
CHAPTERS = (
    ("First mine", ("miner",), (
        ("Pick a miner in the bottom toolbar. Click a highlighted copper or coal deposit.", "하단에서 채굴기를 고르고 강조된 구리 또는 석탄 광맥을 클릭하세요."),
        ("R rotates the preview. Point the arrow toward open ground for your belt.", "R로 설치 방향을 돌려 화살표가 벨트를 놓을 빈칸을 향하게 하세요."),
        ("Click a placed miner to see its output. Right-click to dismantle and recover its build cost.", "설치한 채굴기를 누르면 생산물을 봅니다. 우클릭으로 철거하면 건설 비용을 돌려받아요."))),
    ("Build a line", ("miner","belt","storage"), (
        ("Drag belts from the miner's arrow toward a warehouse. Turn corners while dragging.", "채굴기 화살표 앞에서 창고까지 벨트를 드래그하세요. 드래그 중 꺾으면 모서리가 이어집니다."),
        ("Put the warehouse at the last arrow. An adjacent warehouse can receive directly.", "마지막 화살표 앞에 창고를 놓으세요. 채굴기 바로 앞에 놓으면 벨트 없이도 받아요."),
        ("Check the stock counter below the map. Select a reversed belt and press Shift+R.", "맵 아래 창고 수량이 늘어나는지 보세요. 거꾸로 놓인 벨트는 선택하고 Shift+R로 돌립니다."))),
    ("First delivery", ("storage",), (
        ("Collect ten copper ore OR ten coal in storage. Keep them there for delivery.", "구리 광석이나 석탄 한 종류를 창고에 10개 모으세요. 출하할 재료는 창고에 두세요."),
        ("In the first shipment panel, click Ship ore beside the stocked item.", "오른쪽 첫 출하 패널에서 10개가 모인 광물 옆의 출하 버튼을 누르세요."),
        ("The reward pays for expansion. Later contracts are optional.", "첫 출하 보상으로 설비를 늘릴 수 있어요. 이후 납품은 추가 보상을 위한 선택 목표입니다."))),
    ("Make copper", ("miner","furnace","storage"), (
        ("Place a furnace with its output facing storage. Feed copper ore into its rear or sides.", "제련기 출력 화살표를 창고로 향하게 놓고 뒤나 옆에서 구리 광석을 넣으세요."),
        ("Click the furnace, press Q and select Copper smelting. Watch for ingots in storage.", "제련기 클릭 → Q → 구리 제련을 적용하고 창고에 구리 주괴가 쌓이는지 보세요."),
        ("For coal-fired copper, feed ore from the left and coal from below, with output to the right.", "석탄 구리 제련이라면 왼쪽에서 구리, 아래에서 석탄을 넣고 오른쪽으로 주괴를 빼세요."))),
    ("Unlock iron", ("storage","miner"), (
        ("Click the warehouse holding copper ingots. Select the ingot below the map.", "구리 주괴가 든 창고를 클릭한 뒤 맵 아래 재고 목록에서 구리 주괴를 선택하세요."),
        ("Choose a quantity and press T. Carry three ingots and keep 200 credits.", "수량을 고르고 T로 꺼내세요. 소지한 구리 주괴 3개와 200크레딧이 필요해요."),
        ("Open Research [Y] and research iron mining. Now place a miner on iron.", "연구 [Y]에서 철광석 채굴을 해금하고 철 광맥에 채굴기를 설치하세요."))),
    ("Manual sales", ("storage",), (
        ("Select a stocked warehouse, pick an item and use T to withdraw some.", "재고가 있는 창고를 클릭하고 팔 물품과 수량을 골라 T로 꺼내세요."),
        ("Open Sales desk [M] and click a green sale button. The wallet and sales total rise.", "판매소 [M]에서 초록색 판매 버튼을 누르세요. 보유 크레딧과 누적 매출이 함께 늘어요."),
        ("Spend credits on equipment. Keep materials for research and upgrades.", "판매금으로 설비를 늘리세요. 연구와 업그레이드에 필요한 재료는 일부 남겨 두세요."))),
    ("Process and research", ("furnace","press","drawer","forge"), (
        ("Smelt iron plates, then feed two plates to a gear press to make a gear.", "철광석을 제련해 철판을 만들고 기어 프레스에 철판 2장을 넣어 기어를 만드세요."),
        ("Research Advanced processing, then Factory automation with wire and steel.", "고급 가공 연구 후 전선 가공기로 구리 전선, 합금로로 강철을 만들어 공장 자동화를 연구하세요."),
        ("Check ingredients in the recipe book. Click a machine and press U to upgrade it.", "도움말의 재료 제작법에서 공정을 보세요. 설비 클릭 후 U를 누르면 재료와 돈으로 강화합니다."))),
    ("Automate sales", ("storage","extractor","seller"), (
        ("Place an extractor beside storage, with its arrow pointing away from that warehouse.", "창고 옆에 배출기를 놓고 화살표가 창고 바깥을 향하게 하세요."),
        ("Click the extractor and choose the item. Put an auto seller in front or connect a belt.", "배출기에서 품목을 고르세요. 화살표 앞에 자동 판매기를 놓거나 벨트로 연결하세요."),
        ("Watch cumulative sales reach 500,000. A control module lets the extractor keep reserves.", "누적 매출 50만이 엔딩 목표예요. 배출기에 제어 모듈을 장착하면 창고에 남길 수량을 정할 수 있어요."))),
)


def current_chapter(factory):
    kinds = {machine.kind for machine in factory.machines.values()}
    if not factory.starter_complete:
        return 0 if "miner" not in kinds else 1 if "storage" not in kinds else 2
    if "ore" not in factory.unlocked:
        if factory.player_inventory["copper"] + factory.warehouse_stock("copper") < 3:
            return 3
        return 4
    if not factory.total_sales:
        return 5
    return 6 if "automation" not in factory.unlocked else 7
