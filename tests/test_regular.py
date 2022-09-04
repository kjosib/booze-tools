import unittest

from boozetools.scanning import finite, regular
from boozetools.scanning.engine import IterableScanner
from boozetools.scanning.interface import Bindings, RuleId

class mock_bindings(Bindings):
	def on_match(self, yy, rule_id:RuleId):
		yy.token(rule_id, yy.match())

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
			tokens = list(IterableScanner('j', dfa, mock_bindings(), start=None))
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
		rcl = regular.VOCAB['literal']
		space = rcl()
		del_ = rcl()
		number = regular.VOCAB['number']
		rng = regular.VOCAB['range'](space, del_) # The ascii printing characters :)
		char = regular.VOCAB["cls"](rng)
		pair = regular.VOCAB['sequence'](char, char) # Two of them in a row
		three = number()
		four = number()
		numbers = {three:3, four:4, space:32, del_:127}
		rc = regular.RemoveCounts(numbers)
		sizer = regular.RuleAnalyzer({})
		for regex, expected_size in [
			(char, 1),
			(pair, 2),
			(regular.VOCAB['alternation'](char, char), 1),
			(regular.VOCAB['alternation'](pair, pair), 2),
			(regular.VOCAB['alternation'](char, pair), None),
			(regular.VOCAB['hook'](char), None),
			(regular.VOCAB['star'](char), None),
			(regular.VOCAB['plus'](char), None),
			(regular.VOCAB['n_times'](char, four), 4),
			(regular.VOCAB['n_times'](pair, four), 8),
			(regular.VOCAB['n_to_m'](pair, three, four), None),
		]:
			with self.subTest(regex=regex):
				self.assertEqual(sizer(rc(regex)), expected_size)

