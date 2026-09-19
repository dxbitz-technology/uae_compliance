"""Check that an invoice's own numbers hold together.

Nothing here calculates tax. ERPNext already did that and its figures are the
ones that get posted, so recalculating would only invent a second opinion.
This reads what the document says and reports anywhere it does not add up,
naming the exact difference so somebody can look at the source.

There is no rounding table here either. The pinned currency list carries no
minor units, and guessing what a currency rounds to would be a money
assumption with nothing behind it. Instead every check works at the precision
the document itself used. That is why the identities below are exact: the
document carries its own rounding figure, so there is nothing left to absorb.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from uae_compliance.domain.findings import Finding, Severity, Stage

# One code per way the numbers can disagree.
CODE_TOTALS = "MONEY-0001"
CODE_TAX_BASE = "MONEY-0002"
CODE_TAX_AMOUNT = "MONEY-0003"
CODE_GROUP_MISSING = "MONEY-0004"
CODE_GROUP_UNKNOWN = "MONEY-0005"
CODE_LINE_NET = "MONEY-0006"
CODE_RATE_MISSING = "MONEY-0007"
CODE_AED = "MONEY-0008"

ZERO = Decimal("0")


def _finding(code: str, path: str, message: str, repair: str, **params) -> Finding:
	return Finding(
		code=code,
		severity=Severity.ERROR,
		stage=Stage.ARITHMETIC,
		message=message,
		path=path,
		repair=repair,
		params={k: str(v) for k, v in params.items()},
	)


def _get(document: Mapping, *path, default=None):
	value = document
	for key in path:
		if not isinstance(value, Mapping) or key not in value:
			return default
		value = value[key]
	return value


def _sum(rows: Sequence[Mapping], field: str) -> Decimal:
	total = ZERO
	for row in rows:
		value = row.get(field)
		if isinstance(value, Decimal):
			total += value
	return total


def _scale_of(*values: Decimal) -> int:
	"""The finest precision the document itself used for these values."""
	places = [-v.as_tuple().exponent for v in values if isinstance(v, Decimal) and v.is_finite()]
	return max(places) if places else 2


def _group_key(row: Mapping) -> tuple[str, Decimal] | None:
	"""Tax groups by category and rate together.

	Grouping by rate alone would merge a zero rated supply with an exempt one,
	which are different things on the return even though both carry no tax.
	"""
	category = row.get("tax_category") or row.get("category")
	rate = row.get("tax_rate") if "tax_rate" in row else row.get("rate")
	if not isinstance(category, str) or not isinstance(rate, Decimal):
		return None
	return (category, rate)


def check_totals(document: Mapping) -> list[Finding]:
	"""The three identities from the money rules, each exact.

	Rounding is its own field on the document, so a real invoice has nothing
	left over. A difference here is a genuine disagreement, not a tolerance to
	widen until it passes.
	"""
	totals = _get(document, "totals")
	if not isinstance(totals, Mapping):
		return []
	found: list[Finding] = []
	lines = _get(document, "lines", default=[]) or []
	allowances = _get(document, "allowances", default=[]) or []
	charges = _get(document, "charges", default=[]) or []

	line_net = _sum(lines, "net_amount")
	if isinstance(totals.get("line_net"), Decimal) and totals["line_net"] != line_net:
		found.append(
			_finding(
				CODE_TOTALS,
				"totals.line_net",
				"The line total does not match the sum of the lines.",
				"check_source_invoice",
				stated=totals["line_net"],
				from_lines=line_net,
			)
		)

	expected_exclusive = line_net - _sum(allowances, "amount") + _sum(charges, "amount")
	exclusive = totals.get("tax_exclusive")
	if isinstance(exclusive, Decimal) and exclusive != expected_exclusive:
		found.append(
			_finding(
				CODE_TOTALS,
				"totals.tax_exclusive",
				"The amount before tax does not match the lines and adjustments.",
				"check_source_invoice",
				stated=exclusive,
				expected=expected_exclusive,
			)
		)

	tax = totals.get("tax")
	inclusive = totals.get("tax_inclusive")
	if isinstance(exclusive, Decimal) and isinstance(tax, Decimal) and isinstance(inclusive, Decimal):
		if inclusive != exclusive + tax:
			found.append(
				_finding(
					CODE_TOTALS,
					"totals.tax_inclusive",
					"The amount after tax does not match the amount before tax plus the tax.",
					"check_source_invoice",
					stated=inclusive,
					expected=exclusive + tax,
				)
			)

	payable = totals.get("payable")
	if isinstance(inclusive, Decimal) and isinstance(payable, Decimal):
		prepaid = totals.get("prepaid") if isinstance(totals.get("prepaid"), Decimal) else ZERO
		rounding = totals.get("rounding") if isinstance(totals.get("rounding"), Decimal) else ZERO
		expected_payable = inclusive - prepaid + rounding
		if payable != expected_payable:
			found.append(
				_finding(
					CODE_TOTALS,
					"totals.payable",
					"The payable amount does not match the amount after tax, less prepaid, plus rounding.",
					"check_source_invoice",
					stated=payable,
					expected=expected_payable,
				)
			)
	return found


def check_tax_breakdown(document: Mapping) -> list[Finding]:
	"""Every tax group covers what belongs to it, and nothing is left out."""
	breakdown = _get(document, "tax_breakdown", default=[]) or []
	lines = _get(document, "lines", default=[]) or []
	allowances = _get(document, "allowances", default=[]) or []
	charges = _get(document, "charges", default=[]) or []
	found: list[Finding] = []

	taxable_by_group: dict[tuple[str, Decimal], Decimal] = {}
	for row in lines:
		key = _group_key(row)
		if key and isinstance(row.get("net_amount"), Decimal):
			taxable_by_group[key] = taxable_by_group.get(key, ZERO) + row["net_amount"]
	for row in allowances:
		key = _group_key(row)
		if key and isinstance(row.get("amount"), Decimal):
			taxable_by_group[key] = taxable_by_group.get(key, ZERO) - row["amount"]
	for row in charges:
		key = _group_key(row)
		if key and isinstance(row.get("amount"), Decimal):
			taxable_by_group[key] = taxable_by_group.get(key, ZERO) + row["amount"]

	stated: dict[tuple[str, Decimal], Mapping] = {}
	for index, row in enumerate(breakdown):
		key = _group_key(row)
		if key is None:
			continue
		stated[key] = row
		if key not in taxable_by_group:
			found.append(
				_finding(
					CODE_GROUP_UNKNOWN,
					f"tax_breakdown[{index}]",
					"This tax group does not match anything on the invoice.",
					"check_source_invoice",
					category=key[0],
					rate=key[1],
				)
			)
			continue
		expected = taxable_by_group[key]
		if isinstance(row.get("taxable_amount"), Decimal) and row["taxable_amount"] != expected:
			found.append(
				_finding(
					CODE_TAX_BASE,
					f"tax_breakdown[{index}].taxable_amount",
					"The taxable amount for this group does not match the rows in it.",
					"check_source_invoice",
					category=key[0],
					rate=key[1],
					stated=row["taxable_amount"],
					expected=expected,
				)
			)
		_check_rate_applied(row, index, found)

	for key in sorted(taxable_by_group, key=lambda k: (k[0], k[1])):
		if key not in stated:
			found.append(
				_finding(
					CODE_GROUP_MISSING,
					"tax_breakdown",
					"A tax group used on the invoice has no line in the breakdown.",
					"check_source_invoice",
					category=key[0],
					rate=key[1],
				)
			)
	return found


def _check_rate_applied(row: Mapping, index: int, found: list[Finding]) -> None:
	"""The stated tax matches the stated base at the stated rate.

	Worked at the precision the document already used, so this reports a real
	disagreement rather than a difference this module invented.
	"""
	base = row.get("taxable_amount")
	tax = row.get("tax_amount")
	rate = row.get("rate")
	if not all(isinstance(v, Decimal) for v in (base, tax, rate)):
		return
	scale = _scale_of(tax, base)
	expected = (base * rate / Decimal(100)).quantize(Decimal(1).scaleb(-scale))
	if tax != expected:
		found.append(
			_finding(
				CODE_TAX_AMOUNT,
				f"tax_breakdown[{index}].tax_amount",
				"The tax for this group does not match its base at its rate.",
				"check_source_invoice",
				stated=tax,
				expected=expected,
				rate=rate,
			)
		)


def check_lines(document: Mapping) -> list[Finding]:
	"""Each line's net amount matches its own quantity, price and adjustments.

	A price discount is already inside the net price, so it is never taken off
	again here. Taking it twice is the classic way an invoice ends up short.

	Exact, because ibr-147-ae is exact. Where ERPNext worked the unit price
	back out of the line amount and rounded it, the two really do not multiply
	out and the document really would be refused, so this says so here with
	the figures on it rather than leaving it to a rule id later on.
	"""
	found: list[Finding] = []
	for index, line in enumerate(_get(document, "lines", default=[]) or []):
		quantity = line.get("quantity")
		price = line.get("net_price")
		net = line.get("net_amount")
		if not all(isinstance(v, Decimal) for v in (quantity, price, net)):
			continue
		base_quantity = line.get("base_quantity")
		divisor = base_quantity if isinstance(base_quantity, Decimal) and base_quantity > 0 else Decimal(1)
		expected = quantity * price / divisor
		expected -= _sum(line.get("allowances") or [], "amount")
		expected += _sum(line.get("charges") or [], "amount")
		expected = expected.quantize(Decimal(1).scaleb(-_scale_of(net)))
		if net != expected:
			found.append(
				_finding(
					CODE_LINE_NET,
					f"lines[{index}].net_amount",
					"The line amount does not match its quantity, price and adjustments.",
					"check_source_invoice",
					stated=net,
					expected=expected,
				)
			)
	return found


def check_currency(document: Mapping) -> list[Finding]:
	"""Dirham figures follow a rate that says where it came from."""
	found: list[Finding] = []
	rate_row = _get(document, "exchange_rates", "to_aed")
	rate = rate_row.get("rate") if isinstance(rate_row, Mapping) else None

	needs_aed = [
		(index, row)
		for index, row in enumerate(_get(document, "tax_breakdown", default=[]) or [])
		if isinstance(row.get("tax_amount_aed"), Decimal)
	]
	if needs_aed and not isinstance(rate, Decimal):
		found.append(
			_finding(
				CODE_RATE_MISSING,
				"exchange_rates.to_aed",
				"Dirham amounts are given with no rate to support them.",
				"supply_exchange_rate",
			)
		)
		return found

	for index, row in needs_aed:
		tax = row.get("tax_amount")
		if not isinstance(tax, Decimal):
			continue
		stated = row["tax_amount_aed"]
		expected = (tax * rate).quantize(Decimal(1).scaleb(-_scale_of(stated)))
		if stated != expected:
			found.append(
				_finding(
					CODE_AED,
					f"tax_breakdown[{index}].tax_amount_aed",
					"The dirham tax does not match the invoice tax at the recorded rate.",
					"check_exchange_rate",
					stated=stated,
					expected=expected,
					rate=rate,
				)
			)
	return found


def check(document: Mapping) -> list[Finding]:
	"""Every money check, in one pass, reporting everything it finds."""
	return [
		*check_lines(document),
		*check_totals(document),
		*check_tax_breakdown(document),
		*check_currency(document),
	]
