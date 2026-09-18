"""Getting ERPNext's numbers across the boundary without losing them.

ERPNext stores amounts as floats and rounds them to the currency's precision
as it posts. The canonical model refuses floats outright, because the moment
a tax total is held as binary floating point it can stop adding up.

So every number crosses here, once, by way of its text. The scale is the one
ERPNext itself used for that document, which means a currency with three
decimal places keeps all three and nothing is silently rounded to two on the
way out.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


class Scales:
	"""The precision this document's own fields were posted at."""

	def __init__(self, amount: int, price: int, quantity: int, rate: int):
		self.amount = amount
		self.price = price
		self.quantity = quantity
		self.rate = rate

	@classmethod
	def of(cls, invoice) -> Scales:
		"""Read the precision from the document rather than assuming two.

		Several currencies in this region carry three decimal places, and a
		site can widen its float precision, so the answer belongs to the
		document and not to a table in this app.
		"""
		row = (invoice.get("items") or [None])[0]
		return cls(
			amount=invoice.precision("grand_total") or 2,
			price=(row.precision("rate") if row else None) or 2,
			quantity=(row.precision("qty") if row else None) or 3,
			rate=invoice.precision("conversion_rate") or 9,
		)


def dec(value, scale: int) -> Decimal | None:
	"""One float, one Decimal, at a stated scale.

	Through the text form, because Decimal built straight from a float keeps
	the whole binary approximation and 0.1 arrives as 0.1000000000000000055.
	"""
	if value is None or value == "":
		return None
	quantum = Decimal(1).scaleb(-scale)
	return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def zero(scale: int) -> Decimal:
	return Decimal(0).quantize(Decimal(1).scaleb(-scale))


def flip(value: Decimal | None) -> Decimal | None:
	"""Turn a sign around, keeping the scale.

	A credit note arrives from ERPNext with negative quantities and amounts.
	The rules want it stated positively with its own document type, so signs
	turn once, here, on the fields that carry them. Not by taking the
	absolute value of everything, which quietly hides a genuine negative
	line.
	"""
	if value is None:
		return None
	return -value


def as_date(value) -> str | None:
	"""A date as the rules write it, four digits then month then day.

	ERPNext hands back a date object, or a string, depending on where the
	value came from. Both arrive here and leave the same way.
	"""
	if not value:
		return None
	return str(value)[:10]


def as_timestamp(moment) -> str:
	"""A moment in UTC, ending in Z, which is the only form the model takes."""
	return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
