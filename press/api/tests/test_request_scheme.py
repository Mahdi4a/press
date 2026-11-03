# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from press import overrides


def request_for(host: str, scheme: str = "http") -> Request:
	return Request(EnvironBuilder(path="/.well-known/oauth-authorization-server", base_url=f"{scheme}://{host}").get_environ())


class TestUseConfiguredScheme(FrappeTestCase):
	def run_with(self, request: Request, host_name: str | None) -> str:
		conf = dict(frappe.local.conf)
		if host_name:
			conf["host_name"] = host_name
		with patch.object(frappe.local, "conf", frappe._dict(conf)), patch.object(
			frappe.local, "request", request, create=True
		):
			overrides.use_configured_scheme()
			return request.url

	def test_https_host_name_turns_a_proxied_http_request_into_https(self):
		url = self.run_with(request_for("press.example.com"), "https://press.example.com")

		self.assertTrue(url.startswith("https://press.example.com"))

	def test_other_hosts_are_left_alone(self):
		url = self.run_with(request_for("other.example.com"), "https://press.example.com")

		self.assertTrue(url.startswith("http://other.example.com"))

	def test_without_host_name_nothing_changes(self):
		url = self.run_with(request_for("press.example.com"), None)

		self.assertTrue(url.startswith("http://press.example.com"))
