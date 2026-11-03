# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from press.api import account
from press.press.doctype.team.test_team import create_test_team
from press.utils import otp as otp_purpose
from press.utils import sms
from press.utils.otp import OneTimePassword

MOBILE = "09120000042"


class TestPhoneLogin(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self.clear_counters)
		self.clear_counters()

	def clear_counters(self):
		frappe.cache.delete(
			frappe.cache.make_key(f"press_sms_hour:{MOBILE}"), frappe.cache.make_key(f"press_sms_day:{MOBILE}")
		)

	@patch.object(sms, "send_otp_sms")
	def test_codes_to_one_number_stop_at_the_hourly_limit(self, send):
		for _ in range(sms.HOURLY_LIMIT_PER_MOBILE):
			sms.send_otp_to_mobile(MOBILE, "123456")

		with self.assertRaises(frappe.ValidationError):
			sms.send_otp_to_mobile(MOBILE, "123456")
		self.assertEqual(send.call_count, sms.HOURLY_LIMIT_PER_MOBILE)

	@patch.object(sms, "send_otp_sms", side_effect=sms.requests.ConnectionError)
	def test_a_gateway_that_is_down_is_not_a_silent_success(self, send):
		with self.assertRaises(frappe.ValidationError):
			sms.send_otp_to_mobile(MOBILE, "123456")

	@patch.object(sms, "send_otp_sms")
	def test_no_code_is_sent_while_phone_login_is_off(self, send):
		with patch.object(sms, "phone_login_enabled", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				sms.send_otp_to_mobile(MOBILE, "123456")
		send.assert_not_called()

	def test_an_expired_code_is_rejected(self):
		code = OneTimePassword(otp_purpose.LOGIN, "someone@example.com")
		issued = code.generate()
		frappe.cache.delete(code.key)  # what the end of its time to live does

		self.assertFalse(code.consume(issued))

	def test_a_code_is_withdrawn_after_too_many_wrong_guesses(self):
		code = OneTimePassword(otp_purpose.LOGIN, "someone@example.com")
		issued = code.generate()
		for _ in range(otp_purpose.MAX_WRONG_GUESSES):
			code.consume("000000")

		self.assertFalse(code.consume(issued))

	def test_a_mobile_that_already_registered_cannot_sign_up_again(self):
		team = create_test_team()
		frappe.db.set_value("User", team.user, "mobile_no", MOBILE)

		with self.assertRaises(frappe.ValidationError):
			account.signup(sms.email_from_mobile(MOBILE))

	def test_a_mobile_that_belongs_to_an_email_team_cannot_sign_up(self):
		team = create_test_team()
		frappe.db.set_value("Team", team.name, "phone_number", "+98 912 000 0042")

		self.assertEqual(sms.team_for_mobile(MOBILE), team.name)
		with self.assertRaises(frappe.ValidationError):
			account.signup(sms.email_from_mobile(MOBILE))

	def test_a_toman_team_never_gets_a_stripe_customer(self):
		team = create_test_team()
		team.currency = "IRT"

		with (
			patch("press.press.doctype.team.team.is_stripe_configured", return_value=True),
			patch("press.press.doctype.team.team.get_stripe") as get_stripe,
		):
			team.create_stripe_customer()

		get_stripe.assert_not_called()
