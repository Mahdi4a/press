# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from press.api.regional_payments.zarinpal import utils
from press.press.doctype.team.test_team import create_test_team

AUTHORITY = "A00000000000000000000000000000000001"


def verified(code=100):
	return Mock(json=Mock(return_value={"data": {"code": code, "ref_id": 7}}))


class TestZarinpalCallback(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.team = create_test_team()
		frappe.cache().set_value(
			utils._cache_key(AUTHORITY),
			{"team": self.team.name, "amount_credit": 500000, "amount_toman": 500000, "origin": ""},
			expires_in_sec=60,
		)
		patcher = patch.object(utils, "_urls", return_value=(utils.LIVE_API, utils.LIVE_START_PAY))
		patcher.start()
		self.addCleanup(patcher.stop)
		patcher = patch.object(utils, "_merchant_id", return_value="merchant")
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(utils._release, AUTHORITY)
		self.addCleanup(frappe.cache().delete_value, utils._cache_key(AUTHORITY))

	def credits(self) -> int:
		return frappe.db.count("Balance Transaction", {"description": ("like", f"Zarinpal {AUTHORITY} %")})

	@patch.object(utils.requests, "post", return_value=verified())
	def test_a_second_callback_does_not_credit_again(self, post):
		utils.verify_payment(AUTHORITY, "OK")
		utils.verify_payment(AUTHORITY, "OK")

		self.assertEqual(self.credits(), 1)
		self.assertEqual(post.call_count, 1)
		self.assertTrue(frappe.local.response["location"].endswith("?zarinpal=success"))

	@patch.object(utils.requests, "post", return_value=verified())
	def test_a_callback_that_lost_the_claim_credits_nothing(self, post):
		utils._claim(AUTHORITY)

		utils.verify_payment(AUTHORITY, "OK")

		self.assertEqual(self.credits(), 0)
		self.assertEqual(post.call_count, 0)

	@patch.object(utils.requests, "post", return_value=verified(code=-50))
	def test_a_payment_zarinpal_rejects_is_not_credited_and_can_be_retried(self, post):
		utils.verify_payment(AUTHORITY, "OK")

		self.assertEqual(self.credits(), 0)
		self.assertTrue(frappe.local.response["location"].endswith("?zarinpal=failed"))
		self.assertTrue(utils._claim(AUTHORITY))

	@patch.object(utils.requests, "post", side_effect=utils.requests.ConnectionError)
	def test_an_unreachable_gateway_redirects_instead_of_erroring(self, post):
		utils.verify_payment(AUTHORITY, "OK")

		self.assertEqual(self.credits(), 0)
		self.assertTrue(frappe.local.response["location"].endswith("?zarinpal=failed"))

	def test_a_cancelled_payment_is_not_verified(self):
		with patch.object(utils.requests, "post") as post:
			utils.verify_payment(AUTHORITY, "NOK")

		post.assert_not_called()
		self.assertEqual(self.credits(), 0)


class TestZarinpalOrigin(FrappeTestCase):
	def test_another_site_is_not_used_as_the_return_address(self):
		own = frappe.utils.get_url().rstrip("/")

		self.assertEqual(utils._own_origin("https://evil.example"), own)
		self.assertEqual(utils._own_origin(None), own)
		self.assertEqual(utils._own_origin(own), own)
