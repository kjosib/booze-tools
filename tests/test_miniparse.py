""" A run-down of basic features, I suppose... """
import unittest
import operator
from boozetools.parsing import miniparse


class TestMiniParse(unittest.TestCase):
	def test_00_smoke_test(self):
		b = miniparse.MiniParse('S')
		b.rule('S', 'a b')(None)
		each_token = [('a','Apple'), ('b', 'Boy')]
		x = b.parse(each_token)
		self.assertEqual(x, ('Apple', 'Boy'))

	def test_01_mini_calc(self):
		b = miniparse.MiniParse('E')
		b.left(['*', '/'])
		b.left(['+', '-'])
		for rhs, agent in [
			('number', float),
			('( .E )', None),
			('.E + .E', operator.add),
			('.E - .E', operator.add),
			('.E * .E', operator.mul),
			('.E / .E', operator.mul),
		]:
			with self.subTest(rhs=rhs):
				b.rule('E', rhs)(agent)

		for expr, answer in [
			('81', 81),
			('4 + 5', 9),
			('4 + 5 * 7', 39),
			('4 * 5 + 7', 27),
		]:
			with self.subTest(expr=expr):
				each_token = [(x,None) if x in '()+-*/' else ('number', x) for x in expr.split()]
				self.assertEqual(answer, b.parse(each_token))
	
	def test_02_forgotten_action(self):
		b = miniparse.MiniParse('S')
		b.rule('S', 'a B')
		with self.assertRaises(AssertionError):
			b.rule('B', 'b c')
