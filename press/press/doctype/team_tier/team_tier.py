# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class TeamTier(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Float
		amount_irt: DF.Currency
		last_invoice_amount: DF.Float
		last_invoice_amount_irt: DF.Currency
		paying_user_since: DF.Int
		tier: DF.Data | None
	# end: auto-generated types

	pass
