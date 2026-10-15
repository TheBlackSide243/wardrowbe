from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.wishlist import WishlistItem
from app.services.link_preview import LinkPreview
from app.services.price_watch import apply_price
from app.services.season_swap import plan_swap
from app.services.stylist_service import resolve_citations, wardrobe_listing

OCTOBER = date(2026, 10, 15)


def _item(item_type: str, seasons: list[str] | None = None, **fields) -> ClothingItem:
    return ClothingItem(
        id=uuid4(),
        type=item_type,
        image_path=f"{item_type}.jpg",
        status=ItemStatus.ready,
        season=seasons or [],
        **fields,
    )


class TestSeasonSwap:
    def test_october_in_the_north(self):
        coat = _item("coat", ["winter"])
        shorts = _item("shorts", ["summer"])
        jeans = _item("jeans", ["all-season"])
        jumper = _item("sweater", ["fall", "winter"])
        plan = plan_swap([coat, shorts, jeans, jumper], OCTOBER, 45.7, set())
        assert (plan.current, plan.upcoming) == ("fall", "winter")
        assert [i for i, _ in plan.bring_out] == [coat]
        assert [i for i, _ in plan.put_away] == [shorts]
        assert plan.stays == 2

    def test_southern_hemisphere_is_reversed(self):
        shorts = _item("shorts", ["summer"])
        plan = plan_swap([shorts], OCTOBER, -33.9, set())
        assert (plan.current, plan.upcoming) == ("spring", "summer")
        assert [i for i, _ in plan.bring_out] == [shorts]

    def test_recently_worn_items_stay_out(self):
        shorts = _item("shorts", ["summer"], last_worn_at=OCTOBER - timedelta(days=3))
        assert plan_swap([shorts], OCTOBER, 45.7, set()).put_away == []

    def test_untagged_items_follow_last_year(self):
        scarf = _item("scarf")
        plan = plan_swap([scarf], OCTOBER, 45.7, {scarf.id})
        assert plan.bring_out == [(scarf, "last_year")]

    @pytest.mark.asyncio
    async def test_endpoint(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="sandals",
                image_path="s.jpg",
                status=ItemStatus.ready,
                season=["summer"],
            )
        )
        await db_session.commit()
        response = await client.get("/api/v1/season-swap", headers=auth_headers)
        assert response.status_code == 200, response.json()
        data = response.json()
        assert {"current_season", "upcoming_season", "put_away", "bring_out", "stays"} <= set(data)


class TestPriceWatch:
    def _entry(self, price: str | None, current: str | None = None) -> WishlistItem:
        return WishlistItem(
            name="Giacca",
            price=Decimal(price) if price else None,
            current_price=Decimal(current) if current else None,
            link="https://shop.example.com/p/1",
        )

    def test_reports_a_drop_once_per_new_low(self):
        now = datetime.now(UTC)
        entry = self._entry("129.90")
        drop = apply_price(entry, Decimal("99.00"), now)
        assert drop and drop.old == Decimal("129.90") and drop.new == Decimal("99.00")
        assert entry.price_dropped_at == now
        assert apply_price(entry, Decimal("99.00"), now) is None
        assert apply_price(entry, Decimal("89.00"), now) is not None

    def test_back_to_full_price_clears_the_drop(self):
        now = datetime.now(UTC)
        entry = self._entry("50", current="40")
        entry.price_dropped_at = now
        assert apply_price(entry, Decimal("50"), now) is None
        assert entry.price_dropped_at is None

    def test_first_reading_sets_the_reference_price(self):
        entry = self._entry(None)
        assert apply_price(entry, Decimal("30"), datetime.now(UTC)) is None
        assert entry.price == Decimal("30")

    @pytest.mark.asyncio
    async def test_check_now_endpoint(self, client: AsyncClient, auth_headers):
        created = await client.post(
            "/api/v1/wishlist",
            json={"name": "Giacca", "link": "https://shop.example.com/p/1", "price": "100"},
            headers=auth_headers,
        )
        preview = LinkPreview(url="https://shop.example.com/p/1", price=Decimal("80"))
        with patch("app.services.price_watch.fetch_preview", AsyncMock(return_value=preview)):
            response = await client.post("/api/v1/wishlist/check-prices", headers=auth_headers)
        assert response.status_code == 200, response.json()
        entry = response.json()[0]
        assert entry["id"] == created.json()["id"]
        assert Decimal(entry["current_price"]) == Decimal("80")
        assert entry["price_dropped_at"] is not None


class TestStylist:
    def test_citations_become_item_references(self):
        jacket, sneakers = _item("jacket"), _item("sneakers")
        reply = resolve_citations("Prova la giacca [#1] con [#2] e [#9].", [jacket, sneakers])
        assert reply.text == f"Prova la giacca [[item:{jacket.id}]] con [[item:{sneakers.id}]] e ."
        assert reply.items == [jacket, sneakers]

    def test_listing_numbers_every_item(self):
        listing = wardrobe_listing([_item("jeans", ["all-season"], primary_color="blue")])
        assert listing == "1. blue jeans (all-season)"

    @pytest.mark.asyncio
    async def test_chat_endpoint(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add(
            ClothingItem(
                user_id=test_user.id, type="jeans", image_path="j.jpg", status=ItemStatus.ready
            )
        )
        await db_session.commit()
        with patch(
            "app.services.ai_service.AIService._call_with_fallback",
            AsyncMock(return_value=("Metti i jeans [#1].", None, None)),
        ):
            response = await client.post(
                "/api/v1/stylist",
                json={"messages": [{"role": "user", "content": "Cosa metto oggi?"}]},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["reply"].startswith("Metti i jeans [[item:")
        assert data["items"][0]["type"] == "jeans"

    @pytest.mark.asyncio
    async def test_last_turn_must_be_the_user(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/stylist",
            json={"messages": [{"role": "assistant", "content": "Ciao"}]},
            headers=auth_headers,
        )
        assert response.status_code == 422
