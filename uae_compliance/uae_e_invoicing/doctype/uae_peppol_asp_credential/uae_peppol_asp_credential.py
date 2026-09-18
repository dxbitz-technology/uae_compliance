"""One credential on a provider connection.

The secret is a Password field, so the framework stores it encrypted and no
read of this row returns it. Its removal is handled by the connection, which
knows which rows a save dropped.
"""

from frappe.model.document import Document


class UAEPeppolASPCredential(Document):
	pass
