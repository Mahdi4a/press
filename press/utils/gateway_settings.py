from __future__ import annotations

import frappe
from frappe.utils.password import get_decrypted_password

DEFAULT_TOMAN_PER_USD = 100000


def get_toman_per_usd() -> int:
	"""The dollar rate, only for turning old USD amounts into Toman (an Iranian team still billed in
	USD, or seeding plan prices). Nothing a Toman team is charged or limited by depends on it."""
	return int(get_gateway_setting("zarinpal_toman_per_usd") or DEFAULT_TOMAN_PER_USD)


# Limits for teams billed in Toman, each its own Press Settings value with this default
TOMAN_LIMIT_DEFAULTS = {
	"minimum_credit_irt": 500_000,
	"server_credit_threshold_irt": 20_000_000,
	"default_spending_limit_irt": 10_000_000,
	"referral_threshold_irt": 2_500_000,
	"minimum_partner_mrr_irt": 10_000_000,
}


def get_toman_limit(fieldname: str) -> int:
	return int(get_gateway_setting(fieldname) or TOMAN_LIMIT_DEFAULTS[fieldname])


def get_gateway_setting(fieldname: str, password: bool = False):
	"""A Press Settings value for the SMS and payment gateways.

	Falls back to the same key in site_config.json while the field is still empty,
	so setups made before these fields existed keep working. Zero counts as a value
	(a unticked checkbox), only None and an empty string fall through.
	"""
	if password:
		value = get_decrypted_password("Press Settings", "Press Settings", fieldname, raise_exception=False)
	else:
		value = frappe.db.get_single_value("Press Settings", fieldname)

	if value is None or value == "":
		return frappe.conf.get(fieldname)
	return value
