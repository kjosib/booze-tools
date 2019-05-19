""" Small is beautiful. These algorithms need no introduction. """

from collections.abc import Sequence, Mapping, Iterable
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

def grade(seq:Sequence, *, descending=False) -> list:
	""" returns result such that [seq[i] for i in grade(seq)] == sorted(seq). Cribbed from APL's grade_up/down. """
	return sorted(range(len(seq)), key=seq.__getitem__, reverse=descending)

def everted(permutation:Sequence) -> list:
	""" Creates and returns an inverse permutation: like it's been turned inside-out """
	result = [None] * len(permutation)
	for i, x in enumerate(permutation): result[x] = i
	return result

def strongly_connected_components_by_tarjan(graph):
	"""
	See https://en.wikipedia.org/wiki/Tarjan%27s_strongly_connected_components_algorithm
	Returns a list of strongly-connected components in reverse topological order.
	Each component is a list of member node numbers. Deviating slightly from the wikipedia
	presentation, the low-link is local to the recursive call, eliminating one confusion.
	
	It's expected that graph[q] is the list of arcs from (or perhaps to) node q.
	"""
	def unvisited(q): return index[q] is None
	def connect(q) -> int:
		low_link = index[q] = allocate(stack, q)
		on_stack[q] = True
		for r in graph[q]:
			if unvisited(r): low_link = min(low_link, connect(r))
			elif on_stack[r]: low_link = min(low_link, index[r])
		if low_link == index[q]: # i.e. if node q is the root of an SCC:
			component = stack[low_link:]
			del stack[low_link:]
			for r in component: on_stack[r] = False
			output.append(component)
		return low_link
	def main():
		for q in range(size):
			if unvisited(q): connect(q)
	size = len(graph)
	index = [None] * size
	on_stack = [False] * size
	stack = []
	output = []
	main()
	return output
