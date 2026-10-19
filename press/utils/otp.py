from __future__ import annotations

import os

import frappe

# What a code was issued for. A code handed out to verify a signup must not work
# to log in, so each purpose gets its own key.
SIGNUP = "signup"
LOGIN = "login"
TWO_FACTOR_RECOVERY = "2fa-recovery"
ADD_CONTACT = "add-contact"

# How long a code stays good for. A signup code is mailed alongside the
# setup-account link, so it lasts as long as that link does — see
# `request_key_expiration_time`. Codes that open an account that already exists
# get minutes, not a day.
EXPIRES_IN = {
	SIGNUP: 24 * 60 * 60,
	LOGIN: 10 * 60,
	TWO_FACTOR_RECOVERY: 10 * 60,
	ADD_CONTACT: 10 * 60,
}

# How long before another code may be sent to the same inbox.
RESEND_AFTER = 30

# How many wrong guesses a code survives. A code is six digits, so without a limit per
# code a caller spread over many addresses could still guess it; the limits per address
# do not see that.
MAX_WRONG_GUESSES = 5

# Spend a code, but only while it is still the code being presented. Reading,
# comparing and deleting as three steps lets a code that has been replaced in
# between still succeed, and take the replacement down with it. A wrong guess is
# counted in the same step, and the fifth one withdraws the code.
SPEND = """
local issued = redis.call('GET', KEYS[1])
if issued == ARGV[1] then
	redis.call('DEL', KEYS[2])
	return redis.call('DEL', KEYS[1])
end
if issued then
	local wrong = redis.call('INCR', KEYS[2])
	redis.call('EXPIRE', KEYS[2], ARGV[3])
	if wrong >= tonumber(ARGV[2]) then
		redis.call('DEL', KEYS[1], KEYS[2])
	end
end
return 0
"""


def generate_otp():
	"""Generates a cryptographically secure random OTP"""

	return int.from_bytes(os.urandom(5), byteorder="big") % 900000 + 100000


class OneTimePassword:
	"""A one-time password held in the cache, hashed, until it expires.

	These used to live on Account Request, which tied logging in to still having
	the record written when you signed up. Accounts whose request was never
	created, or had since been cleaned up, could not log in at all.

	The identifier is whatever the code is about: an email for logging in, an
	Account Request for verifying a signup.

	Keys are namespaced up front and only raw redis commands are used on them.
	Frappe's cache wrappers namespace and pickle on the way past, which would
	both double up the prefix and put a value in front of Lua that it cannot
	compare.
	"""

	def __init__(self, purpose: str, identifier: str):
		self.purpose = purpose
		self.identifier = identifier
		self.expires_in = EXPIRES_IN[purpose]

	@property
	def key(self) -> bytes:
		return frappe.cache.make_key(f"press_otp:{self.purpose}:{self.identifier}")

	@property
	def resend_key(self) -> bytes:
		return frappe.cache.make_key(f"press_otp_sent:{self.purpose}:{self.identifier}")

	@property
	def wrong_guesses_key(self) -> bytes:
		return frappe.cache.make_key(f"press_otp_wrong:{self.purpose}:{self.identifier}")

	def hashed(self, code: str | int) -> str:
		return frappe.utils.sha256_hash(str(code))

	def generate(self) -> str:
		code = str(generate_otp())
		if frappe.conf.developer_mode and frappe.local.dev_server:
			code = "111111"

		frappe.cache.set(self.key, self.hashed(code), ex=self.expires_in)
		frappe.cache.delete(self.wrong_guesses_key)
		self.hold_resend()

		return code

	def hold_resend(self):
		"""Refuse another code to this identifier for the next RESEND_AFTER seconds."""
		frappe.cache.set(self.resend_key, 1, ex=RESEND_AFTER)

	def verify(self, code: str | int) -> bool:
		"""Whether the code is the one currently issued. Claims nothing."""
		issued = frappe.cache.get(self.key)

		return issued is not None and issued.decode() == self.hashed(code)

	def consume(self, code: str | int) -> bool:
		"""Check the code and spend it, in one step, so only one caller may use it.

		Two callers can read the same code before either removes it, and a code
		can be replaced between being read and being removed. Neither is decided
		by reading, so the check and the delete happen together in Redis and the
		delete only lands on the code that was checked.
		"""
		return bool(
			frappe.cache.eval(
				SPEND, 2, self.key, self.wrong_guesses_key, self.hashed(code), MAX_WRONG_GUESSES, self.expires_in
			)
		)

	def clear(self):
		frappe.cache.delete(self.key, self.wrong_guesses_key)

	@property
	def issued_recently(self) -> bool:
		return frappe.cache.get(self.resend_key) is not None
