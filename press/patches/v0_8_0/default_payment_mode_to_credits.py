"""Credits are the only way to pay, so a team with no payment mode starts on them."""

import frappe


def execute():
	team = frappe.qb.DocType("Team")
	(
		frappe.qb.update(team)
		.set(team.payment_mode, "Prepaid Credits")
		.where(team.payment_mode.isnull() | (team.payment_mode == ""))
	).run()
