from __future__ import annotations

import inspect
import unittest

from fastapi.params import Depends

from app.database import get_db, get_identity_db, get_restaurant_service_db
from app.routers import restaurant, system


def dependency_for(endpoint: object, parameter: str):
    default = inspect.signature(endpoint).parameters[parameter].default
    if not isinstance(default, Depends):
        raise AssertionError(f"{parameter} is not a FastAPI dependency")
    return default.dependency


class RestaurantServiceRoutingTests(unittest.TestCase):
    def test_fb_and_public_workflows_use_restaurant_service_database(self) -> None:
        for endpoint in (
            restaurant.get_fb_settings,
            restaurant.update_fb_settings,
            restaurant.setup_fb_workspace,
            restaurant.list_tables,
            restaurant.create_table,
            restaurant.get_table,
            restaurant.update_table,
            restaurant.delete_table,
            restaurant.list_sessions,
            restaurant.open_session,
            restaurant.get_session,
            restaurant.get_session_detail,
            restaurant.place_order,
            restaurant.cancel_order,
            restaurant.cancel_order_item,
            restaurant.update_order_item_status,
            restaurant.request_bill,
            restaurant.checkout_session,
            restaurant.get_session_payment_qr,
            restaurant.close_session,
            restaurant.list_kitchen_tickets,
            restaurant.update_ticket,
            restaurant.get_pickup_queue,
            restaurant.mark_pickup_queue_served,
            restaurant.public_get_menu,
            restaurant.public_place_order,
            restaurant.public_order_status,
            restaurant.public_request_bill,
            restaurant.qs_get_menu,
            restaurant.qs_place_order,
            restaurant.qs_order_status,
        ):
            with self.subTest(endpoint=endpoint.__name__):
                self.assertIs(
                    dependency_for(endpoint, "db"),
                    get_restaurant_service_db,
                )

    def test_platform_and_central_workflows_remain_on_legacy_database(self) -> None:
        for endpoint in (
            restaurant.create_brand,
            restaurant.update_brand,
            restaurant.update_brand_transfer_config,
            restaurant.ingredient_usage_report,
        ):
            with self.subTest(endpoint=endpoint.__name__):
                self.assertIs(dependency_for(endpoint, "db"), get_db)

    def test_system_branch_settings_split_access_and_operational_sessions(self) -> None:
        for endpoint in (
            system.get_branch_settings,
            system.update_branch_settings,
            system.upload_branch_promptpay_qr,
            system.delete_branch_promptpay_qr,
            system.upload_branch_receipt_logo,
            system.delete_branch_receipt_logo,
        ):
            with self.subTest(endpoint=endpoint.__name__):
                self.assertIs(
                    dependency_for(endpoint, "db"),
                    get_restaurant_service_db,
                )
                self.assertIs(
                    dependency_for(endpoint, "identity_db"),
                    get_identity_db,
                )
