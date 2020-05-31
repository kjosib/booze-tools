"""
These bits are about classifying characters for purposes of running a finite
state machine, not for representing character classes in regular expressions.

At the moment, the only supported mechanisms are simple: Store the boundaries
between codepoint ranges with identical properties. To minimize the alphabet
is to assign equivalence classes to these ranges. A runtime, binary search
identifies the correct range, and then a list index operation identifies the
final character class.

As an aside: The present scanner table compaction method is probably not too
sensitive to the order of equivalence classes.
"""

import bisect
from ..support import pretty, interfaces


class SimpleClassifier(interfaces.Classifier):
	def __init__(self, bounds):
		self.bounds = tuple(bounds)
	def cardinality(self): return 1+len(self.bounds)
	def classify(self, codepoint:int): return bisect.bisect_right(self.bounds, codepoint)
	def display(self): pretty.print_grid([['-', *self.bounds]])

class MetaClassifier(interfaces.Classifier):
	def __init__(self, bounds, classes):
		self.bounds = tuple(bounds)
		self.classes = tuple(classes)
		assert len(self.bounds) + 1 == len(self.classes)
		assert set(self.classes) == set(range(self.cardinality()))
	def cardinality(self): return max(self.classes)+1
	def classify(self, codepoint): return self.classes[bisect.bisect_right(self.bounds, codepoint)]
	def display(self):
		bound_repr = ["'"+chr(b) if 32 < b < 127 else b for b in self.bounds]
		pretty.print_grid([('-', *bound_repr), self.classes, ])
