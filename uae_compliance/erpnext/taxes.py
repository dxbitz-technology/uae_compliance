"""The tax breakdown, the charges that are not tax, and the totals.

Two facts from the pinned controller shape this file.

A document discount is already inside the line amounts. ERPNext spreads it
across the rows and rewrites each row's net amount and net rate, so putting
it back as a document allowance would take it off twice. The one case it
does not spread is a cash or non trade discount on the grand total, which
comes off after tax and has no place in the model, so it is reported rather
than approximated.

`total_taxes_and_charges` is not VAT. Anything posted there without a tax
mapping is a charge, and it is carried as one.
"""

from __future__ import annotations

from decimal import Decimal

from uae_compliance.domain.findings import Finding, Severity, SourceRef, Stage
from uae_compliance.erpnext import mapping
from uae_compliance.erpnext.numbers import Scales, dec, flip, zero

CODE_DISCOUNT_AFTER_TAX = "MAP-0005"
CODE_CHARGE_TREATMENT = "MAP-0008"


def split_tax_rows(invoice, resolution, source) -> tuple[dict, list]:
	"""Which posted tax rows are VAT, and which are something else.

	A row is VAT when a mapping says which category it belongs to. Anything
	else is a charge on the document. Neither is assumed from the account's
	name.
	"""
	vat = {}
	charges = []
	for row in invoice.get("taxes") or []:
		# Quietly, because an unmapped row here is a charge rather than a
		# mistake, and saying so every time would bury the real findings.
		found = mapping.tax_category(invoice.company, row.account_head, None, resolution, source, quiet=True)
		if found:
			vat[row.name] = found
		else:
			charges.append(row)
	return vat, charges


def breakdown(
	invoice,
	lines,
	vat_rows,
	attribution,
	scales: Scales,
	credit_note: bool,
	company_currency: str | None = None,
) -> list[dict]:
	"""The tax total, grouped by every dimension the rules ask for.

	Grouped by category and rate together, because two lines at the same rate
	under different categories are two rows on the document and adding them
	together would lose the reason one of them is exempt.
	"""
	by_key: dict[tuple, dict] = {}
	for line in lines:
		if not line.get("tax_category"):
			continue
		key = (line["tax_category"], line["tax_rate"])
		group = by_key.setdefault(
			key,
			{
				"category": line["tax_category"],
				"rate": line["tax_rate"],
				"reason": line.get("tax_reason"),
				"reason_code": line.get("tax_reason_code"),
				"taxable_amount": zero(scales.amount),
				"tax_amount": zero(scales.amount),
				"_lines": [],
			},
		)
		group["taxable_amount"] += _taxable(line, vat_rows, attribution, scales, invoice, credit_note)
		group["_lines"].append(line["source_row"])

	_attribute_tax(by_key, invoice, vat_rows, attribution, scales, credit_note, company_currency)
	for group in by_key.values():
		group.pop("_lines", None)
	return [by_key[key] for key in sorted(by_key, key=lambda k: (k[0], k[1]))]


def _taxable(line, vat_rows, attribution, scales: Scales, invoice, credit_note: bool):
	"""What the tax on this line was actually worked out on.

	Usually the line's own net amount, and not always. A charge taken before
	a tax row is inside that row's base, so a hundred of goods with twenty of
	freight in front of a five percent row is taxed on a hundred and twenty.
	Summing the line net amounts alone would state a base of a hundred
	against a tax of six.

	The per row table records the base each tax row applied to each line, so
	that is read rather than worked out. Where nothing was posted against a
	line, its own net amount is the answer.
	"""
	rate = Decimal(str(invoice.conversion_rate or 1))
	for hit in attribution.get(line["source_row"]) or []:
		if hit["tax_row"] not in vat_rows:
			continue
		base = dec(hit["taxable_amount"], scales.amount)
		if not base:
			# Nothing recorded against this line for that row. A base of
			# zero under a line that has an amount means the table did not
			# carry one, and the line's own amount is the better answer.
			continue
		if rate != 1:
			base = dec(base / rate, scales.amount)
		# The posted base already carries the line's own sign, including a
		# negative line on an ordinary invoice. Only a credit note turns,
		# and it turns the same way its line amounts do.
		return flip(base) if credit_note else base
	return line["net_amount"]


def _attribute_tax(by_key, invoice, vat_rows, attribution, scales, credit_note, company_currency=None):
	"""Put each posted tax amount against the group its lines belong to.

	The per row table holds company currency amounts. Where the invoice is in
	another currency the group amounts are converted and the leftover from
	rounding goes on the largest group, so the parts still add up to the
	posted total instead of drifting from it.
	"""
	rate = Decimal(str(invoice.conversion_rate or 1))
	line_group = {}
	for key, group in by_key.items():
		for row_name in group["_lines"]:
			line_group[row_name] = key

	for item_row, hits in attribution.items():
		key = line_group.get(item_row)
		if key is None:
			continue
		for hit in hits:
			if hit["tax_row"] not in vat_rows:
				continue
			amount = dec(hit["amount"], scales.amount)
			if amount is None:
				continue
			if rate != 1:
				amount = dec(amount / rate, scales.amount)
			by_key[key]["tax_amount"] += amount

	# The per row table holds company currency amounts, which already are
	# dirhams when the company keeps its books in them. Summed rather than
	# converted, because a posted figure beats one we work out.
	#
	# Only for an invoice in another currency. Repeating the same figure in
	# the same currency says nothing, and the money rules would then want a
	# rate for a conversion that never happened.
	if invoice.currency != "AED" and company_currency == "AED":
		for group in by_key.values():
			total = zero(scales.amount)
			for item_row in group["_lines"]:
				for hit in attribution.get(item_row) or []:
					if hit["tax_row"] in vat_rows:
						total += dec(hit["amount"], scales.amount) or zero(scales.amount)
			group["tax_amount_aed"] = flip(total) if credit_note else total

	posted = zero(scales.amount)
	for row in invoice.get("taxes") or []:
		if row.name in vat_rows:
			posted += dec(row.tax_amount_after_discount_amount, scales.amount) or zero(scales.amount)

	_settle(by_key, posted, scales)
	if credit_note:
		# Only the tax turns here. The taxable amount was built from the line
		# net amounts, which turned already, and turning it twice put the
		# group back where it started.
		for group in by_key.values():
			group["tax_amount"] = flip(group["tax_amount"])


def _settle(by_key, posted, scales):
	"""Make the parts add up to what ERPNext posted.

	Any difference is rounding from the conversion, so it goes on the largest
	group. Largest by taxable amount, then by category and rate, so the same
	invoice always settles the same way.
	"""
	if not by_key:
		return
	total = sum((group["tax_amount"] for group in by_key.values()), zero(scales.amount))
	difference = posted - total
	if not difference:
		return
	by_key[_settlement_group(by_key)]["tax_amount"] += difference


def _settlement_group(by_key):
	"""Which group takes the leftover.

	Never a group taxed at nothing. A zero rated or exempt supply carrying a
	few fils of VAT is a false statement about that supply, and it is the one
	a big zero rated line invites, because it is usually the largest group on
	the invoice. So the leftover goes to the largest group that is taxed at
	all, and only falls back to the largest of any kind when no group is.
	"""
	taxed = [key for key in by_key if key[1]] or list(by_key)
	return max(taxed, key=lambda k: (abs(by_key[k]["taxable_amount"]), k[0], str(k[1])))


def charge_rows(
	charges, invoice, scales: Scales, credit_note: bool, breakdown=None, source=None, out_findings=None
) -> list[dict]:
	"""Posted charges that are not VAT, as document charges.

	A charge still has a tax treatment, because the rules need one for every
	amount on the document. Where a charge sits inside a tax row's base, as
	freight taken before a VAT row does, its treatment is that row's. That
	is read from the document rather than assumed: the tax was worked out on
	the charge, so the charge is taxed the same way.

	Where the document has more than one taxed group there is no way to say
	which one a charge belongs to, and it is reported rather than picked.
	"""
	groups = [group for group in (breakdown or []) if group.get("category")]
	treatment = groups[0] if len(groups) == 1 else None

	out = []
	for row in charges:
		amount = dec(row.tax_amount_after_discount_amount, scales.amount)
		if not amount:
			continue
		charge = {
			"amount": flip(amount) if credit_note else amount,
			"reason": row.description or row.account_head,
		}
		if treatment:
			charge["tax_category"] = treatment["category"]
			charge["tax_rate"] = treatment["rate"]
		elif out_findings is not None and source is not None:
			out_findings.note(
				Finding(
					code=CODE_CHARGE_TREATMENT,
					severity=Severity.ERROR,
					stage=Stage.MAPPING,
					message="This charge is on the invoice with no tax treatment of its own.",
					path="charges.tax_category",
					source=source,
					repair="Map the account this charge posts to, so its tax treatment is stated.",
					params={"charge": row.description or row.account_head or ""},
				)
			)
		out.append(charge)
	return out


def in_dirhams(invoice, scales: Scales, credit_note: bool, company_currency: str | None) -> dict:
	"""The dirham figures, taken from what ERPNext posted.

	Only for an invoice in another currency, because one already in dirhams
	states them once and repeating them says nothing.

	And only where the company keeps its books in dirhams, because then the
	base amounts already are the dirham amounts and nothing has to be worked
	out. Where the company currency is something else there is no evidenced
	rate to dirhams, and inventing one is worse than saying so.
	"""
	if invoice.currency == "AED" or company_currency != "AED":
		return {}

	tax = dec(invoice.base_total_taxes_and_charges, scales.amount)
	inclusive = dec(invoice.base_grand_total, scales.amount)
	if credit_note:
		tax = flip(tax)
		inclusive = flip(inclusive)
	return {"tax_in_aed": tax, "tax_inclusive_aed": inclusive}


def totals(
	invoice,
	charges,
	tax_total,
	scales: Scales,
	credit_note: bool,
	company_currency: str | None = None,
) -> dict:
	"""The document totals, as ERPNext posted them.

	Nothing here is worked out from the lines. The money rules check that
	these agree with the lines and report it when they do not, which is a
	different job from producing them.
	"""
	charge_total = sum((row["amount"] for row in charges), zero(scales.amount))
	line_net = dec(invoice.net_total, scales.amount) or zero(scales.amount)
	grand = dec(invoice.grand_total, scales.amount) or zero(scales.amount)
	rounded = dec(invoice.rounded_total, scales.amount) if not invoice.disable_rounded_total else None
	rounding = dec(invoice.rounding_adjustment, scales.amount) or zero(scales.amount)
	prepaid = dec(invoice.total_advance, scales.amount) or zero(scales.amount)

	if credit_note:
		# Every figure ERPNext posted negative turns, and that includes the
		# rounding and the advance. Leaving the rounding behind states it the
		# wrong way round and puts the amount due out by twice its value.
		line_net = flip(line_net)
		grand = flip(grand)
		rounded = flip(rounded)
		rounding = flip(rounding)
		prepaid = flip(prepaid)

	return {
		"line_net": line_net,
		"allowances": zero(scales.amount),
		"charges": charge_total,
		"tax_exclusive": line_net + charge_total,
		"tax": tax_total,
		"tax_inclusive": grand,
		"prepaid": prepaid,
		"rounding": rounding,
		# ERPNext keeps the grand total whole and records the advance next to
		# it. What is still due does not include money already collected, so
		# the advance comes off here.
		"payable": (grand if rounded is None else rounded) - prepaid,
		**in_dirhams(invoice, scales, credit_note, company_currency),
	}


def discount_check(invoice, source: SourceRef) -> Finding | None:
	"""The one discount shape this model cannot carry.

	A cash or non trade discount on the grand total comes off after tax.
	ERPNext leaves the lines alone, so there is no line amount and no tax
	group it belongs to. Stating it anywhere in the model would change what
	was posted, so it is reported instead.
	"""
	if not invoice.discount_amount:
		return None
	if invoice.apply_discount_on == "Grand Total" and invoice.get("is_cash_or_non_trade_discount"):
		return Finding(
			code=CODE_DISCOUNT_AFTER_TAX,
			severity=Severity.ERROR,
			stage=Stage.MAPPING,
			message="A cash discount taken off the grand total cannot be shown on an e-invoice.",
			path="totals.allowances",
			source=source,
			repair="Apply the discount on the net total, or record it as a separate credit note.",
		)
	return None
