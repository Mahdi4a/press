"""Add Toman (IRT) as a currency, price every plan in it and bill Iranian teams in it.

Plans get price_irt from their USD price at the rate in Press Settings ("Toman per 1 USD"),
so they can be adjusted by hand afterwards. Only plans without a Toman price are filled.
"""

import frappe

from press.utils.gateway_settings import get_toman_per_usd

PLAN_DOCTYPES = (
	"Site Plan",
	"Server Plan",
	"Server Storage Plan",
	"Server Snapshot Plan",
	"S3 Storage Plan",
	"Static IP Plan",
	"Cluster Plan",
	"Marketplace App Plan",
)


# A Currency column holds up to 12 whole digits; a plan priced beyond that is not a real price
MAX_TOMAN = 10**11


def to_toman(usd: float, rate: int) -> float | None:
	"""Whole Toman, to the nearest thousand once the amount is large enough for that to be small."""
	toman = (usd or 0) * rate
	if toman >= MAX_TOMAN:
		return None
	return round(toman, -3) if toman >= 100000 else round(toman)


def set_price(doctype: str, name: str, usd: float, rate: int):
	toman = to_toman(usd, rate)
	if toman is None:
		print(f"{doctype} {name}: {usd} USD is too large to convert, price_irt left empty")
		return
	frappe.db.set_value(doctype, name, "price_irt", toman, update_modified=False)


def execute():
	create_currency()
	rate = get_toman_per_usd()

	for doctype in PLAN_DOCTYPES:
		for plan in frappe.get_all(doctype, fields=["name", "price_usd", "price_irt"]):
			if not plan.price_irt and plan.price_usd:
				set_price(doctype, plan.name, plan.price_usd, rate)

	# Add-ons are rows in a child table of the marketplace plan
	for row in frappe.get_all("Marketplace Add On", fields=["name", "price_usd", "price_irt"]):
		if not row.price_irt and row.price_usd:
			set_price("Marketplace Add On", row.name, row.price_usd, rate)

	seed_team_tiers(rate)
	bill_iranian_teams_in_toman(rate)


def seed_team_tiers(rate: int):
	"""Give each Team Tier Toman amounts, to be adjusted by hand. Only empty ones are filled."""
	for tier in frappe.get_all(
		"Team Tier", fields=["name", "amount", "amount_irt", "last_invoice_amount", "last_invoice_amount_irt"]
	):
		for usd_field, irt_field in (("amount", "amount_irt"), ("last_invoice_amount", "last_invoice_amount_irt")):
			if not tier.get(irt_field) and tier.get(usd_field):
				toman = to_toman(tier.get(usd_field), rate)
				if toman is not None:
					frappe.db.set_value("Team Tier", tier.name, irt_field, toman, update_modified=False)


def create_currency():
	if frappe.db.exists("Currency", "IRT"):
		frappe.db.set_value("Currency", "IRT", "enabled", 1)
		return

	frappe.get_doc(
		{
			"doctype": "Currency",
			"currency_name": "IRT",
			"enabled": 1,
			"symbol": "Toman",
			"symbol_on_right": 1,
			"number_format": "#,###",
		}
	).insert(ignore_permissions=True)


def bill_iranian_teams_in_toman(rate: int):
	"""Switch Iranian teams to IRT. A team with money history keeps USD, since its amounts are already recorded."""
	for team in frappe.get_all("Team", filters={"country": "Iran", "currency": ["!=", "IRT"]}, pluck="name"):
		has_history = frappe.db.exists("Balance Transaction", {"team": team}) or frappe.db.exists(
			"Invoice", {"team": team, "docstatus": ["!=", 2], "total": [">", 0]}
		)
		if has_history:
			print(f"Team {team} has billing history, left in USD")
			continue
		frappe.db.set_value("Team", team, "currency", "IRT", update_modified=False)
		# The spending limit was set in USD; it caps the team's subscriptions, now counted in Toman
		limit = frappe.db.get_value("Team", team, "spending_limit") or 0
		frappe.db.set_value("Team", team, "spending_limit", limit * rate, update_modified=False)
