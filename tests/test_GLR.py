import unittest

from boozetools import context_free, GLR, interfaces

class TestGLR0(unittest.TestCase):
	
	def setUp(self):
		print(self._testMethodName)
		self.cfg = context_free.ContextFreeGrammar()
		self.cfg.start.append('S')
		self.good = []
	def tearDown(self):
		glr0 = GLR.lr0_construction(self.cfg)
		glalr = GLR.lalr_construction(self.cfg)
		for sentence in self.good:
			with self.subTest(sentence=sentence):
				assert glr0.trial_parse(sentence)
				assert glalr.trial_parse(sentence)

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
		self.RR("""
		S:a X d | a Y e | b X e | b Y d
		X:c
		Y:c
		""")
		self.good = ['acd', 'ace', 'bcd', 'bce']
	
	def test_01_even_length_palindromes(self):
		""" This is a strictly non-deterministic grammar. """
		self.R("S:|a S a|b S b")
		self.good = ['aabbbbaa', 'abba', 'baab', 'abbaabba', '']
	