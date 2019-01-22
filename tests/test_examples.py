import unittest

from example import json

class TestJson(unittest.TestCase):
	
	def test_00_smoke_test(self):
		self.assertEqual(25.2, json.parse('25.2'))
	
	def test_01_glossary_entry(self):
		""" See https://json.org/example.html """
		text = """
{
    "glossary": {
        "title": "example glossary",
		"GlossDiv": {
            "title": "S",
			"GlossList": {
                "GlossEntry": {
                    "ID": "SGML",
					"SortAs": "SGML",
					"GlossTerm": "Standard Generalized Markup Language",
					"Acronym": "SGML",
					"Abbrev": "ISO 8879:1986",
					"GlossDef": {
                        "para": "A meta-markup language, used to create markup languages such as DocBook.",
						"GlossSeeAlso": ["GML", "XML"]
                    },
					"GlossSee": "markup"
                }
            }
        }
    }
}
		"""
		data = json.parse(text)
		entry = data['glossary']['GlossDiv']['GlossList']['GlossEntry']
		self.assertEqual('Standard Generalized Markup Language', entry['GlossTerm'])
		self.assertEqual(["GML", "XML"], entry['GlossDef']['GlossSeeAlso'])
		