import unittest
import os, pprint
import json as standard_json
import example.json

from boozetools.macroparse import compiler
from boozetools import runtime

# See https://json.org/example.html
GLOSSARY_JSON = """
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

class TestJson(unittest.TestCase):
	
	def test_00_smoke_test(self):
		self.assertEqual(25.2, example.json.parse('25.2'))
		self.assertEqual(chr(255), example.json.parse(r'"\u00ff"'))
	
	def test_01_glossary_entry(self):
		data = example.json.parse(GLOSSARY_JSON)
		entry = data['glossary']['GlossDiv']['GlossList']['GlossEntry']
		self.assertEqual('Standard Generalized Markup Language', entry['GlossTerm'])
		self.assertEqual(["GML", "XML"], entry['GlossDef']['GlossSeeAlso'])

class TestMacroCompiler(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		example_folder = os.path.dirname(example.json.__file__)
		automaton = compiler.compile_file(os.path.join(example_folder, 'json.md'))
		# The transition into and back out of JSON should be non-destructive, but it's worth being sure.
		serialized = standard_json.dumps(automaton)
		cls.automaton = standard_json.loads(serialized)
		scanner_data = cls.automaton['scanner']
		cls.dfa = runtime.CompactDFA(dfa=scanner_data['dfa'], alphabet=scanner_data['alphabet'])
		pass
	
	def test_00_smoke_test(self):
		assert False, "There's still a couple drivers to write."
