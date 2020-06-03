import unittest
import os
import json as standard_json
import example.mini_json, example.macro_json, example.calculator

from boozetools.macroparse import compiler
from boozetools.parsing import shift_reduce
from boozetools.parsing.general import brute_force, gss
from boozetools.support import runtime, interfaces, expansion
from boozetools.scanning import recognition

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
example_folder = os.path.dirname(example.mini_json.__file__)

mock_scan_listener = interfaces.ScanErrorListener()
mock_parse_listener = interfaces.ParseErrorListener()

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
def compile_example(which, method):
	""" Returns a set of tables; good smoke test overall for sample grammars. """
	return compiler.compile_file(os.path.join(example_folder, which+'.md'), method=method)

class TestMiniJson(unittest.TestCase):
	
	def test_json_miniparser(self):
		parse_tester(self, example.mini_json.parse)
	

class TestMacroJson(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		automaton = compile_example('json', 'LALR')
		# The transition into and back out of JSON should be non-destructive, but it's worth being sure.
		serialized = standard_json.dumps(automaton)
		cls.automaton = standard_json.loads(serialized)
		scanner_data = cls.automaton['scanner']
		cls.dfa = expansion.CompactDFA(dfa=scanner_data['dfa'], alphabet=scanner_data['alphabet'])
		cls.scan_rules = runtime.BoundScanRules(action=scanner_data['action'], driver=example.macro_json.ExampleJSON())
		pass
	
	def macroscan_json(self, text):
		return recognition.IterableScanner(text=text, automaton=self.dfa, rules=self.scan_rules, start='INITIAL', on_error=mock_scan_listener)
	
	def test_00_macroparse_compiled_scanner(self):
		def parse(text):
			tokens = list(self.macroscan_json(text))
			assert len(tokens)
			return example.mini_json.grammar.parse(tokens)
		parse_tester(self, parse)
	
	def test_01_macroparse_compiled_parser(self):
		parser_data = self.automaton['parser']
		spt = expansion.CompactHandleFindingAutomaton(parser_data)
		combine = runtime.parse_action_bindings(example.macro_json.ExampleJSON(), spt.message_catalog)
		parse_tester(self, lambda text: shift_reduce.parse(spt, combine, self.macroscan_json(text), on_error=mock_parse_listener))
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
				self.assertAlmostEqual(example.calculator.instance.parse(text), expect)

class SimpleParseDriver:
	""" Act as a stand-in for parsing non-deterministic things as needed for the tests. """
	@staticmethod
	def parse_nothing(): return ()

LONG_STRING = 'abbabbaaababaaaabbbbbbbaaaabaabbaabaaaabababaaaaba'
LONG_STRING = LONG_STRING + LONG_STRING[::-1] + 'a'
PALINDROMES = ['abba', 'ababa', 'abbbba', 'abbbbba', 'abbabba', (LONG_STRING + LONG_STRING[::-1])]

class TestNonDeterministic(unittest.TestCase):
	
	@classmethod
	def setUpClass(cls) -> None:
		automaton = compile_example('nondeterministic_grammar', 'LR1')
		cls.parse_table = expansion.CompactHandleFindingAutomaton(automaton['parser'])
	
	# @unittest.skip('time trials')
	def test_brute_force_and_ignorance(self):
		combine = runtime.parse_action_bindings(SimpleParseDriver(), self.parse_table.message_catalog)
		for string in PALINDROMES:
			with self.subTest('Palindrome: '+string):
				parser = brute_force.BruteForceAndIgnorance(self.parse_table, combine, language="Palindrome")
				for c in string: parser.consume(c, c)
				result = parser.finish()
				assert len(result) == 1
				tree = result[0]
				while isinstance(tree, tuple) and tree:
					assert tree[0] == tree[2]
					tree = tree[1]
				if tree: assert isinstance(tree, str) and len(tree)==1
		parser = brute_force.BruteForceAndIgnorance(self.parse_table, combine, language="Palindrome")
		for c in LONG_STRING: parser.consume(c, c)
		try: result = parser.finish()
		except interfaces.GeneralizedParseError: pass
		else: assert False

	
	# @unittest.skip('time trials')
	def test_gss_trial_palindromes(self):
		for string in PALINDROMES:
			with self.subTest('Palindrome: '+string):
				gss.gss_trial_parse(self.parse_table, string, language="Palindrome")
		try: gss.gss_trial_parse(self.parse_table, LONG_STRING, language="Palindrome")
		except interfaces.GeneralizedParseError: pass
		else: assert False
	
	def test_gss_hidden_right(self):
		for s in ['b', 'ab', 'aab', 'aaaaaaab']:
			with self.subTest(s=s):
				gss.gss_trial_parse(self.parse_table, s, language="HiddenRight")
	
	def test_gss_hidden_left(self):
		for s in ['a', 'ab', 'abb', 'abbb']:
			with self.subTest(s=s):
				gss.gss_trial_parse(self.parse_table, s, language="HiddenLeft")
		try: gss.gss_trial_parse(self.parse_table, 'ba', language="HiddenLeft")
		except interfaces.GeneralizedParseError: pass
		else: assert False
	
	def test_hidden_mid(self):
		gss.gss_trial_parse(self.parse_table, 'a', language='HiddenMid')
		for bad in ['aa', '']:
			with self.subTest(s=bad):
				try: gss.gss_trial_parse(self.parse_table, bad, language='HiddenMid')
				except interfaces.GeneralizedParseError: pass
				else: assert False
	
class TestSampleLanguages(unittest.TestCase):
	def test_they_should_build(self):
		for identity in 'decaf', 'pascal':
			with self.subTest(identity):
				compile_example(identity, 'LR1')
		
