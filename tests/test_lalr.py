import unittest

from boozetools.parsing.context_free import Rule, ContextFreeGrammar
from boozetools.parsing.lalr import lalr_construction

def lalr_complete() -> ContextFreeGrammar:
	# Frank DeRemer and Thomas Pennello give an LR0 graph for a grammar that is LALR, but not NQLALR.
	# "Efficient Computation of LALR(1) Look-Ahead Sets"
	# ACM Transactions on Programming Languages and Systems, Vol. 4, No. 4 (October 1982), pp. 615–649.
	# (The image in on the 18th page of the PDF.)   https://dl.acm.org/doi/pdf/10.1145/69622.357187

	# The lalr construction on this grammar should have no inadequacies.
	cfg = ContextFreeGrammar()
	cfg.start.append("S")
	for lhs, rhs in [
		("S", "agd"),
		("S", "aAc"),
		("S", "bAd"),
		("S", "bgc"),
		("A", "B"),
		("B", "g"),
	]: cfg.add_rule(Rule(lhs, tuple(rhs), None, 0, None))
	cfg.validate()
	return cfg

class MyTestCase(unittest.TestCase):
	
	def test_lalr_is_quite_lalr(self):
		hfa = lalr_construction(lalr_complete())
		assert not hfa.has_shift_reduce_conflict()


if __name__ == '__main__':
	unittest.main()
