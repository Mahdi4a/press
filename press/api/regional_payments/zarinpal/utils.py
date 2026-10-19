from __future__ import annotations

import frappe
import requests

from press.utils import get_current_team
from press.utils.gateway_settings import get_gateway_setting, get_toman_per_usd

SANDBOX_API = "https://sandbox.zarinpal.com/pg/v4/payment"
SANDBOX_START_PAY = "https://sandbox.zarinpal.com/pg/StartPay"
LIVE_API = "https://payment.zarinpal.com/pg/v4/payment"
LIVE_START_PAY = "https://payment.zarinpal.com/pg/StartPay"
PENDING_TTL = 60 * 60
TIMEOUT = 15
# Zarinpal result codes meaning the payment is verified (101 = already verified before)
VERIFIED_CODES = (100, 101)


def _urls() -> tuple[str, str]:
	# Sandbox unless "Zarinpal Live Mode" is explicitly ticked in Press Settings
	if get_gateway_setting("zarinpal_live"):
		return LIVE_API, LIVE_START_PAY
	return SANDBOX_API, SANDBOX_START_PAY


def _merchant_id() -> str:
	merchant_id = get_gateway_setting("zarinpal_merchant_id")
	if not merchant_id:
		frappe.throw("Zarinpal is not configured. Set the Zarinpal Merchant ID in Press Settings.")
	return merchant_id


def _toman_per_usd() -> int:
	return get_toman_per_usd()


def _cache_key(authority: str) -> str:
	return f"zarinpal_pending:{authority}"


@frappe.whitelist()
def create_payment(amount: float):
	"""Start a Zarinpal payment that tops up the current team's prepaid credits. Returns the gateway URL.

	`amount` is in the team's currency: Toman for teams billed in IRT. An Iranian team still
	billed in USD (it has history in USD) pays the Toman equivalent at the configured rate.
	"""
	amount = float(amount)
	if amount <= 0:
		frappe.throw("Amount must be greater than zero")

	team = get_current_team()
	team_currency = frappe.db.get_value("Team", team, "currency")
	amount_toman = int(round(amount if team_currency == "IRT" else amount * _toman_per_usd()))
	api, start_pay = _urls()
	# The bank sends the browser back to where the payment was started, so the login cookie
	# of that address is still in effect
	origin = (frappe.get_request_header("Origin") or frappe.utils.get_url()).rstrip("/")

	response = requests.post(
		f"{api}/request.json",
		json={
			"merchant_id": _merchant_id(),
			"amount": amount_toman,
			"currency": "IRT",
			"description": f"Prepaid credits for {team}",
			"callback_url": f"{origin}/api/method/press.api.regional_payments.zarinpal.utils.verify_payment",
		},
		headers={"Accept": "application/json"},
		timeout=TIMEOUT,
	).json()

	data = response.get("data") or {}
	if data.get("code") != 100 or not data.get("authority"):
		frappe.log_error(f"Zarinpal request failed: {response}", "Zarinpal Error")
		frappe.throw("Could not start the payment. Please try again later.")

	authority = data["authority"]
	frappe.cache().set_value(
		_cache_key(authority),
		{"team": team, "amount_credit": amount, "amount_toman": amount_toman, "origin": origin},
		expires_in_sec=PENDING_TTL,
	)
	return f"{start_pay}/{authority}"


@frappe.whitelist(allow_guest=True)
def verify_payment(Authority: str | None = None, Status: str | None = None):  # noqa: N803
	"""Zarinpal callback. Verifies the payment and credits the team, then redirects to billing."""
	pending = frappe.cache().get_value(_cache_key(Authority)) if Authority else None
	origin = (pending or {}).get("origin") or frappe.utils.get_url().rstrip("/")
	billing_url = f"{origin}/dashboard/billing"
	redirect_to = f"{billing_url}?zarinpal=failed"

	if pending and Status == "OK":
		api, _start = _urls()
		response = requests.post(
			f"{api}/verify.json",
			json={
				"merchant_id": _merchant_id(),
				"amount": pending["amount_toman"],
				"authority": Authority,
			},
			headers={"Accept": "application/json"},
			timeout=TIMEOUT,
		).json()
		data = response.get("data") or {}

		if data.get("code") in VERIFIED_CODES:
			remark = f"Zarinpal {Authority} (ref {data.get('ref_id')})"
			# Idempotent: the user may reload the callback URL
			if not frappe.db.exists("Balance Transaction", {"description": ("like", f"Zarinpal {Authority}%")}):
				# The bank sends the browser back here, often without a login cookie. Zarinpal
				# has just confirmed the payment, so crediting does not depend on who is asking.
				frappe.set_user("Administrator")
				frappe.get_doc("Team", pending["team"]).allocate_credit_amount(
					pending["amount_credit"], source="Prepaid Credits", remark=remark
				)
				# Frappe rolls a GET request back, and this is one: the bank redirects here
				frappe.db.commit()
			frappe.cache().delete_value(_cache_key(Authority))
			redirect_to = f"{billing_url}?zarinpal=success"
		else:
			frappe.log_error(f"Zarinpal verify failed: {response}", "Zarinpal Error")

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = redirect_to
