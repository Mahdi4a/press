# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from press.utils import otp as otp_purpose
from press.utils import sms
from press.utils.otp import OneTimePassword

MOBILE = "09120000043"
EMAIL = f"{MOBILE}@phone.press.local"


def answer(status: int = 200, body: dict | None = None) -> Mock:
	response = Mock(status_code=status, ok=status < 400, text=str(body))
	response.json.return_value = body or {}
	return response


def sent(uuid: str = "c1654ef5-0bf8-4e30-854f-4c9dc18d7a34", minutes: int = 5) -> Mock:
	expire_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
	return answer(200, {"type": "sms", "uuid": uuid, "expire_at": expire_at, "data": {}})


class TestSignaladsOtpService(FrappeTestCase):
	def setUp(self):
		super().setUp()
		for patcher in (
			patch.object(sms, "otp_service_enabled", return_value=True),
			patch.object(sms, "_config", return_value=("token", "")),
			patch.object(sms, "count_codes_sent"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.code = OneTimePassword(otp_purpose.LOGIN, EMAIL, mobile=MOBILE)
		self.addCleanup(self.code.clear)

	@patch.object(sms.requests, "post")
	def test_signalads_makes_the_code_and_press_keeps_only_its_session(self, post):
		post.return_value = sent()

		handed_over = self.code.generate()

		self.assertEqual(handed_over, "")
		self.assertEqual(frappe.cache.get(self.code.key), b"svc:c1654ef5-0bf8-4e30-854f-4c9dc18d7a34")
		self.assertTrue(post.call_args.args[0].endswith("/api_v1/otp/send"))
		self.assertEqual(post.call_args.kwargs["json"]["mobile"], MOBILE)

	@patch.object(sms.requests, "post")
	def test_the_session_does_not_outlive_the_code(self, post):
		post.return_value = sent(minutes=5)

		self.code.generate()

		self.assertLessEqual(frappe.cache.ttl(self.code.key), 5 * 60)

	@patch.object(sms.requests, "post")
	def test_a_code_signalads_confirms_is_spent(self, post):
		post.side_effect = [sent(), answer(200, {"uuid": "x", "verified": True})]
		self.code.generate()

		self.assertTrue(self.code.consume("123456"))
		self.assertTrue(post.call_args.args[0].endswith("/api_v1/otp/verify"))
		self.assertEqual(post.call_args.kwargs["json"]["code"], "123456")
		self.assertIsNone(frappe.cache.get(self.code.key))

	@patch.object(sms.requests, "post")
	def test_a_wrong_code_is_refused_and_withdrawn_after_five(self, post):
		post.side_effect = [sent()] + [answer(200, {"uuid": "x", "verified": False})] * 5
		self.code.generate()

		for _ in range(otp_purpose.MAX_WRONG_GUESSES):
			self.assertFalse(self.code.consume("000000"))

		self.assertIsNone(frappe.cache.get(self.code.key))

	@patch.object(sms.requests, "post")
	def test_an_expired_session_is_simply_not_verified(self, post):
		post.side_effect = [sent(), answer(404)]
		self.code.generate()

		self.assertFalse(self.code.consume("123456"))

	@patch.object(sms.requests, "post")
	def test_emails_never_go_to_signalads(self, post):
		code = OneTimePassword(otp_purpose.LOGIN, "someone@example.com")
		self.addCleanup(code.clear)

		issued = code.generate()

		self.assertEqual(len(issued), 6)
		post.assert_not_called()
		self.assertTrue(code.consume(issued))

	@patch.object(sms.requests, "post", side_effect=sms.requests.ConnectionError)
	def test_a_service_that_is_down_is_not_a_silent_success(self, post):
		with self.assertRaises(frappe.ValidationError):
			self.code.generate()

		self.assertIsNone(frappe.cache.get(self.code.key))

	@patch.object(sms.requests, "post", return_value=answer(400, {"detail": "bad"}))
	def test_an_answer_without_a_session_is_an_error(self, post):
		with self.assertRaises(frappe.ValidationError):
			self.code.generate()

	def test_a_switched_off_service_leaves_our_own_codes_alone(self):
		with patch.object(sms, "otp_service_enabled", return_value=False):
			issued = OneTimePassword(otp_purpose.LOGIN, EMAIL, mobile=MOBILE).generate()

		self.assertEqual(len(issued), 6)

	def test_time_left_is_read_from_the_offset_time_signalads_sends(self):
		soon = (datetime.now(timezone.utc) + timedelta(seconds=90)).astimezone(timezone(timedelta(hours=3, minutes=30)))

		self.assertAlmostEqual(sms._seconds_until(soon.isoformat()), 90, delta=3)
		self.assertEqual(sms._seconds_until(None), 300)
