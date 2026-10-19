from __future__ import annotations

import frappe
import requests
from iran_base.utils.sms import try_normalize_mobile

from press.utils.gateway_settings import get_gateway_setting

SIGNALADS_BASE_URL = "https://transmitor.signalads.com"
TIMEOUT = 15


# Accounts that sign up with a mobile number get a placeholder email so the rest of
# Press, which identifies users by email, keeps working. OTPs for these go out by SMS.
PHONE_EMAIL_DOMAIN = "phone.press.local"


# Codes one number may be sent per hour and per day. SMS in Iran can arrive minutes late, so a
# real user presses "resend" several times; texting a stranger over and over is what this stops.
# Both are set in Press Settings (SMS Limits), or in site_config.json under the same names.
HOURLY_LIMIT_PER_MOBILE = 10
DAILY_LIMIT_PER_MOBILE = 30
COUNT_WINDOW = """
local sent = redis.call('INCR', KEYS[1])
if sent == 1 then
	redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return sent
"""


class SMSNotConfigured(frappe.ValidationError):
	pass


def normalize_mobile(mobile: str) -> str:
	"""Return an Iranian mobile as 09XXXXXXXXX. Accepts +98 / 0098 / 98 / 9 prefixes and Persian digits."""
	if (normalized := try_normalize_mobile(mobile)) is None:
		frappe.throw("Invalid mobile number", frappe.ValidationError)
	return normalized


def email_from_mobile(mobile: str) -> str:
	return f"{normalize_mobile(mobile)}@{PHONE_EMAIL_DOMAIN}"


def mobile_from_email(email: str) -> str | None:
	"""The mobile number behind a placeholder email, or None for a real email."""
	local, _, domain = str(email or "").strip().lower().partition("@")
	return local if domain == PHONE_EMAIL_DOMAIN else None


def user_for_mobile(mobile: str) -> str | None:
	"""The user who owns this mobile number, whatever email that account now has."""
	return frappe.db.get_value("User", {"mobile_no": normalize_mobile(mobile)}, "name")


def setup_mobile_user(doc, method=None):
	"""User after_insert hook for accounts created with a mobile number.

	The mobile number is kept on the user so the account can be found by it after the
	placeholder email is replaced. A global Email Unsubscribe makes Frappe's email queue
	drop every message to the placeholder address.
	"""
	mobile = mobile_from_email(doc.name)
	if not mobile:
		return

	doc.db_set("mobile_no", mobile, update_modified=False)
	if not frappe.db.exists("Email Unsubscribe", {"email": doc.name}):
		frappe.get_doc(
			{"doctype": "Email Unsubscribe", "email": doc.name, "global_unsubscribe": 1}
		).insert(ignore_permissions=True)


def send_otp_to_mobile(mobile: str, code: str | int):
	"""Queue an OTP SMS so how long delivery takes does not depend on the request."""
	mobile = normalize_mobile(mobile)
	for window, seconds, limit in (
		("hour", 60 * 60, get_gateway_setting("sms_hourly_limit_per_mobile") or HOURLY_LIMIT_PER_MOBILE),
		("day", 24 * 60 * 60, get_gateway_setting("sms_daily_limit_per_mobile") or DAILY_LIMIT_PER_MOBILE),
	):
		key = frappe.cache.make_key(f"press_sms_{window}:{mobile}")
		if frappe.cache.eval(COUNT_WINDOW, 1, key, seconds) > int(limit):
			frappe.throw("Too many codes have been sent to this number. Please try again later.")

	frappe.enqueue(
		"press.utils.sms.send_otp_sms",
		queue="short",
		enqueue_after_commit=True,
		mobile=mobile,
		code=str(code),
	)


def _config() -> tuple[str, str]:
	token = get_gateway_setting("signalads_token", password=True)
	sender = get_gateway_setting("signalads_sender")
	if not (token and sender):
		frappe.throw(
			"SMS is not configured. Set the Signalads API token and sender number in Press Settings.",
			SMSNotConfigured,
		)
	return token, sender


def send_sms(mobile: str, message: str) -> dict:
	"""Send a plain SMS through Signalads (Transmitor)."""
	token, sender = _config()
	response = requests.post(
		f"{SIGNALADS_BASE_URL}/api_v1/sms/send",
		headers={"Authorization": f"Bearer {token}"},
		json={"from": sender, "message": message, "numbers": [normalize_mobile(mobile)]},
		timeout=TIMEOUT,
	)
	if not response.ok:
		frappe.log_error(f"Signalads SMS failed: {response.status_code} {response.text}", "SMS Error")
		frappe.throw("Could not send SMS. Please try again later.")
	return response.json()


def send_pattern_sms(mobile: str, pattern_id: int, parameters: dict[str, str]) -> dict:
	"""Send a SMS built from a pre-approved Signalads pattern (required by most Iranian lines for OTPs)."""
	token, sender = _config()
	response = requests.post(
		f"{SIGNALADS_BASE_URL}/api_v1/patterns/send",
		headers={"Authorization": f"Bearer {token}"},
		json={
			"from": sender,
			"pattern_id": int(pattern_id),
			"number": normalize_mobile(mobile),
			"parameters": {k: str(v) for k, v in parameters.items()},
		},
		timeout=TIMEOUT,
	)
	if not response.ok:
		frappe.log_error(f"Signalads pattern SMS failed: {response.status_code} {response.text}", "SMS Error")
		frappe.throw("Could not send SMS. Please try again later.")
	return response.json()


def send_otp_sms(mobile: str, code: str | int) -> dict:
	"""Send an OTP code, via a pattern when `signalads_otp_pattern_id` is set, else as plain text."""
	pattern_id = get_gateway_setting("signalads_otp_pattern_id")
	if pattern_id:
		# Signalads OTP patterns name their variable "otp"
		return send_pattern_sms(mobile, pattern_id, {"otp": str(code)})
	return send_sms(mobile, f"کد تایید شما: {code}")
