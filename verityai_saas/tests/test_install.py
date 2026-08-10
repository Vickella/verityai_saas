from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas.install import REQUIRED_ENGINE_DOCTYPES, validate_engine_installation


class TestStandaloneInstallation(FrappeTestCase):
	def test_engine_dependency_is_validated_locally(self):
		self.assertTrue(validate_engine_installation())

	@patch("verityai_saas.install.frappe.db.exists", return_value=False)
	def test_missing_engine_has_clear_local_error(self, _exists):
		with self.assertRaises(frappe.ValidationError) as error:
			validate_engine_installation()
		for doctype in REQUIRED_ENGINE_DOCTYPES:
			self.assertIn(doctype, str(error.exception))
