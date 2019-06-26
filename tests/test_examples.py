import unittest
import os
import json as standard_json
import example.mini_json, example.macro_json, example.calculator

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


class TestMiniJson(unittest.TestCase):
	
	def test_json_miniparser(self):
		parse_tester(self, example.mini_json.parse)
	

class TestMacroJson(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		example_folder = os.path.dirname(example.mini_json.__file__)
		automaton = compiler.compile_file(os.path.join(example_folder, 'json.md'), method='LALR')
		# The transition into and back out of JSON should be non-destructive, but it's worth being sure.
		serialized = standard_json.dumps(automaton)
		cls.automaton = standard_json.loads(serialized)
		scanner_data = cls.automaton['scanner']
		cls.dfa = runtime.CompactDFA(dfa=scanner_data['dfa'], alphabet=scanner_data['alphabet'])
		cls.scan_rules = runtime.BoundScanRules(action=scanner_data['action'], driver=example.macro_json.ExampleJSON())
		pass
	
	def macroscan_json(self, text):
		return algorithms.Scanner(text=text, automaton=self.dfa, rules=self.scan_rules, start='INITIAL')
	
	def test_00_macroparse_compiled_scanner(self):
		def parse(text):
			tokens = list(self.macroscan_json(text))
			assert len(tokens)
			return example.mini_json.grammar.parse(tokens)
		parse_tester(self, parse)
	
	def test_01_macroparse_compiled_parser(self):
		parser_data = self.automaton['parser']
		spt = runtime.CompactHandleFindingAutomaton(parser_data)
		combine = runtime.parse_action_bindings(example.macro_json.ExampleJSON())
		parse_tester(self, lambda text: algorithms.parse(spt, combine, self.macroscan_json(text)))
		pass

class TestCalculator(unittest.TestCase):
	def test_00_simple_operations(self):
		for text, expect in [
			('12.5', 12.5),
			('-12.5', -12.5),
			('3+ 4', 7),
			('3+-4', -1),
			('3+4+5', 12),
			('3*4+5', 17),
			('3+4*5', 23),
			('(3+4)*5', 35),
			('2^3', 8),
			('2^3^2', 512),  # Exponentiation is right-associative.
			('(2^3)^2', 64),
			('-1 ^ 2', 1), # THIS is why unary negation needs a higher precedence level.
			('a=3', 3),
			('b=4', 4),
			('a^2 + b^2 - 25', 0),
			('e^(i*pi)', -1),
			('3i-2', -2+3j),
		]:
			with self.subTest(text=text):
				self.assertAlmostEqual(example.calculator.parse(text), expect)
