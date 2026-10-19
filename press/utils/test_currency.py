# Copyright (c) 2026, Frappe and Contributors
# See license.txt
from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from press.utils.currency import IRT, USD, currency_for_country, currency_symbol, price_field


class TestCurrency(FrappeTestCase):
	def test_price_field_per_currency(self):
		self.assertEqual(price_field("USD"), "price_usd")
		self.assertEqual(price_field("INR"), "price_inr")
		self.assertEqual(price_field("IRT"), "price_irt")

	def test_price_field_falls_back_to_usd(self):
		self.assertEqual(price_field(None), "price_usd")
		self.assertEqual(price_field("EUR"), "price_usd")

	def test_currency_symbol(self):
		self.assertEqual(currency_symbol("USD"), "$")
		self.assertEqual(currency_symbol("INR"), "₹")
		self.assertEqual(currency_symbol("IRT"), "Toman")
		self.assertEqual(currency_symbol(None), "$")

	def test_team_currency_comes_from_country(self):
		self.assertEqual(currency_for_country("India"), "INR")
		self.assertEqual(currency_for_country("Iran"), IRT)
		self.assertEqual(currency_for_country("France"), USD)
		self.assertEqual(currency_for_country(None), USD)
