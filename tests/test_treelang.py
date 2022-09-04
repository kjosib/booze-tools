from boozetools.support.treelang import RankedAlphabet, BaseTerm
import unittest

class MyTestCase(unittest.TestCase):
	def test_constant(self):
		ra = RankedAlphabet("cat1")
		
		const = ra.symbol("a_constant")
		assert issubclass(const, BaseTerm)
		c1 = const()
		c2 = const()
		self.assertEqual(c1, c1)
		self.assertEqual(c2, c2)
		self.assertNotEqual(c1, c2)
		assert type(c1) is const
		assert type(c2) is const
		assert list(c1) == []
		self.assertEqual("<a_constant/0>", str(c1))
		
		with self.assertRaises(TypeError):
			const(c1)
		with self.assertRaises(TypeError):
			const(None)

	def test_field_access(self):
		ra = RankedAlphabet("A", "B")
		a = ra.symbol("a", x="A", y="B")
		b = ra.symbol("b", z="B")
		c = ra.symbol("c")
		ra.categorize("A", "a", "c")
		ra.categorize("B", "b", "c")
		tree = a(a(c(), b(c())), c())
		assert type(tree) is a
		assert type(tree.x) is a
		assert type(tree.x.x) is c
		assert type(tree.x.y) is b
		assert type(tree.x.y.z) is c
		assert type(tree.y) is c
		assert tree.x.x is not tree.x.y.z
		
		with self.assertRaises(TypeError):
			a(tree)
		with self.assertRaises(TypeError):
			b(tree)
		

if __name__ == '__main__':
	unittest.main()
