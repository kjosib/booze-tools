import unittest
import os
import json as standard_json
import importlib

import example.mini_json, example.macro_json, example.calculator

from boozetools.macroparse import compiler, expansion
from boozetools.parsing import shift_reduce
from boozetools.parsing.interface import ParseError, ParseErrorListener
from boozetools.parsing.general import brute_force, gss
from boozetools.scanning.engine import IterableScanner
from boozetools.scanning.interface import ScannerBlocked
from boozetools.macroparse import runtime

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

mock_parse_listener = ParseErrorListener()

def parse_tester(self:unittest.TestCase, parse):
	# Smoke Test
	with self.subTest(text='25.2'): self.assertEqual(25.2, parse('25.2'))
	with self.subTest(text=r'"\u00ff"'): self.assertEqual(chr(255), parse(r'"\u00ff"'))
	
	# Glossary Entry
	with self.subTest(text='[[glossary entry]]'):
		try:data = parse(GLOSSARY_JSON)
		except ScannerBlocked as err:
			print(repr(GLOSSARY_JSON[err.position:err.position+10]))
			raise
		entry = data['glossary']['GlossDiv']['GlossList']['GlossEntry']
		self.assertEqual('Standard Generalized Markup Language', entry['GlossTerm'])
		self.assertEqual(["GML", "XML"], entry['GlossDef']['GlossSeeAlso'])

def compile_example(which, method, verbose=False):
	""" Returns a set of tables; good smoke test overall for sample grammars. """
	return compiler.compile_file(os.path.join(example_folder, which+'.md'), method=method, verbose=verbose)

class TestMiniJson(unittest.TestCase):
	
	def test_json_miniparser(self):
		parse_tester(self, example.mini_json.parse)
	

class TestMacroJson(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		tables = compile_example('json', 'LALR')
		# The transition into and back out of JSON should be non-destructive, but it's worth being sure.
		serialized = standard_json.dumps(tables)
		cls.tables = standard_json.loads(serialized)

	def macroscan_json(self, text):
		scanner_table = self.tables['scanner']
		dfa = expansion.CompactDFA(dfa=scanner_table['dfa'], alphabet=scanner_table['alphabet'])
		driver = example.macro_json.ExampleJSON()
		bindings = runtime.MacroScanBindings(driver, expansion.scan_actions(scanner_table['action']))
		return IterableScanner(text, dfa, bindings=bindings, start='INITIAL')
	
	def test_00_macroparse_compiled_scanner(self):
		def parse(text):
			tokens = list(self.macroscan_json(text))
			assert len(tokens)
			return example.mini_json.grammar.parse(tokens)
		parse_tester(self, parse)
	
	def test_01_macroparse_compiled_parser(self):
		spt = expansion.CompactHFA(self.tables['parser'])
		combine = runtime.parse_action_bindings(example.macro_json.ExampleJSON(), spt.each_constructor())
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
				self.assertAlmostEqual(example.calculator.calculator.parse(text), expect)

class SimpleParseDriver:
	""" Act as a stand-in for parsing non-deterministic things as needed for the tests. """
	@staticmethod
	def parse_nothing(): return ()

LONG_STRING = 'abbabbaaababaaaabbbbbbbaaaabaabbaabaaaabababaaaaba'
LONG_STRING = LONG_STRING + LONG_STRING[::-1] + 'a'
PALINDROMES = ['', 'a', 'aa', 'aba', 'abba', 'ababa', 'abbbba', 'abbbbba', 'abbabba', (LONG_STRING + LONG_STRING[::-1])]

class TestPalindrome(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.automaton = compile_example('nondeterministic/palindrome', 'LR1', verbose=True)
		parse_table = cls.automaton['parser']
		assert parse_table['splits']
		cls.hfa = expansion.CompactHFA(parse_table)
		
	# @unittest.skip('time trials')
	def test_brute_force_and_ignorance(self):
		combine = runtime.parse_action_bindings(SimpleParseDriver(), self.hfa.each_constructor())
		for string in PALINDROMES:
			with self.subTest('Palindrome: '+string):
				parser = brute_force.BruteForceAndIgnorance(self.hfa, combine, language="Palindrome")
				for c in string: parser.consume(c, c)
				result = parser.finish()
				assert len(result) == 1
				tree = result[0]
				while isinstance(tree, tuple) and tree:
					assert tree[0] == tree[2]
					tree = tree[1]
				if tree: assert isinstance(tree, str) and len(tree)==1
		parser = brute_force.BruteForceAndIgnorance(self.hfa, combine, language="Palindrome")
		for c in LONG_STRING: parser.consume(c, c)
		with self.assertRaises(ParseError):
			parser.finish()

	# @unittest.skip('time trials')
	def test_gss_trial_palindromes(self):
		for string in PALINDROMES:
			with self.subTest('Palindrome: '+string):
				gss.gss_trial_parse(self.hfa, string, language="Palindrome")
		try: gss.gss_trial_parse(self.hfa, LONG_STRING, language="Palindrome")
		except ParseError: pass
		else: assert False
	
	
class TestHiddenRecursion(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.automaton = compile_example('nondeterministic/hidden_recursion', 'LR1')
		cls.hfa = expansion.CompactHFA(cls.automaton['parser'])
	
	
	def test_gss_hidden_right(self):
		for s in ['b', 'ab', 'aab', 'aaaaaaab']:
			with self.subTest(s=s):
				gss.gss_trial_parse(self.hfa, s, language="HiddenRight")
	
	def test_gss_hidden_left(self):
		for s in ['a', 'ab', 'abb', 'abbb']:
			with self.subTest(s=s):
				gss.gss_trial_parse(self.hfa, s, language="HiddenLeft")
		try: gss.gss_trial_parse(self.hfa, 'ba', language="HiddenLeft")
		except ParseError: pass
		else: assert False
	
	def test_hidden_mid(self):
		gss.gss_trial_parse(self.hfa, 'a', language='HiddenMid')
		for bad in ['aa', '']:
			with self.subTest(s=bad):
				try: gss.gss_trial_parse(self.hfa, bad, language='HiddenMid')
				except ParseError: pass
				else: assert False
	
class TestSampleLanguages(unittest.TestCase):
	def test_they_should_build(self):
		for identity in 'decaf', 'pascal':
			with self.subTest(identity):
				compile_example(identity, 'LR1')
	
	def test_pascal(self):
		importlib.import_module("example.pascal")
