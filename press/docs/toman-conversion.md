# Toman prices and conversion

A plan's `Price (IRT)` is the price. A Toman team is charged that amount and nothing converts it.

## The only conversions

| What | Where | Rate |
|---|---|---|
| USD amount to Toman (an Iranian team still billed in USD, seeding old plan prices) | `usd_to_toman` in `utils/gateway_settings.py` | Press Settings, `Toman per 1 USD` |
| Toman to Rial (what Zarinpal is asked for and verifies) | `toman_to_rial` in `utils/gateway_settings.py` | fixed, 1 Toman = 10 Rial |

Used by `create_payment` and `_verify_and_credit` in `api/regional_payments/zarinpal/utils.py`, and by `get_toman_per_usd` in `press/doctype/team/team.py` and `patches/v0_8_0/add_toman_currency.py`.

## Price columns

- `Price (IRT)`: billed to teams whose currency is IRT.
- `Price (INR)`: billed only to INR teams. It is not required any more, so a Toman-only plan can be saved.
- `Price (USD)`: billed to USD teams.
- `paid_plans()` counts a plan as paid when any of the three is above zero.

## Display

The `IRT` Currency record has the symbol `Toman`, placed after the amount.

## Plan titles

`scripts/retitle_toman_plans.py` replaces the dollar titles of the `USD ...` plans with their Toman price. It changes `plan_title` only, never a plan's name, and prints a dry-run report unless called with `dry_run=False`.
