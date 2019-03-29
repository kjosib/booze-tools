""" Small is beautiful. These algorithms need no introduction. """

import operator

def allocate(a_list:list, item):
	""" Too frequent an idiom not to abbreviate. """
	idx = len(a_list)
	a_list.append(item)
	return idx

def transitive_closure(roots, successors) -> set:
	""" Transitive closure is a simple unordered graph exploration. """
	black = set()
	grey = set(roots)
	while grey:
		k = grey.pop()
		if k not in black:
			black.add(k)
			them = successors(k)
			if them is not None: grey.update(them)
	return black

class BreadthFirstTraversal:
	""" This object also accumulates and exposes data about the traversal path. """
	def __init__(self):
		self.current, self.traversal, self.catalog, self.earliest_predecessor, self.breadcrumbs = None, [], {}, [], []
	def execute(self, visit):
		""" visit(key, lookup) should call self.lookup(successor_key, breadcrumb), which returns an integer. """
		for self.current, key in enumerate(self.traversal): visit(key)
		self.current = None
	def lookup(self, key, *, breadcrumb=None) -> int:
		if key not in self.catalog:
			self.catalog[key] = allocate(self.traversal, key)
			self.earliest_predecessor.append(self.current)
			self.breadcrumbs.append(breadcrumb)
		return self.catalog[key]
	def depth_list(self) -> list:
		result = []
		for p in self.earliest_predecessor: result.append(0 if p is None else 1+result[p])
		return result

class EquivalenceClassifier:
	def __init__(self):
		self.catalog = {}
		self.exemplars = []
	def classify(self, key):
		if key not in self.catalog:
			self.catalog[key] = allocate(self.exemplars, key)
		return self.catalog[key]

def hamming_distance(a, b):
	""" Compute the number of places in two (equal-length) sequences with unequal corresponding elements. """
	assert len(a) == len(b)
	return sum(map(operator.ne, a, b))
