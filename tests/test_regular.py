import unittest

from boozetools.support import interfaces
from boozetools.scanning import finite, regular, recognition

def mock_scan_act(yy, rule_id): yy.token(rule_id, yy.matched_text())

mock_scan_error_listener = interfaces.ScanErrorListener()

class TestNFA(unittest.TestCase):
	def test_00_new_node(self):
		""" The IDE gets confused about nested classes. This proves it works the way I think it does. """
		nfa = finite.NFA()
		q = nfa.new_node('yellow')
		self.assertEqual(1, len(nfa.states))
		self.assertEqual(nfa.states[q].rank, 'yellow')
	def test_01_conditions(self):
		""" Calling for a condition code should create it if necessary. """
		nfa = finite.NFA()
		self.assertEqual(0, len(nfa.states))
		assert 'Blue' not in nfa.initial
		a,b = nfa.condition('Blue')
		assert 'Blue' in nfa.initial
		assert a != b
		self.assertEqual(2, len(nfa.states))
	def test_02_determinize_empty_nfa(self):
		nfa = finite.NFA()
		assert isinstance(nfa.subset_construction(), finite.DFA)
	def test_03_recognize_one_letter(self):
		nfa = finite.NFA()
		q0, q1 = nfa.condition(None)
		qf = nfa.new_node(0)
		nfa.final[qf] = 1
		nfa.link(q0, qf, [65, 91, 97, 123])
		nfa.link_epsilon(q1, q0)
		def assertion():
			tokens = list(recognition.IterableScanner(text='j', automaton=dfa, act=mock_scan_act, start=None, on_error=mock_scan_error_listener))
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
		rcl = regular.codepoint.leaf
		rbl = regular.bound.leaf
		one = regular.char_range.from_args(rcl(32), rcl(127), ) # The ascii printing characters :)
		two = regular.sequence.from_args(one, one) # Two of them in a row
		sizer = regular.Sizer({})
		for regex, expected_size in [
			(one, 1),
			(two, 2),
			(regular.alternation.from_args(one, one), 1),
			(regular.alternation.from_args(two, two), 2),
			(regular.alternation.from_args(one, two), None),
			(regular.hook.from_args(one), None),
			(regular.star.from_args(one), None),
			(regular.plus.from_args(one), None),
			(regular.counted.from_args(one, rbl(4), rbl(4)), 4),
			(regular.counted.from_args(two, rbl(4), rbl(4)), 8),
			(regular.counted.from_args(two, rbl(3), rbl(4)), None),
		]: self.assertEqual(regex.tour(sizer), expected_size)

		
