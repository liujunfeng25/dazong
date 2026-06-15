import asyncio
from datetime import date

from routers.orders import order_meta, search_order_products


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeUser:
    id = 101
    role = "client"


class _FakeDelivery:
    def __init__(self, did=7):
        self.id = did
        self.company_name = "测试物流"
        self.username = "delivery001"


class _FakeContract:
    def __init__(self):
        self.id = 9
        self.period_start = date(2020, 1, 1)
        self.period_end = date(2099, 12, 31)
        self.category_ids_json = [3, 5]
        self.category_rates_json = [{"category_id": 3, "float_rate": 0.1}]
        self.price_float_rate = 0.05


class _FakeCategory:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name


class _FakeProduct:
    def __init__(self, pid, name, category1_id=3):
        self.id = pid
        self.name = name
        self.unit = "斤"
        self.spec = ""
        self.reference_price = 10.0
        self.category1_id = category1_id
        self.category2_id = None
        self.logo = None
        self.image_list_json = []
        self.standard_type = "standard"


class _MetaSession:
    def __init__(self, delivery_rows, deliveries, categories):
        self.delivery_rows = delivery_rows
        self.deliveries = deliveries
        self.categories = categories
        self._scalars_calls = 0

    async def execute(self, _stmt):
        return _ExecuteResult(self.delivery_rows)

    async def scalars(self, _stmt):
        self._scalars_calls += 1
        if self._scalars_calls == 1:
            return _ScalarsResult(self.deliveries)
        return _ScalarsResult(self.categories)


def test_order_meta_returns_contract_categories(monkeypatch):
    contract = _FakeContract()
    categories = [_FakeCategory(3, "蔬菜"), _FakeCategory(5, "肉禽")]

    async def _signed(_db, _client_id, _delivery_id):
        return contract

    async def _run():
        db = _MetaSession([(7,)], [_FakeDelivery(7)], categories)
        monkeypatch.setattr("routers.orders._signed_contract_for_order", _signed)
        user = _FakeUser()
        out = await order_meta(delivery_id=7, user=user, db=db)
        assert out["contract_categories"] == [
            {"id": 3, "name": "蔬菜"},
            {"id": 5, "name": "肉禽"},
        ]

    asyncio.run(_run())


def test_search_order_products_applies_category1_id(monkeypatch):
    captured = {}

    async def _serialize(_db, rows, _user_id, _delivery_id=None):
        return [{"id": r.id, "name": r.name, "category1_id": r.category1_id} for r in rows]

    async def _run():
        product = _FakeProduct(1, "大白菜", category1_id=3)

        class _SearchSession:
            async def scalar(self, stmt):
                captured["count_stmt"] = stmt
                return 1

            async def scalars(self, stmt):
                captured["select_stmt"] = stmt
                return _ScalarsResult([product])

        monkeypatch.setattr("routers.orders._serialize_order_products", _serialize)
        user = _FakeUser()
        out = await search_order_products(
            keyword="白菜",
            category1_id=3,
            contract_categories_only=False,
            user=user,
            db=_SearchSession(),
        )
        assert out["total"] == 1
        assert out["items"][0]["category1_id"] == 3
        assert captured["count_stmt"] is not None
        assert captured["select_stmt"] is not None

    asyncio.run(_run())
