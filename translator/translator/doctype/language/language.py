# Copyright (c) 2015, Frappe Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from translator.data import get_lang_name

class Language(Document):
	def validate(self):
		name_by_google = get_lang_name(self.language_code)
		if name_by_google:
			self.language_name = name_by_google

def clear_cache():
	for lang in frappe.db.sql_list("select name from tabLanguage"):
		frappe.cache().delete_value("lang-data:" + lang)
