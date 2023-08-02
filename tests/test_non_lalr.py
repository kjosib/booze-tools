import unittest

from boozetools.parsing.context_free import Rule, ContextFreeGrammar
from boozetools.parsing.lalr import lalr_construction
from boozetools.parsing.lr1 import minimal_lr1, canonical_lr1

def simpler_case() -> ContextFreeGrammar:
	""" An example from the IELR paper """
	cfg = ContextFreeGrammar()
	cfg.start.append("S")
	for lhs, rhs in [
		("S", "a X d"),
		("S", "a Y e"),
		("S", "b X e"),
		("S", "b Y d"),
		("X", "c"),
		("Y", "c"),
	]: cfg.add_rule(Rule(lhs, tuple(rhs.split()), None, 0, None))
	cfg.validate()
	return cfg

def harder_case() -> ContextFreeGrammar:
	""" The grammar from issue #45 """
	cfg = ContextFreeGrammar()
	cfg.start.append("S")
	for lhs, rhs in [
		("S", "a X a"),
		("S", "b X b"),
		("S", "a Y b"),
		("S", "b Y a"),
		("X", "c XP"),
		("Y", "c YP"),
		("XP", "c"),
		("YP", "c"),
	]: cfg.add_rule(Rule(lhs, tuple(rhs.split()), None, 0, None))
	cfg.validate()
	return cfg

CASES = [
	("simpler_case", simpler_case()),
	("harder_case", harder_case()),
]

class MyTestCase(unittest.TestCase):
	def _attempt(self, method, outcome):
		for name, case in CASES:
			with self.subTest(name):
				hfa = method(case)
				assert not hfa.has_shift_reduce_conflict()
				assert outcome == hfa.has_reduce_reduce_conflict()

	def test_lalr_gets_both_wrong(self):
		self._attempt(lalr_construction, True)

	def test_canonical_lr1_gets_both_right(self):
		self._attempt(canonical_lr1, False)

	def test_minimal_lr1_gets_both_right(self):
		self._attempt(minimal_lr1, False)

if __name__ == '__main__':
	unittest.main()
