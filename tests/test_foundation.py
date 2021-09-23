import unittest
import itertools
import boozetools.support.foundation as foundation

"""
A wheel sieve is mildly tricky.
"""

sample_primes = [
	2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97,
	101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211,
]


class ModuleTests(unittest.TestCase):
	def test_generate_primes(self):
		predicate = sample_primes[-1].__ge__
		result = list(itertools.takewhile(predicate, foundation.generate_primes()))
		self.assertEqual(sample_primes, result)


if __name__ == '__main__':
	unittest.main()
