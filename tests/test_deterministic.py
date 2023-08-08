import unittest

from boozetools.parsing import automata, shift_reduce
from boozetools.parsing.context_free import ContextFreeGrammar, LEFT, RIGHT, SemanticAction, Rule
from boozetools.parsing.lalr import lalr_construction
from boozetools.parsing.lr1 import canonical_lr1, minimal_lr1

def mysterious_reduce_conflict():
	""" This is your standard way to trigger a "mysterious" reduce/reduce conflict in LALR. """
	return ContextFreeGrammar.shorthand("S", {'S':'aXd|aYe|bXe|bYd', 'X':'c', 'Y':'c',})

def mysterious_invasive_conflict():
	"""
	This example comes from the IELR paper, page 945.
	It's a simple grammar for a language with four members; the grammar is not LR(1) due to an
	obvious shift/reduce conflict at 'aa.a'; we exclude 'aaaa' by declaring 'a' as left-associative
	but the LALR algorithm accidentally removes 'baab' from the language at the same time.
	Thus we have a "mysterious invasive conflict": canonical LR(1) correctly recognizes 'baab'.
	"""
	cfg = ContextFreeGrammar.shorthand("S", {'S': 'aAa|bAb', 'A':'a|aa'})
	cfg.assoc(LEFT, ['a'])
	return cfg

class TestContextFree(unittest.TestCase):
	def test_decide_sr(self):
		sut = ContextFreeGrammar.shorthand('S', {'S': 'abc|ab|abd'})
		assert sut.decide_shift_reduce('c', 0) is None
		sut.assoc(RIGHT, ['c'])
		sut.assoc(LEFT, ['d'])
		assert sut.decide_shift_reduce('c', 0) is RIGHT
		assert sut.decide_shift_reduce('d', 2) is LEFT

class TableMethodTester(unittest.TestCase):
	def setUp(self):
		print(self._testMethodName)
		self.g = ContextFreeGrammar()
		self.g.start.append('S')
		self.good = []
		self.bad = []
		self.pure = True
	@staticmethod
	def construct(cfg) -> automata.HFA: raise NotImplementedError()
	def tearDown(self):
		try: table = automata.tabulate(self.construct(self.g), self.g, style=automata.DeterministicStyle(True))
		except automata.PurityError:
			assert not self.pure
			if self.good or self.bad: table = automata.tabulate(self.construct(self.g), self.g,
																style=automata.DeterministicStyle(False))
			else: return
		#table.display()
		for sentence in self.good:
			with self.subTest(sentence=sentence):
				shift_reduce.trial_parse(table, sentence.split())
		for sentence in self.bad:
			with self.subTest(sentence=sentence):
				try: shift_reduce.trial_parse(table, sentence.split())
				except ValueError: pass
				else: assert False, "This should have raised an exception."
	def r(self, lhs, rhs:str):
		rhs = rhs.split()
		rule = Rule(lhs.strip(), tuple(rhs), None, SemanticAction('x', ()), None)
		self.g.add_rule(rule)
	def R(self, text):
		lhs, rest = text.split(':')
		for rhs in rest.split('|'): self.r(lhs, rhs)

class TestLALR(TableMethodTester):
	
	construct = staticmethod(lalr_construction)
	
	def test_00_single_rename(self):
		self.R('S:r')
		self.good.append('r')
	def test_01_single_epsilon_rule(self):
		self.R('S:')
		self.good.append('')
	def test_02_right_recursion(self):
		self.R('S:x|x S')
	def test_03_left_recursion_(self):
		self.R('S:[ U ]')
		self.R('U:L')
		self.R('L:x')
		self.R('L:L x')
		# self.g.display()
		self.good.append('[ x ]')
		self.good.append('[ x x x x ]')
	def test_04_left_recursive_alternation(self):
		self.R('S:x|S y x')
	def test_05_shift_reduce_conflict(self):
		self.R('S: E | S + S')
		self.pure = False
	def test_06_deep_renaming(self):
		self.R('S:A')
		self.R('A:B')
		self.R('B:C')
		self.R('C:d')
		self.good.append('d')
	def test_10_smoke_test(self):
		# Parsing Techniques: A Practical Guide -- Page 201
		self.R('S:E')
		self.R('E:E - T | T')
		self.R('T:n | ( E )')
	def test_11_invasive(self):
		self.g = mysterious_invasive_conflict()
		self.good = ['a a a', 'b a b',]
		self.bad = [
			'a a a a', # Not a member because 'a' is left-associative. Otherwise, non-LR(1).
			'b a a b', # This is a failing of the LALR algorithm. Canonical-LR(1) would recognize it.
		]
	def test_12_new(self):
		self.g = mysterious_reduce_conflict()
		self.pure = False
		self.good = ['a c d', 'b c e', ]
		self.bad = ['a c e', 'b c d', ] # This is because X is chosen over Y, being defined earlier.
		

class TestCLR(TableMethodTester):
	construct = staticmethod(canonical_lr1)
	def test_invasive(self):
		self.g = mysterious_invasive_conflict()
		self.good = ['a a a', 'b a b', 'b a a b',]
		self.bad = ['a a a a',]
	def test_new(self):
		self.g = mysterious_reduce_conflict()
		self.good = ['a c d', 'a c e', 'b c d', 'b c e']

class TestLR1(TableMethodTester):
	construct = staticmethod(minimal_lr1)
	def test_invasive(self):
		self.g = mysterious_invasive_conflict()
		self.good = ['a a a', 'b a b', 'b a a b',]
		self.bad = ['a a a a',]
	def test_new(self):
		self.g = mysterious_reduce_conflict()
		self.good = ['a c d', 'a c e', 'b c d', 'b c e']
