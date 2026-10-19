"""The currencies Press bills in, and the plan price column each one reads.

A team is billed in one currency, chosen from its country when it is created. Every
plan keeps a price per currency (price_usd, price_inr, price_irt), so code that picks
a price should go through here instead of comparing the currency to "INR".
"""

from __future__ import annotations

USD = "USD"
INR = "INR"
IRT = "IRT"  # Iranian Toman

PRICE_FIELDS = {USD: "price_usd", INR: "price_inr", IRT: "price_irt"}
SYMBOLS = {USD: "$", INR: "₹", IRT: "Toman"}


def price_field(currency: str | None) -> str:
	"""The plan column holding prices in this currency. USD for anything unknown."""
	return PRICE_FIELDS.get(currency or USD, PRICE_FIELDS[USD])


def currency_symbol(currency: str | None) -> str:
	return SYMBOLS.get(currency or USD, SYMBOLS[USD])


def currency_for_country(country: str | None) -> str:
	"""The currency a team in this country is billed in."""
	if country == "India":
		return INR
	if country == "Iran":
		return IRT
	return USD


# Fixed USD/INR rate the partner program has always used to compare billing across the two
INR_PER_USD_PARTNER = 83


def partner_amount(amount: float, from_currency: str | None, to_currency: str | None) -> float | None:
	"""An invoice amount as the partner program counts it, in the partner's currency.

	Same currency is returned untouched. USD and INR convert at the fixed partner rate. Toman has
	no rate at all, so anything crossing it returns None and the caller leaves the amount out."""
	if from_currency == to_currency:
		return amount
	if IRT in (from_currency, to_currency):
		return None
	if to_currency == USD:
		return amount / INR_PER_USD_PARTNER
	return amount * INR_PER_USD_PARTNER


def ensure_toman_currency():
	"""Create the Toman Currency record, or enable it. A new site has none, since patches do not run on install."""
	import frappe

	if frappe.db.exists("Currency", IRT):
		frappe.db.set_value("Currency", IRT, "enabled", 1)
		return

	frappe.get_doc(
		{
			"doctype": "Currency",
			"currency_name": IRT,
			"enabled": 1,
			"symbol": SYMBOLS[IRT],
			"symbol_on_right": 1,
			"number_format": "#,###",
		}
	).insert(ignore_permissions=True)
