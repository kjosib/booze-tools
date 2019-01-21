import unittest
import regular, algorithms

class PassiveScanner(algorithms.Scanner):
	def invoke(self, rule, match): return rule, match


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
		dfa = nfa.subset_construction()
		self.assertEqual([(1,'j')], list(PassiveScanner(dfa).scan('j')))
		dfa = dfa.minimize_states().minimize_alphabet()
		self.assertEqual([(1,'j')], list(PassiveScanner(dfa).scan('j')))
