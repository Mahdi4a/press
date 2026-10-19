from __future__ import annotations

from urllib.parse import urlparse

import frappe
import requests

from press.guards import role_guard
from press.utils import get_current_team
from press.utils.gateway_settings import get_gateway_setting, get_toman_limit, get_toman_per_usd

SANDBOX_API = "https://sandbox.zarinpal.com/pg/v4/payment"
SANDBOX_START_PAY = "https://sandbox.zarinpal.com/pg/StartPay"
LIVE_API = "https://payment.zarinpal.com/pg/v4/payment"
LIVE_START_PAY = "https://payment.zarinpal.com/pg/StartPay"
PENDING_TTL = 60 * 60
TIMEOUT = 15
# Zarinpal result codes meaning the payment is verified (101 = already verified before)
VERIFIED_CODES = (100, 101)
# How long a payment stays claimed once credited, so a late duplicate callback finds it
CLAIM_TTL = 24 * 60 * 60
# Smallest USD amount an Iranian team still billed in USD may top up
MINIMUM_USD_CREDIT = 5


def _urls() -> tuple[str, str]:
	if get_gateway_setting("zarinpal_live"):
		return LIVE_API, LIVE_START_PAY

	# The sandbox verifies any payment, so it would hand out free credits on a live site
	# that forgot to tick "Zarinpal Live Mode". It must be asked for.
	if not (frappe.conf.developer_mode or frappe.conf.get("zarinpal_allow_sandbox")):
		frappe.throw(
			"Zarinpal is in sandbox mode. Tick Zarinpal Live Mode in Press Settings, "
			"or set zarinpal_allow_sandbox in site_config.json for testing."
		)
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


def _claim_key(authority: str) -> bytes:
	return frappe.cache.make_key(f"zarinpal_claim:{authority}")


def _claim(authority: str) -> bool:
	"""Take the right to credit this payment. Only one callback gets it, however many arrive at once."""
	return bool(frappe.cache.set(_claim_key(authority), 1, nx=True, ex=CLAIM_TTL))


def _release(authority: str):
	frappe.cache.delete(_claim_key(authority))


def _own_origin(value: str | None) -> str:
	"""The browser's origin, only when it is this site. The bank sends the user back to it, so
	taking any value would let a caller point that redirect anywhere."""
	own = frappe.utils.get_url().rstrip("/")
	value = (value or "").rstrip("/")
	if value and urlparse(value).netloc in {urlparse(own).netloc, frappe.request.host}:
		return value
	return own


def _minimum_amount(team_currency: str) -> float:
	return get_toman_limit("minimum_credit_irt") if team_currency == "IRT" else MINIMUM_USD_CREDIT


@frappe.whitelist()
@role_guard.api("billing")
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
	if amount < _minimum_amount(team_currency):
		frappe.throw(f"Amount should be at least {_minimum_amount(team_currency)}")
	amount_toman = int(round(amount if team_currency == "IRT" else amount * _toman_per_usd()))
	api, start_pay = _urls()
	# The bank sends the browser back to where the payment was started, so the login cookie
	# of that address is still in effect
	origin = _own_origin(frappe.get_request_header("Origin"))

	try:
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
	except (requests.RequestException, ValueError):
		frappe.log_error("Zarinpal request could not be made", "Zarinpal Error")
		frappe.throw("Could not start the payment. Please try again later.")

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

	# Claiming first, not checking afterwards, is what stops a payment that is called back twice
	# at the same moment from being credited twice
	if pending and Status == "OK" and _claim(Authority):
		try:
			if _verify_and_credit(Authority, pending):
				redirect_to = f"{billing_url}?zarinpal=success"
			else:
				_release(Authority)
		except Exception:
			_release(Authority)
			frappe.log_error("Zarinpal payment could not be credited", "Zarinpal Error")
	elif Authority and not pending and frappe.cache.exists(_claim_key(Authority)):
		# The user reloaded the callback after it was credited
		redirect_to = f"{billing_url}?zarinpal=success"

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = redirect_to


def _verify_and_credit(authority: str, pending: dict) -> bool:
	"""Ask Zarinpal whether the payment went through and credit the team. True once it is credited."""
	api, _start = _urls()
	try:
		response = requests.post(
			f"{api}/verify.json",
			json={
				"merchant_id": _merchant_id(),
				"amount": pending["amount_toman"],
				"authority": authority,
			},
			headers={"Accept": "application/json"},
			timeout=TIMEOUT,
		).json()
	except (requests.RequestException, ValueError):
		frappe.log_error("Zarinpal verify could not be made", "Zarinpal Error")
		return False

	data = response.get("data") or {}
	if data.get("code") not in VERIFIED_CODES:
		frappe.log_error(f"Zarinpal verify failed: {response}", "Zarinpal Error")
		return False

	remark = f"Zarinpal {authority} (ref {data.get('ref_id')})"
	if not frappe.db.exists("Balance Transaction", {"description": ("like", f"Zarinpal {authority} %")}):
		# The bank sends the browser back here, often without a login cookie. Zarinpal
		# has just confirmed the payment, so crediting does not depend on who is asking.
		frappe.set_user("Administrator")
		frappe.get_doc("Team", pending["team"]).allocate_credit_amount(
			pending["amount_credit"], source="Prepaid Credits", remark=remark
		)
		# Frappe rolls a GET request back, and this is one: the bank redirects here
		frappe.db.commit()
	frappe.cache().delete_value(_cache_key(authority))
	return True
