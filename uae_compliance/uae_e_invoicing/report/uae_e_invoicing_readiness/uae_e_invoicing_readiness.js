frappe.query_reports["UAE e-Invoicing Readiness"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "readiness",
			label: __("Readiness"),
			fieldtype: "Select",
			options: [
				"",
				"Not checked",
				"Stale",
				"Further checks required",
				"Needs details",
				"Ready locally",
				"Unavailable",
				"Out of scope",
			],
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
		},
	],

	// Red for anything that would stop a send, amber for anything stale.
	// Nothing else is coloured, because colouring everything says nothing.
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "readiness" && data) {
			if (data.readiness === "Needs details") {
				value = `<span class="indicator red">${value}</span>`;
			} else if (data.readiness === "Stale" || data.readiness === "Unavailable") {
				value = `<span class="indicator orange">${value}</span>`;
			} else if (data.readiness === "Ready locally") {
				value = `<span class="indicator green">${value}</span>`;
			}
		}
		return value;
	},
};
