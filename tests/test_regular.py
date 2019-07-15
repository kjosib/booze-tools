import unittest

from boozetools.support import interfaces
from boozetools.scanning import regular, recognition


class MockScanRules(interfaces.ScanRules):
	def invoke(self, scan_state, action): return action, scan_state.matched_text()
	def get_trailing_context(self, rule_id: int): return None

class TestNFA(unittest.TestCase):
	def test_00_new_node(self):
		""" The IDE gets confused about nested classes. This proves it works the way I think it does. """
		nfa = regular.NFA()
		q = nfa.new_node('yellow')
		self.assertEqual(1, len(nfa.states))
		self.assertEqual(nfa.states[q].rank, 'yellow')
	def test_01_conditions(self):
		""" Calling for a condition code should create it if necessary. """
		nfa = regular.NFA()
		self.assertEqual(0, len(nfa.states))
		assert 'Blue' not in nfa.initial
		a,b = nfa.condition('Blue')
		assert 'Blue' in nfa.initial
		assert a != b
		self.assertEqual(2, len(nfa.states))
	def test_02_determinize_empty_nfa(self):
		nfa = regular.NFA()
		assert isinstance(nfa.subset_construction(), regular.DFA)
	def test_03_recognize_one_letter(self):
		nfa = regular.NFA()
		q0, q1 = nfa.condition(None)
		qf = nfa.new_node(0)
		nfa.final[qf] = 1
		nfa.link(q0, qf, [65, 91, 97, 123])
		nfa.link_epsilon(q1, q0)
		def assertion():
			tokens = list(recognition.Scanner(text='j', automaton=dfa, rules=MockScanRules(), start=None))
			self.assertEqual([(1,'j')], tokens)
		dfa = nfa.subset_construction()
		assertion()
		dfa = dfa.minimize_states().minimize_alphabet()
		assertion()

class TestAST(unittest.TestCase):
	def test_00_lengths_behave_correctly(self):
		"""
		Explains the nature of computing the a-priori length of a regular expression.
		This gets used in working out the details for trailing-context expressions.
		"""
		c = regular.CharClass([32, 128]) # The ascii printing characters :)
		two = regular.Sequence(c,c) # Two of them in a row
		assert c.length() == 1
		assert two.length() == 2
		assert regular.Alternation(c, c).length() == 1
		assert regular.Alternation(two, two).length() == 2
		assert regular.Alternation(c, two).length() is None
		assert regular.Hook(c).length() is None
		assert regular.Star(c).length() is None
		assert regular.Plus(c).length() is None
		assert regular.Counted(c, 4,4).length() == 4
		assert regular.Counted(two, 4,4).length() == 8
		assert regular.Counted(two, 3,4).length() is None
		
		
