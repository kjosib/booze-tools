import unittest

from boozetools import context_free, GLR, interfaces

class TestGLR0(unittest.TestCase):
	@staticmethod
	def parse(hfa: GLR.GLR0_Construction, cfg: context_free.ContextFreeGrammar, sentence):
		"""
		This is intended to be a super simplistic embodiment of some idea how to make a GLR parse engine.
		It exists only for unit-testing the GLR stuff, and therefore doesn't try to build a semantic value.

		The approach taken is a lock-step parallel simulation with a list of active possible stacks in
		cactus-stack form: each entry is a cons cell consisting of a state id and prior stack. This
		approach is guaranteed to work despite exploring all possible paths through the parse.

		To adapt this algorithm to a stronger table, simply replace the two lines beginning:
			for rule_id in ...
		with something that uses foreknowledge of the lexeme that's coming after some sequence
		of reductions. One could incorporate precedence and even arbitrary predicate tests following a
		roughly similar plan: consult the predicate before entering the reduction into the "alive" list.
		"""
		
		def reduce(stack, rule_id):
			""" To perform a reduction, roll the stack to before the RHS and then shift the LHS. """
			rule = cfg.rules[rule_id]
			for i in range(len(rule.rhs)): stack = stack[1]
			return hfa.graph[stack[0]].shift[rule.lhs], stack
		
		root = (hfa.initial[0], None)
		alive = [root]
		print("Attempting to parse", sentence)
		for lexeme in sentence:
			next = []
			for stack in alive:
				state = hfa.graph[stack[0]]
				if lexeme in state.shift: next.append((state.shift[lexeme], stack))
				for rule_id in state.reduce: alive.append(reduce(stack, rule_id))
			alive = next
			if not alive: raise interfaces.ParseError("Parser died midway at something ungrammatical.")
		for stack in alive:
			if stack[0] == hfa.accept[0]: return True
			for rule_id in hfa.graph[stack[0]].reduce: alive.append(reduce(stack, rule_id))
		raise interfaces.ParseError("Parser recognized a viable prefix, but not a complete sentence.")
	
	def setUp(self):
		print(self._testMethodName)
		self.cfg = context_free.ContextFreeGrammar()
		self.cfg.start.append('S')
		self.good = []
	def tearDown(self):
		hfa = GLR.GLR0_Construction(self.cfg)
		# hfa.display(self.cfg)
		for sentence in self.good:
			with self.subTest(sentence=sentence):
				assert TestGLR0.parse(hfa, self.cfg, sentence)

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
	