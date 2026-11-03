# Sends one real code through Signalads' OTP service and checks it, to try the service by hand.
# The token is read from the SIGNALADS_TOKEN environment variable, never from Press Settings.
#
# docker exec -e SIGNALADS_TOKEN=<token> press-test16 bash -lc \
#   'cd /home/frappe/frappe-bench && bench --site test16.localhost execute \
#    press.scripts.try_signalads_otp.send --kwargs "{\"mobile\": \"09XXXXXXXXX\", \"pattern_id\": 2181}"'
# then, with the code that arrives:
# docker exec -e SIGNALADS_TOKEN=<token> press-test16 bash -lc \
#   'cd /home/frappe/frappe-bench && bench --site test16.localhost execute \
#    press.scripts.try_signalads_otp.check --kwargs "{\"mobile\": \"09XXXXXXXXX\", \"code\": \"123456\"}"'
import os
from unittest.mock import patch

import frappe

from press.utils import otp as otp_purpose
from press.utils import sms
from press.utils.otp import OneTimePassword


def _identity(mobile):
	return f"{sms.normalize_mobile(mobile)}@phone.press.local"


def _service(pattern_id=None):
	token = os.environ.get("SIGNALADS_TOKEN")
	if not token:
		raise SystemExit("Set SIGNALADS_TOKEN first")

	real_setting = sms.get_gateway_setting

	def setting(fieldname, *args, **kwargs):
		# An unset pattern in Press Settings reads as 0, which would win over any site config
		if fieldname == "signalads_otp_pattern_id" and pattern_id:
			return pattern_id
		return real_setting(fieldname, *args, **kwargs)

	return (
		patch.object(sms, "otp_service_enabled", return_value=True),
		patch.object(sms, "_config", return_value=(token, "")),
		patch.object(sms, "get_gateway_setting", side_effect=setting),
		# Press logs why and tells the user only that the service is down; here, show why
		patch.object(sms, "_otp_service_failed", side_effect=_show_why),
	)


def _show_why(what):
	raise SystemExit(f"Signalads OTP service failed: {what}")


def send(mobile, pattern_id=None):
	enabled, config, setting, why = _service(pattern_id)
	with enabled, config, setting, why:
		code = OneTimePassword(otp_purpose.LOGIN, _identity(mobile), mobile=mobile)
		print("handed over for Press to send:", repr(code.generate()))
		print("kept in the cache:", frappe.cache.get(code.key), "good for", frappe.cache.ttl(code.key), "s")


def check(mobile, code):
	enabled, config, setting, why = _service()
	with enabled, config, setting, why:
		spent = OneTimePassword(otp_purpose.LOGIN, _identity(mobile), mobile=mobile).consume(code)
		print("Signalads confirmed the code:", spent)
