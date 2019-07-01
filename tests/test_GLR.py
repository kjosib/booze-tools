import unittest

from boozetools import context_free, GLR, interfaces, LR

class TestGLR0(unittest.TestCase):
	
	def setUp(self):
		print(self._testMethodName)
		self.cfg = context_free.ContextFreeGrammar()
		self.cfg.start.append('S')
		self.good = []
		self.bad = []
		self.pathological = False
	def tearDown(self):
		try: self.cfg.validate()
		except context_free.Fault: assert self.pathological, "Grammar %r should have validated."%self._testMethodName
		else:
			assert not self.pathological, "Grammar %r should not have validated."%self._testMethodName
			glr0 = GLR.lr0_construction(self.cfg)
			glalr = GLR.lalr_construction(self.cfg)
			glr1 = GLR.canonical_lr1(self.cfg)
			for sentence in self.good:
				with self.subTest(sentence=sentence):
					for hfa in [glr0, glalr, glr1]:
						assert hfa.trial_parse(sentence)
			for sentence in self.bad:
				with self.subTest(sentence=sentence):
					for hfa in [glr0, glalr, glr1]:
						try: hfa.trial_parse(sentence)
						except interfaces.GeneralizedParseError: pass
						else: assert False, "%r should not be accepted."%sentence

	def r(self, lhs, rhs:str):
		rhs = rhs.split()
		self.cfg.rule(lhs.strip(), rhs, None if len(rhs)==1 else len(self.cfg.rules), None)

	def R(self, text):
		lhs, rest = text.split(':')
		for rhs in rest.split('|'): self.r(lhs, rhs)
	
	def RR(self, rules:str):
		for text in rules.splitlines():
			text = text.strip()
			if text: self.R(text)
	
	def test_00_non_lalr(self):
		""" This grammar is LR1, but not LALR. """
		self.RR("""
		S:a X d | a Y e | b X e | b Y d
		X:c
		Y:c
		""")
		self.good = ['acd', 'ace', 'bcd', 'bce']
	
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
	
	def test_05_pathology_boundless_epsilon(self):
		"""
		This shows the other fly in the trial_parse ointment: a symbol that produces
		unbounded repetition of epsilon creates another kind of infinite loop.
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
		print(GLR.lr0_construction(self.cfg).graph[0].shift)
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
		""" Epsilon left-recursion in first position is normal. Here S may be epsilon, and is left-recursive. """
		self.R('S: E | S x')
		self.R('E: | y')
		self.good = ['', 'xxx', 'y', 'yxxx']
		
	def test_09_pathology_boundless_epsilon_type_two(self):
		""" The Epsilon Loop Detector can be a tad tricky to get right... """
		self.R('S: E | S x')
		self.R('E: | y | E S')
		self.pathological = True
