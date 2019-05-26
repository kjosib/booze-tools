import unittest

from boozetools import context_free, LR, algorithms


def collect(*args): return args

def each_token(s): return [(t,t) for t in s.split()]

class TestLalr(unittest.TestCase):
	def setUp(self):
		print(self._testMethodName)
		self.g = context_free.ContextFreeGrammar()
		self.g.start.append('S')
		self.good = []
	def tearDown(self):
		print(self.g.find_epsilon())
		table = LR.lalr_construction(self.g)
		table.display()
		for sentence in self.good:
			with self.subTest(sentence=sentence):
				algorithms.parse(table, self.combine, each_token(sentence))
	def combine(self, rule_id, arg_stack:list):
		pass
	def r(self, lhs, rhs:str):
		rhs = rhs.split()
		self.g.rule(lhs.strip(), rhs, None if len(rhs)==1 else len(self.g.rules), None)
	def R(self, text):
		lhs, rest = text.split(':')
		for rhs in rest.split('|'): self.r(lhs, rhs)
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
