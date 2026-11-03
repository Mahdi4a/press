"""Phone login worked before it had a switch, so the switch starts on.

A Check added to an existing Press Settings reads as unticked until it is saved once.
"""

import frappe


def execute():
	frappe.db.set_single_value("Press Settings", "phone_login_enabled", 1)
