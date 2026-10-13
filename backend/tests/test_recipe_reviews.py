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

    def test_no_publish_endpoint(self):
        from app.routers.recipe_reviews import router
        self.assertFalse(any("publish" in r.path or "activate" in r.path for r in router.routes))

if __name__=="__main__": unittest.main()
