import unittest
import os
import json as standard_json
import example.json, example.macroparse

from boozetools.macroparse import compiler
from boozetools import runtime, algorithms

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

def parse_tester(self:unittest.TestCase, parse):
	# Smoke Test
	with self.subTest(text='25.2'): self.assertEqual(25.2, parse('25.2'))
	with self.subTest(text=r'"\u00ff"'): self.assertEqual(chr(255), parse(r'"\u00ff"'))
	
	# Glossary Entry
	with self.subTest(text='[[glossary entry]]'):
		data = parse(GLOSSARY_JSON)
		entry = data['glossary']['GlossDiv']['GlossList']['GlossEntry']
		self.assertEqual('Standard Generalized Markup Language', entry['GlossTerm'])
		self.assertEqual(["GML", "XML"], entry['GlossDef']['GlossSeeAlso'])


class TestJson(unittest.TestCase):
	
	def test_json_miniparser(self):
		parse_tester(self, example.json.parse)
	

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
		cls.scan_rules = runtime.SymbolicScanRules(action=scanner_data['action'], driver=example.macroparse.ExampleJSON())
		pass
	
	def macroscan_json(self, text):
		return algorithms.Scanner(text=text, automaton=self.dfa, rulebase=self.scan_rules, start='INITIAL')
	
	def test_00_macroparse_compiled_scanner(self):
		def parse(text):
			tokens = list(self.macroscan_json(text))
			assert len(tokens)
			return example.json.grammar.parse(tokens)
		parse_tester(self, parse)
	
	def test_01_macroparse_compiled_parser(self):
		parser_data = self.automaton['parser']
		spt = runtime.SymbolicParserTables(parser_data)
		combine = runtime.symbolic_reducer(example.macroparse.ExampleJSON())
		parse_tester(self, lambda text: algorithms.parse(spt, combine, self.macroscan_json(text)))
		pass

