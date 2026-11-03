# In bench IPython console:  %run press/scripts/retitle_toman_plans.py
# Replaces dollar display titles ("$5") of the "USD ..." Site Plans with their Toman price.
# Only plan_title changes, never the plan's name, so subscriptions that point to it keep working.
# retitle() only prints what it would change. Take a backup, read the report, then retitle(dry_run=False).
import frappe


def toman_title(price_irt):
	return f"{price_irt:,.0f} Toman"


def retitle(dry_run=True):
	plans = frappe.get_all(
		"Site Plan",
		filters={"name": ("like", "USD %"), "price_irt": (">", 0)},
		fields=["name", "plan_title", "price_irt"],
		order_by="name",
	)
	changes = [(p.name, p.plan_title, toman_title(p.price_irt)) for p in plans if p.plan_title != toman_title(p.price_irt)]
	for name, old, new in changes:
		print(f"{name}: {old!r} -> {new!r}")
		if not dry_run:
			frappe.db.set_value("Site Plan", name, "plan_title", new, update_modified=False)
	if not dry_run:
		frappe.db.commit()
	print(f"{len(changes)} of {len(plans)} plans {'would change' if dry_run else 'changed'}")
	return changes
