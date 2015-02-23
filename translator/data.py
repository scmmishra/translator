# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals
import frappe, os

from frappe.translate import read_csv_file, get_all_languages, write_translations_file, get_messages_for_app
from translator.doctype.translated_message.translated_message import get_placeholders_count
import frappe.utils
from csv import writer


def import_languages():
	with open(frappe.get_app_path("frappe", "data", "languages.txt"), "r") as f:
		for l in unicode(f.read(), "utf-8").splitlines():
			if l:
				code, name = l.strip().split(None, 1)
				if not frappe.db.exists("Language", code):
					print "inserting " + code
					frappe.get_doc({
						"doctype":"Language",
						"language_code": code,
						"language_name": name
					}).insert()

		frappe.db.commit()

def import_translations():
	apps_path = frappe.get_app_path("frappe", "..", "..")
	for app in os.listdir(apps_path):
		translations_folder = os.path.join(apps_path, app, app, "translations")
		if os.path.exists(translations_folder):
			for lang in frappe.db.sql_list("select name from tabLanguage"):
				path = os.path.join(translations_folder, lang + ".csv")
				if os.path.exists(path):
					print "Evaluating {0}...".format(lang)
					data = read_csv_file(path)
					for m in data:
						if not frappe.db.get_value("Translated Message",
							{"language": lang, "source": m[0]}):
							frappe.get_doc({
								"doctype": "Translated Message",
								"language": lang,
								"source": m[0],
								"translated": m[1],
								"verfied": 0
							}).insert()
							frappe.db.commit()
				else:
					print path + " does not exist"


def export_translations():
	# ssh -p 9999 frappe@frappe.io "cd /home/frappe/frappe-bench/apps/frappe && git diff" | patch -p1
	for lang in get_all_languages():
		if lang!="en":
			print "exporting " + lang
			edited = dict(frappe.db.sql("""select source, translated
				from `tabTranslated Message` where language=%s""", lang))
			for app in frappe.get_all_apps(True):
				path = os.path.join(frappe.get_app_path(app, "translations", lang + ".csv"))
				if os.path.exists(path):
					# only update existing strings
					current = dict(read_csv_file(path))

					for key in current:
						current[key] = edited.get(key) or current[key]

					write_translations_file(app, lang, current, sorted(current.keys()))

def import_translations_from_file(lang, fname, editor):
	from frappe.translate import read_csv_file

	frappe.local.session.user = editor

	for m in read_csv_file(fname):
		src = frappe.db.get_value("Translated Message", {"language": lang, "source": m[0]}, ["name", "source", "translated"])
		if src and src[2] != m[1]:
			message = frappe.get_doc("Translated Message", src[0])
			message.translated = m[1]
			try:
				message.save()
				frappe.db.commit()
				print src[1] + " updated"
			except frappe.ValidationError:
				print src[1] + " ignored"
		else:
			message = frappe.new_doc("Translated Message")
			message.source = m[0]
			message.translated = m[1]
			message.language = lang
			print "saving", m[0]
			message.save()

def import_source_messages():
	for app in frappe.db.sql_list("select name from `tabTranslator App`"):
		app_version = frappe.get_hooks(app_name='frappe')['app_version'][0]
		messages = get_messages_for_app(app)
		for message in messages:
			source_message = frappe.db.get_value("Source Message", {"message": message[1]}, ["name", "message", "position", "app_version"], as_dict=True)
			if source_message:
				if source_message["position"] != message[0] or source_message["app_version"] != app_version:
					d = frappe.get_doc("Source Message", source_message['name'])
					d.app_version = app_version
					d.position = message[0]
					d.save()
			else:
				d = frappe.new_doc("Source Message")
				d.position = message[0]
				d.message = message[1]
				d.app = app
				d.app_version = app_version
				d.save()

def import_translated_from_text_files(untranslated_dir, translated_dir):
	def read_file(path):
		with open(path) as f:
			lines = [x.decode('utf-8-SIG').rstrip('\r\n') for x in f.readlines()]
			lines = [x for x in lines if x]
			return lines

	def restore_newlines(s):
		return (s.replace("||||||", "\n\n")
				.replace("| | | | | |", "\n\n")
				.replace("|||||", "\\\n")
				.replace("| | | | |", "\\\n")
				.replace("||||", "\\n")
				.replace("| | | |", "\\n")
				.replace("|||", "\n")
				.replace("| | |", "\n"))
	
	for lang in frappe.db.sql_list("select name from tabLanguage"):
		if lang == 'en':
			continue

		scache ={}
		for s, t in zip(read_file(os.path.join(untranslated_dir, lang+'.txt')), read_file(os.path.join(translated_dir, lang+'.txt'))):
			if scache.get(s):
				source = scache[s]
			else:
				source = frappe.db.get_value("Source Message", {"message": restore_newlines(s)})
				scache[s] = source
			dest = frappe.db.get_value("Translated Message", {"source": source, "language": lang})
			if not source:
				print 'Cannot find source message for', s
				continue

			if not get_placeholders_count(s) == get_placeholders_count(t):
				continue

			if dest:
				frappe.db.set_value("Translated Message", dest, "translated", restore_newlines(t))
			else:
				d = frappe.new_doc("Translated Message")
				d.language = lang
				d.translated = restore_newlines(t)
				d.source = source
				d.save()
		print 'done for', lang

def write_untranslated_csvs(path):
	for lang in frappe.db.sql_list("select name from tabLanguage"):
		write_untranslated_file(lang, os.path.join(path, lang+'.txt'))
		

def write_untranslated_file(lang, path):
	def escape_newlines(s):
		return (s.replace("\\\n", "|||||")
				.replace("\\n", "||||")
				.replace("\n", "|||"))
	
	with open(path, "w") as f:
		for m in get_untranslated(lang):
			# replace \n with ||| so that internal linebreaks don't get split
			f.write((escape_newlines(m) + os.linesep).encode("utf-8"))

def get_untranslated(lang):
	return frappe.db.sql_list("""select source.message from `tabSource Message` source 
	left join `tabTranslated Message` translated on (source.name=translated.source and translated.language = %s) 
	where translated.name is null and source.disabled != 1""", (lang, ))

def write_csv_for_all_languages():
	langs = frappe.db.sql_list("select name from tabLanguage")
	apps = frappe.db.sql_list("select name from `tabTranslator App`")
	for lang in langs:
		for app in apps:
			write_csv(app, lang, frappe.utils.get_files_path("{0}-{1}.csv".format(app, lang)))

def write_csv(app, lang, path):
	translations = frappe.db.sql("""select source.position, source.message, translated.translated from `tabSource Message` source 
	left join `tabTranslated Message` translated on (source.name=translated.source and translated.language = %s) 
	where translated.name is not null and source.disabled != 1 and source.app = %s""", (lang, app))
	with open(path, 'w') as msgfile:
		w = writer(msgfile, lineterminator='\n')
		for t in translations:
			w.writerow([t[0].encode('utf-8') if t[0] else '', t[1].encode('utf-8'), t[2].encode('utf-8')])

