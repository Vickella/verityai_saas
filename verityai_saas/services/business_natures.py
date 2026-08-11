import frappe


def lead(fieldname, label, fieldtype="Data", *, options=None, required=False, description=None):
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": fieldtype,
		"options": options,
		"required": int(required),
		"description": description,
	}


BUSINESS_NATURES = {
	"Consultancy": {
		"description": "Advisory and consulting firms qualifying needs, stakeholders, scope, value, and engagement timing.",
		"fields": [
			lead("advisory_area", "Advisory Area", "Select", options="Strategy\nTechnology\nTax\nRisk & Compliance\nFinance\nOperations\nHuman Resources\nOther", required=True, description="Which advisory capability is the prospect looking for?"),
			lead("current_challenge", "Current Challenge", "Text", required=True, description="What business problem or decision triggered this enquiry?"),
			lead("desired_outcome", "Desired Outcome", "Small Text", required=True, description="What measurable result would make the engagement successful?"),
			lead("organisation_size", "Organisation Size", "Select", options="1-10\n11-50\n51-200\n201-1000\n1000+"),
			lead("decision_makers", "Decision Makers", "Small Text", description="Who sponsors, evaluates, and approves the engagement?"),
			lead("urgency", "Required Start", "Select", options="Immediately\nWithin 30 days\n1-3 months\n3-6 months\nExploring"),
			lead("budget_range", "Budget Range", description="An indicative range or approved budget, if known."),
			lead("consultation_preference", "Consultation Preference", "Select", options="Online\nPhone\nOnsite"),
		],
	},
	"General Services": {
		"description": "Service businesses qualifying service fit, location, urgency, volume, budget, and decision readiness.",
		"fields": [
			lead("service_needed", "Service Needed", "Small Text", required=True),
			lead("service_location", "Service Location", required=True),
			lead("customer_type", "Customer Type", "Select", options="Individual\nSME\nCorporate\nGovernment\nNonprofit"),
			lead("scope_or_quantity", "Scope / Quantity", "Small Text"),
			lead("current_process", "Current Process", "Small Text"),
			lead("main_pain_points", "Main Pain Points", "Text"),
			lead("timeline", "Required Timeline", "Select", options="Urgent\nWithin 30 days\n1-3 months\nLater"),
			lead("budget_range", "Budget Range"),
		],
	},
	"Software / Web Development": {
		"description": "Software and technology sales discovery covering solution scope, users, integrations, delivery risk, and budget.",
		"fields": [
			lead("project_type", "Project Type", "Select", options="Website\nWeb Application\nMobile App\nERP / Business System\nAutomation\nData & Analytics\nAI Solution\nSupport", required=True),
			lead("business_problem", "Business Problem", "Text", required=True),
			lead("must_have_features", "Must-have Features", "Text", required=True),
			lead("expected_users", "Expected Users", "Int"),
			lead("existing_systems", "Existing Systems", "Small Text"),
			lead("integration_requirements", "Integration Requirements", "Small Text"),
			lead("target_launch_date", "Target Launch Date", "Date"),
			lead("budget_range", "Budget Range"),
		],
	},
	"Retail / POS": {
		"description": "Retail discovery for stores, sales channels, catalogue size, inventory controls, payments, and rollout.",
		"fields": [
			lead("number_of_outlets", "Number of Outlets", "Int", required=True),
			lead("sales_channels", "Sales Channels", "Select", options="In-store\nOnline\nIn-store & Online\nWholesale", required=True),
			lead("pos_devices", "Required POS Devices", "Int"),
			lead("catalogue_size", "Approximate SKU Count", "Int"),
			lead("current_pos", "Current POS / System"),
			lead("inventory_challenges", "Inventory Challenges", "Text"),
			lead("payment_methods", "Payment Methods", "Small Text"),
			lead("target_go_live", "Target Go-live", "Date"),
		],
	},
	"Manufacturing": {
		"description": "Manufacturing qualification across production type, planning, capacity, traceability, quality, and implementation.",
		"fields": [
			lead("products_made", "Products Manufactured", "Small Text", required=True),
			lead("production_type", "Production Type", "Select", options="Make to Stock\nMake to Order\nEngineer to Order\nProcess Manufacturing\nMixed", required=True),
			lead("facility_count", "Production Facilities", "Int"),
			lead("production_volume", "Typical Production Volume"),
			lead("planning_method", "Current Planning Method", "Small Text"),
			lead("traceability_need", "Traceability Requirement", "Select", options="None\nBatch\nSerial Number\nBatch & Serial Number"),
			lead("quality_requirements", "Quality / Compliance Requirements", "Text"),
			lead("implementation_timeline", "Implementation Timeline", "Select", options="0-3 months\n3-6 months\n6-12 months\nExploring"),
		],
	},
	"Professional Services": {
		"description": "Professional practices qualifying service lines, engagement models, resourcing, billing, compliance, and reporting.",
		"fields": [
			lead("practice_area", "Practice Area", "Small Text", required=True),
			lead("team_size", "Professional Team Size", "Int"),
			lead("engagement_model", "Engagement Model", "Select", options="Fixed Fee\nTime & Materials\nRetainer\nSuccess Fee\nMixed"),
			lead("monthly_engagements", "Monthly Client Engagements", "Int"),
			lead("workflow_challenges", "Workflow Challenges", "Text", required=True),
			lead("billing_method", "Current Billing Method"),
			lead("reporting_needs", "Reporting Needs", "Small Text"),
			lead("target_start", "Target Start", "Date"),
		],
	},
	"Construction & Property": {
		"description": "Construction and property pipeline discovery for projects, sites, budgets, approvals, subcontractors, and delivery controls.",
		"fields": [
			lead("business_segment", "Business Segment", "Select", options="Construction\nProperty Development\nProperty Management\nQuantity Surveying\nArchitecture\nFacilities Management", required=True),
			lead("active_projects", "Active Projects / Properties", "Int"),
			lead("typical_project_value", "Typical Project Value", "Currency"),
			lead("site_count", "Sites / Locations", "Int"),
			lead("current_system", "Current Project System"),
			lead("control_needs", "Required Controls", "Text", description="Budgeting, procurement, variations, progress billing, subcontractors, or maintenance."),
			lead("approval_stakeholders", "Approval Stakeholders", "Small Text"),
			lead("target_start", "Target Start", "Date"),
		],
	},
	"Healthcare & Clinics": {
		"description": "Healthcare discovery for facilities, patient volumes, clinical workflows, privacy, billing, and system integrations.",
		"fields": [
			lead("facility_type", "Facility Type", "Select", options="Clinic\nHospital\nPharmacy\nLaboratory\nDental Practice\nSpecialist Practice\nOther", required=True),
			lead("facility_count", "Number of Facilities", "Int"),
			lead("monthly_patients", "Monthly Patient Volume", "Int"),
			lead("priority_workflows", "Priority Workflows", "Text", required=True),
			lead("current_systems", "Current Clinical / Billing Systems", "Small Text"),
			lead("privacy_requirements", "Privacy / Regulatory Requirements", "Small Text"),
			lead("integration_requirements", "Required Integrations", "Small Text"),
			lead("target_go_live", "Target Go-live", "Date"),
		],
	},
	"Education & Training": {
		"description": "Education sales discovery for learner volumes, programmes, campuses, admissions, learning delivery, billing, and reporting.",
		"fields": [
			lead("institution_type", "Institution Type", "Select", options="School\nCollege\nUniversity\nTraining Provider\nOnline Academy\nCorporate Learning", required=True),
			lead("student_count", "Learner / Student Count", "Int"),
			lead("campus_count", "Campuses / Locations", "Int"),
			lead("programmes_offered", "Programmes Offered", "Small Text"),
			lead("priority_needs", "Priority Needs", "Text", required=True),
			lead("current_system", "Current Student / Learning System"),
			lead("reporting_requirements", "Reporting / Accreditation Needs", "Small Text"),
			lead("next_intake", "Next Intake / Deadline", "Date"),
		],
	},
	"Hospitality & Tourism": {
		"description": "Hospitality qualification for properties, capacity, booking channels, guest operations, payments, and seasonal deadlines.",
		"fields": [
			lead("property_type", "Business Type", "Select", options="Hotel\nLodge\nRestaurant\nTour Operator\nTravel Agency\nEvents Venue\nOther", required=True),
			lead("location_count", "Locations / Properties", "Int"),
			lead("capacity", "Rooms / Tables / Guest Capacity"),
			lead("booking_channels", "Booking / Sales Channels", "Small Text"),
			lead("current_system", "Current Booking / POS System"),
			lead("operational_challenges", "Operational Challenges", "Text", required=True),
			lead("integration_requirements", "Channel / Payment Integrations", "Small Text"),
			lead("season_deadline", "Season / Go-live Deadline", "Date"),
		],
	},
	"Logistics & Transport": {
		"description": "Transport and logistics discovery covering fleet, shipment volume, routes, tracking, proof of delivery, and billing.",
		"fields": [
			lead("transport_mode", "Transport Mode", "Select", options="Road Freight\nCourier\nPassenger\nAir\nSea\nRail\nMultimodal", required=True),
			lead("fleet_size", "Fleet Size", "Int"),
			lead("monthly_shipments", "Monthly Trips / Shipments", "Int"),
			lead("service_regions", "Service Regions", "Small Text"),
			lead("tracking_method", "Current Tracking Method"),
			lead("operational_challenges", "Operational Challenges", "Text", required=True),
			lead("integration_requirements", "Required Integrations", "Small Text"),
			lead("target_go_live", "Target Go-live", "Date"),
		],
	},
	"Agriculture & Agribusiness": {
		"description": "Agriculture discovery for operation type, land or production scale, seasons, traceability, procurement, and markets.",
		"fields": [
			lead("operation_type", "Operation Type", "Select", options="Crop Farming\nLivestock\nAgro-processing\nInputs & Supplies\nAggregation\nExport\nMixed", required=True),
			lead("products", "Products / Commodities", "Small Text", required=True),
			lead("operation_scale", "Acreage / Herd / Production Scale"),
			lead("location_count", "Farms / Locations", "Int"),
			lead("season_or_cycle", "Current Season / Production Cycle"),
			lead("priority_needs", "Priority Needs", "Text", required=True),
			lead("traceability_requirements", "Traceability / Compliance", "Small Text"),
			lead("decision_timeline", "Decision Timeline", "Select", options="This season\nNext season\nWithin 12 months\nExploring"),
		],
	},
	"Financial Services & Insurance": {
		"description": "Regulated financial sales discovery covering product lines, scale, controls, customer journeys, security, and compliance.",
		"fields": [
			lead("business_segment", "Business Segment", "Select", options="Banking\nMicrofinance\nInsurance\nInvestment\nPayments\nFintech\nAccounting Services", required=True),
			lead("products_offered", "Products Offered", "Small Text"),
			lead("customer_count", "Customer / Policy Count", "Int"),
			lead("priority_workflows", "Priority Workflows", "Text", required=True),
			lead("current_systems", "Current Core Systems", "Small Text"),
			lead("regulatory_requirements", "Regulatory Requirements", "Small Text"),
			lead("security_requirements", "Security / Hosting Requirements", "Small Text"),
			lead("target_go_live", "Target Go-live", "Date"),
		],
	},
	"Wholesale & Distribution": {
		"description": "Distribution discovery for catalogue, warehouses, order channels, pricing, fulfilment, credit controls, and delivery.",
		"fields": [
			lead("product_categories", "Product Categories", "Small Text", required=True),
			lead("catalogue_size", "Approximate SKU Count", "Int"),
			lead("warehouse_count", "Warehouses", "Int"),
			lead("customer_count", "Active Trade Customers", "Int"),
			lead("order_channels", "Order Channels", "Small Text"),
			lead("pricing_complexity", "Pricing / Discount Structure", "Text"),
			lead("delivery_operation", "Delivery / Fleet Operation", "Small Text"),
			lead("target_go_live", "Target Go-live", "Date"),
		],
	},
	"Automotive": {
		"description": "Automotive qualification for dealerships, workshops, parts, branches, service capacity, inventory, and customer follow-up.",
		"fields": [
			lead("business_type", "Business Type", "Select", options="Dealership\nWorkshop\nParts Retailer\nFleet Services\nRental\nMixed", required=True),
			lead("branch_count", "Branches", "Int"),
			lead("service_bays", "Service Bays", "Int"),
			lead("parts_catalogue_size", "Parts Catalogue Size", "Int"),
			lead("current_system", "Current Dealer / Workshop System"),
			lead("priority_needs", "Priority Needs", "Text", required=True),
			lead("integration_requirements", "Required Integrations", "Small Text"),
			lead("target_go_live", "Target Go-live", "Date"),
		],
	},
	"Nonprofit / NGO": {
		"description": "Mission-driven organisation discovery for programmes, beneficiaries, donors, grants, field operations, and reporting.",
		"fields": [
			lead("mission_area", "Mission / Programme Area", "Small Text", required=True),
			lead("programme_count", "Active Programmes", "Int"),
			lead("operating_regions", "Operating Regions", "Small Text"),
			lead("beneficiary_scale", "Beneficiary Scale"),
			lead("donor_reporting", "Donor Reporting Requirements", "Text", required=True),
			lead("grant_management", "Current Grant Management Process", "Small Text"),
			lead("field_data_needs", "Field Data Collection Needs", "Small Text"),
			lead("budget_cycle", "Budget / Funding Cycle"),
		],
	},
	"E-commerce": {
		"description": "Digital commerce discovery for platform, catalogue, markets, traffic, orders, payments, fulfilment, and growth.",
		"fields": [
			lead("commerce_platform", "Current Platform", "Select", options="None\nShopify\nWooCommerce\nMagento\nCustom\nMarketplace\nOther", required=True),
			lead("catalogue_size", "Product Catalogue Size", "Int"),
			lead("monthly_orders", "Monthly Orders", "Int"),
			lead("target_markets", "Target Markets", "Small Text"),
			lead("payment_methods", "Payment Methods", "Small Text"),
			lead("fulfilment_model", "Fulfilment Model", "Small Text"),
			lead("integration_requirements", "Required Integrations", "Text"),
			lead("growth_goal", "12-month Growth Goal", "Small Text"),
		],
	},
}


def seed_business_natures():
	"""Create curated seeds and merge updates without deleting customer-defined fields."""
	for name, definition in BUSINESS_NATURES.items():
		doc = (
			frappe.get_doc("AI Business Nature", name)
			if frappe.db.exists("AI Business Nature", name)
			else frappe.get_doc({"doctype": "AI Business Nature", "business_nature": name})
		)
		doc.description = definition["description"]
		existing = {row.fieldname: row for row in doc.get("lead_fields", [])}
		for values in definition["fields"]:
			row = existing.get(values["fieldname"])
			if row:
				row.update(values)
			else:
				doc.append("lead_fields", values)
		doc.flags.ignore_version = True
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)


def business_nature_options():
	rows = frappe.get_all(
		"AI Business Nature",
		fields=["name", "business_nature", "description"],
		order_by="business_nature asc",
	)
	for row in rows:
		doc = frappe.get_doc("AI Business Nature", row.name)
		row["lead_fields"] = [
			{
				"fieldname": field.fieldname,
				"label": field.label,
				"fieldtype": field.fieldtype,
				"required": bool(field.required),
				"description": field.description,
			}
			for field in doc.get("lead_fields", [])
		]
	return rows


def ensure_business_natures():
	"""Repair missing curated profiles before presenting the selector to a user."""
	existing = set(frappe.get_all("AI Business Nature", pluck="name"))
	if not set(BUSINESS_NATURES).issubset(existing):
		seed_business_natures()
	return business_nature_options()


def validate_business_nature(value, *, required=False):
	value = str(value or "").strip()
	if not value and not required:
		return None
	if not value or not frappe.db.exists("AI Business Nature", value):
		frappe.throw("Choose a supported business nature from the available options.", frappe.ValidationError)
	return value
