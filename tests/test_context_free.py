import unittest

from boozetools.parsing.context_free import ContextFreeGrammar

class TestContextFreeGrammar(unittest.TestCase):
	def test_find_first_simple_case(self):
		sut = ContextFreeGrammar.shorthand("S", {"S":"a|b|c"})
		first = sut.find_first()
		self.assertSetEqual(first['S'], set("abc"))

if __name__ == '__main__':
	unittest.main()
