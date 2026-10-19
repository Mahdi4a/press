from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from press.api.partner import calculate_partner_tier, get_partner_tier_targets, transfer_credits
from press.press.doctype.team.team import Team
from press.press.doctype.team.test_team import create_test_team
from press.utils.currency import partner_amount


def make_tier(title: str, target_in_irt: float):
	return frappe.get_doc(
		{"doctype": "Partner Tier", "title": title, "enabled": 1, "target_in_irt": target_in_irt}
	).insert(ignore_permissions=True)


class TestPartnerToman(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_calculate_partner_tier_picks_highest_toman_target_reached(self):
		low = make_tier("Test IRT Low", 1_000_000)
		high = make_tier("Test IRT High", 5_000_000)

		self.assertEqual(calculate_partner_tier(3_000_000, "IRT")["name"], low.name)
		self.assertEqual(calculate_partner_tier(6_000_000, "IRT")["name"], high.name)

	def test_get_partner_tier_targets_returns_toman_targets_by_title(self):
		make_tier("Test IRT Target", 7_500_000)
		self.assertEqual(get_partner_tier_targets("IRT")["Test IRT Target"], 7_500_000)

	def test_partner_amount_never_converts_toman(self):
		self.assertEqual(partner_amount(500, "IRT", "IRT"), 500)
		self.assertIsNone(partner_amount(500, "USD", "IRT"))
		self.assertIsNone(partner_amount(500, "IRT", "INR"))
		self.assertEqual(partner_amount(830, "INR", "USD"), 10)
		self.assertEqual(partner_amount(10, "USD", "INR"), 830)

	def _transfer(self, partner_currency: str, customer_currency: str):
		partner = create_test_team()
		partner.db_set({"currency": partner_currency, "erpnext_partner": 1, "partner_status": "Active"})
		customer = create_test_team()
		customer.db_set("currency", customer_currency)
		partner.reload()
		with (
			patch("press.api.partner.get_current_team", return_value=partner),
			patch.object(Team, "get_balance", return_value=10_000_000),
			patch.object(Team, "get_partner_level", return_value=None),
			patch.object(Team, "allocate_credit_amount") as allocate,
		):
			return transfer_credits(1000, customer.name), allocate

	def test_transfer_credits_refuses_toman_partner_to_other_currency_customer(self):
		with self.assertRaisesRegex(frappe.ValidationError, "billed in Toman"):
			self._transfer("IRT", "USD")

	def test_transfer_credits_refuses_other_currency_partner_to_toman_customer(self):
		with self.assertRaisesRegex(frappe.ValidationError, "billed in Toman"):
			self._transfer("INR", "IRT")

	def test_transfer_credits_between_toman_teams_moves_plain_toman(self):
		_, allocate = self._transfer("IRT", "IRT")
		self.assertEqual(allocate.call_args_list[0].args[0], 1000)
