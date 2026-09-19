// Adds the tax questions to the customer and supplier quick entry form.
//
// It extends whatever class is installed rather than the one ERPNext ships,
// so another app that has already extended the same form keeps working. The
// order matters: this file loads after ERPNext's, takes what is there, and
// puts itself on top.
//
// Nothing here is required. Most of what the rules want is not known when
// somebody is typing a new customer in, and refusing to create the customer
// until it is would make this something to work around.

frappe.provide("frappe.ui.form");

(function () {
	const installed = frappe.ui.form.ContactAddressQuickEntryForm;
	if (!installed || installed.uae_compliance_extended) return;

	const extended = class extends installed {
		get_variant_fields() {
			const fields = super.get_variant_fields();
			return uae_compliance.party_entry.arrange(fields).concat(
				uae_compliance.party_entry.tax_fields()
			);
		}

		insert() {
			// One request, so the party, its address and contact, and the
			// profile all arrive together or none of them do.
			return uae_compliance.party_entry.insert(this);
		}
	};
	extended.uae_compliance_extended = true;

	frappe.ui.form.ContactAddressQuickEntryForm = extended;
	frappe.ui.form.CustomerQuickEntryForm = extended;
	frappe.ui.form.SupplierQuickEntryForm = extended;
})();

window.uae_compliance = window.uae_compliance || {};

uae_compliance.party_entry = {
	// The country decides which questions make sense, so it is asked before
	// them rather than at the bottom of the address block.
	arrange(fields) {
		const country = fields.find((field) => field.fieldname === "country_address");
		if (!country) return fields;
		const rest = fields.filter((field) => field !== country);
		return [
			{ fieldtype: "Section Break", label: __("Where this party is"), collapsible: 0 },
			Object.assign({}, country, { label: __("Country") }),
			...rest,
		];
	},

	tax_fields() {
		return [
			{ fieldtype: "Section Break", label: __("Tax and e-invoicing"), collapsible: 1 },
			{
				label: __("Registered for VAT"),
				fieldname: "vat_state",
				fieldtype: "Select",
				options: ["Not sure", "Registered", "Not registered"],
				default: "Not sure",
				description: __("Not sure is a real answer. Leave it until somebody knows."),
			},
			{
				label: __("VAT Number"),
				fieldname: "vat_number",
				fieldtype: "Data",
				depends_on: "eval:doc.vat_state=='Registered'",
			},
			{
				label: __("Additional UAE VAT Number"),
				fieldname: "extra_vat_number",
				fieldtype: "Data",
				depends_on: "eval:doc.country_address && doc.country_address!='United Arab Emirates'",
				description: __("A party outside the UAE can hold a UAE registration as well as its own."),
			},
			{ fieldtype: "Column Break" },
			{
				label: __("On the e-invoicing network"),
				fieldname: "peppol_state",
				fieldtype: "Select",
				options: ["Not sure", "Registered", "Not registered"],
				default: "Not sure",
				description: __("What they told us. It is not checked until a lookup checks it."),
			},
			{
				label: __("Network Scheme"),
				fieldname: "endpoint_scheme",
				fieldtype: "Data",
				depends_on: "eval:doc.peppol_state=='Registered'",
				description: __("0235 for a UAE tax number. A party abroad may use another."),
			},
			{
				label: __("Network Address"),
				fieldname: "endpoint_value",
				fieldtype: "Data",
				depends_on: "eval:doc.peppol_state=='Registered'",
			},
		];
	},

	insert(form) {
		const values = Object.assign({}, form.dialog.doc);
		delete values.__islocal;
		delete values.__unsaved;
		delete values.doctype;

		// The same renaming the native form does, because the doctype holds
		// these under different names than the dialog collects them under.
		const rename = {
			email_address: "email_id",
			mobile_number: "mobile_no",
			map_to_first_name: "first_name",
			map_to_last_name: "last_name",
			country_address: "country",
		};
		Object.entries(rename).forEach(([from, to]) => {
			if (values[from] !== undefined) {
				values[to] = values[from];
				delete values[from];
			}
		});

		return frappe
			.call({
				method: "uae_compliance.services.party_entry.create_party",
				args: { doctype: form.doctype, values: JSON.stringify(values) },
			})
			.then((reply) => {
				if (!reply.message) return;
				form.dialog.hide();
				if (form.after_insert) {
					form.after_insert({ doctype: form.doctype, name: reply.message.name });
				} else {
					frappe.set_route("Form", form.doctype, reply.message.name);
				}
			});
	},
};
