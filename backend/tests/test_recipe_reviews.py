import unittest
from types import SimpleNamespace
from uuid import uuid4
from pydantic import ValidationError
from fastapi import HTTPException
from app.dependencies import TokenData
from app.schemas.recipe_review import RecipeProposal
from app.services.recipe_review_service import can_manage, transition_allowed, visible
from sqlalchemy.dialects import postgresql

class RecipeReviewTests(unittest.TestCase):
    def test_scoped_approver_and_maker_checker(self):
        owner=uuid4()
        actor=TokenData(user_id=owner,company_id=uuid4(),brand_id=uuid4(),branch_id=uuid4(),permissions=["company.kitchen.manage"],scope_types=["branch"])
        self.assertFalse(can_manage(actor))
        actor.scope_types=["company"]
        self.assertTrue(can_manage(actor))
        row=SimpleNamespace(created_by=owner,status="submitted")
        with self.assertRaises(HTTPException): transition_allowed(row,actor,"approve")
        actor.user_id=uuid4()
        transition_allowed(row,actor,"approve")
        row.status="approved_hold"
        for action in ["save","submit","approve","return","reject","resolve"]:
            with self.assertRaises(HTTPException): transition_allowed(row,actor,action)

    def test_branch_visibility(self):
        actor=TokenData(user_id=uuid4(),company_id=uuid4(),brand_id=uuid4(),branch_id=uuid4(),permissions=["fb.recipe.manage"])
        sql=str(visible(actor).compile(dialect=postgresql.dialect()))
        self.assertIn("company_id =",sql); self.assertIn("brand_id =",sql); self.assertIn("branch_id =",sql)

    def test_proposal_validation(self):
        item=uuid4()
        p=dict(output_id=uuid4(),name="Test",recipe_type="production",yield_qty="1",yield_unit="kg",effective_from="2026-10-14",reason="Test reason",
            ingredients=[dict(item_id=item,quantity="1",unit="kg")])
        RecipeProposal.model_validate(p)
        for change in [dict(yield_qty=0),dict(loss_percent=100),dict(output_id=item),dict(ingredients=p["ingredients"]*2),
                       dict(ingredients=[dict(item_id=None,quantity=1,unit="kg")])]:
            with self.assertRaises(ValidationError): RecipeProposal.model_validate({**p,**change})

    def test_publish_requires_approved_state_and_different_manager(self):
        actor=TokenData(user_id=uuid4(),company_id=uuid4(),branch_id=None,permissions=["company.kitchen.manage"],scope_types=["company"])
        row=SimpleNamespace(created_by=uuid4(),status="draft")
        with self.assertRaises(HTTPException): transition_allowed(row,actor,"publish")
        row.status="approved_hold"
        transition_allowed(row,actor,"publish")
        row.created_by=actor.user_id
        with self.assertRaises(HTTPException): transition_allowed(row,actor,"publish")

class RecipeHistoricalReturnTests(unittest.IsolatedAsyncioTestCase):
    async def test_restaurant_return_uses_sale_snapshot_not_current_recipe(self):
        from decimal import Decimal
        from unittest.mock import AsyncMock
        from app.services.store_inventory_service import StoreInventoryService
        company, menu_id, ingredient_id = uuid4(), uuid4(), uuid4()
        ingredient = SimpleNamespace(id=ingredient_id, company_id=company, cost_price=2)
        db = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(new_value={"recipe_snapshots": [{
            "menu_product_id": str(menu_id), "sold_qty": "2", "recipe_id": str(uuid4()), "version": 1,
            "ingredients": [{"product_id": str(ingredient_id), "quantity": "600", "unit": "g"}]}]})),
            get=AsyncMock(return_value=ingredient))
        service = StoreInventoryService(db)
        service._expand_items = AsyncMock(side_effect=AssertionError("Must not read today's recipe"))
        service.stock_service._get_or_create_balance = AsyncMock(return_value=SimpleNamespace(cost_per_unit=2))
        service.stock_service._record_movement = AsyncMock()
        order = SimpleNamespace(id=uuid4(), recipe_stock_posted_at=True, recipe_stock_reversed_at=None)
        await service.reverse_items(order=order, company_id=company, brand_id=uuid4(), branch_id=uuid4(), location_id=uuid4(),
            user_id=uuid4(), items=[(SimpleNamespace(id=menu_id), Decimal("1"))], reference_type="test_refund", note="Return")
        self.assertEqual(service.stock_service._record_movement.call_args.kwargs["qty_delta"], Decimal("300.0000"))
        service._expand_items.assert_not_called()

    async def test_legacy_partial_return_fails_closed_without_frozen_bom(self):
        from unittest.mock import AsyncMock
        from app.services.store_inventory_service import StoreInventoryService
        service = StoreInventoryService(SimpleNamespace(scalar=AsyncMock(return_value=None)))
        service._expand_items = AsyncMock(side_effect=AssertionError("Never use today's recipe"))
        with self.assertRaises(HTTPException) as raised:
            await service.reverse_items(order=SimpleNamespace(id=uuid4(), recipe_stock_posted_at=True, recipe_stock_reversed_at=None),
                company_id=uuid4(), brand_id=uuid4(), branch_id=uuid4(), location_id=uuid4(), user_id=uuid4(),
                items=[], reference_type="test_partial", note="Return")
        self.assertEqual(raised.exception.status_code, 409)
        service._expand_items.assert_not_called()

if __name__=="__main__": unittest.main()
