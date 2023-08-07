import unittest

from boozetools.parsing import context_free
from boozetools.parsing.interface import ParseError
from boozetools.parsing.lr0 import lr0_construction, ParseItemMap
from boozetools.parsing.lalr import lalr_construction
from boozetools.parsing.lr1 import canonical_lr1, minimal_lr1

class GrammarTester(unittest.TestCase):
	
	def setUp(self):
		print(self._testMethodName)
		self.cfg = context_free.ContextFreeGrammar()
		self.cfg.start.append('S')
		self.pathological = False
	
	def r(self, lhs, rhs: str):
		rhs_syms = tuple(rhs.split())
		rule = context_free.Rule(lhs.strip(), rhs_syms, None, context_free.SemanticAction('x', ()), None)
		self.cfg.add_rule(rule)
	
	def R(self, text):
		lhs, rest = text.split(':')
		for rhs in rest.split('|'): self.r(lhs, rhs)
	
	def RR(self, rules: str):
		for text in rules.splitlines():
			text = text.strip()
			if text: self.R(text)

	def check_postcondition(self): raise NotImplementedError(type(self))

	def tearDown(self):
		try: self.cfg.validate()
		except context_free.Fault: assert self.pathological, "Grammar %r should have validated." % self._testMethodName
		else:
			assert not self.pathological, "Grammar %r should not have validated."%self._testMethodName
			self.check_postcondition()
	
class TestTableConstructions(GrammarTester):
	
	def setUp(self):
		super().setUp()
		self.good = []
		self.bad = []
		self.expect_lr1_size = 0
	
	def check_postcondition(self):
		pim = ParseItemMap.from_grammar(self.cfg)
		constructions = [
			("LR(0)", lr0_construction(pim)),
			("LALR(1)", lalr_construction(self.cfg)),
			("Canonical LR(1)", canonical_lr1(self.cfg)),
			("Minimal LR(1)", minimal_lr1(self.cfg)),
		]
		if self.expect_lr1_size:
			self.assertEqual(self.expect_lr1_size, len(constructions[-1][1].graph))
		for cons_name, hfa in constructions:
			for sentence in self.good:
				with self.subTest(cons=cons_name, sentence=sentence):
					assert hfa.trial_parse(self.cfg.rules, sentence)
			for sentence in self.bad:
				with self.subTest(cons=cons_name, sentence=sentence):
					try:
						hfa.trial_parse(self.cfg.rules, sentence)
					except ParseError: pass
					else: assert False, "%r should not be accepted." % sentence
	
	def test_00_non_lalr(self):
		""" This grammar is LR1, but not LALR. """
		self.RR("""
		S:a X d | a Y e | b X e | b Y d
		X:c
		Y:c
		""")
		self.good = ['acd', 'ace', 'bcd', 'bce']
		self.expect_lr1_size = 14
	
	def test_01_even_length_palindromes(self):
		""" This is a strictly non-deterministic, but unambiguous grammar. """
		self.R("S:|a S a|b S b")
		self.good = ['aabbbbaa', 'abba', 'baab', 'abbaabba', '']
		self.bad = [
			'xyz', # Contains unrecognized tokens
			'aba', # Not of even-length
			'abab', # Not a palindrome
		]
	
	def test_02_mild_ambiguity(self):
		""" There are exactly two parses for the single sentence in this language. """
		self.R('S:a X|Y c')
		self.R('X:b c')
		self.R('Y:a b')
		self.good = ['abc']
		self.bad = ['abbc']
	
	def test_03_pathology_self_production(self):
		"""
		This shows one fly in the trial_parse ointment: a symbol that produces itself
		(possibly indirectly) creates an infinite loop in the set of possible parses.
		"""
		self.R('S: X b')
		self.R('X: a | X')
		self.pathological = True
	
	def test_04_pathology_mutual_self_production(self):
		"""
		This shows one fly in the trial_parse ointment: a symbol that produces itself
		(possibly indirectly) creates an infinite loop in the set of possible parses.
		"""
		self.R('S: X c')
		self.R('X: a | Y')
		self.R('Y: b | X')
		self.pathological = True
	
	def test_05_pathology_boundless_nullable(self):
		"""
		This shows the other fly in the trial_parse ointment: a symbol that produces
		unbounded nullable repetition creates another kind of infinite loop.
		"""
		self.R('S: X b')
		self.R('X: Y | Y X')
		self.R('Y: | a')
		self.pathological = True
	
	def test_06_pathology_no_base_case(self):
		"""
		This ought to fail, as the language contains no finite strings!
		"""
		self.R('S: X c')
		self.R('X : X a')
		pim = ParseItemMap.from_grammar(self.cfg)
		print(lr0_construction(pim).graph[0].shift)
		self.pathological = True

	def test_07_pathology_mutual_no_base_case(self):
		"""
		This ought to fail, as the language contains no finite strings!
		"""
		self.R('S: X c')
		self.R('X : Y a')
		self.R('Y : X b')
		self.pathological = True

	def test_08_zero_or_more(self):
		""" Nullable left-recursion in first position is normal. Here S is nullable (by way of E) and left-recursive. """
		self.R('S: E | S x')
		self.R('E: | y')
		self.good = ['', 'xxx', 'y', 'yxxx']
		
	def test_09_pathology_boundless_nullable_type_two(self):
		""" The Nullable Loop Detector can be a tad tricky to get right... """
		self.R('S: E | S x')
		self.R('E: | y | E S')
		self.pathological = True
	
	def test_10_hidden_right_recursion(self):
		self.R('S: a S E | b')
		self.R('E: ')
		self.good = ['b', 'ab', 'aab', 'aaab']
		self.bad = ['', 'a', 'ba']
	
	@unittest.skip("This test breaks the simplistic trial-parser.")
	def test_11_hidden_left_recursion(self):
		self.R('S: E S b | a')
		self.R('E: ')
		self.good = ['a', 'ab', 'abb', 'abbb']
	
	@unittest.skip("This test breaks the simplistic trial-parser.")
	def test_12_hidden_mid_recursion(self):
		self.R('S: E S E | a')
		self.R('E: ')
		self.good = ['a']
