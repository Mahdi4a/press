# Copyright (c) 2019, Frappe and contributors
# For license information, please see license.txt


import frappe

from press.utils.currency import ensure_toman_currency


def after_install():
	ensure_toman_currency()
	create_administrator_team()
	create_default_cluster()


def create_administrator_team():
	administrator_team = frappe.get_doc(
		{
			"doctype": "Team",
			"name": "Administrator",
			"user": "Administrator",
			"enabled": 1,
			"free_account": 1,
			"team_members": [{"user": "Administrator"}],
		}
	)
	administrator_team.insert()


def create_default_cluster():
	default_cluster = frappe.get_doc({"doctype": "Cluster", "name": "Default"})
	default_cluster.insert()
