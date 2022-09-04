""" Small is beautiful. These algorithms need no introduction. """

from collections.abc import Sequence
from collections import deque
import operator

def allocate(a_list:list, item):
	"""
	Append an item to a list, and return the new item's index in that list.
	Too frequent an idiom not to abbreviate.
	"""
	idx = len(a_list)
	a_list.append(item)
	return idx

def transitive_closure(roots, successors) -> set:
	"""
	Transitive closure is a simple application of graph search.
	(This particular implementation is breadth-first.)
	
	This function does not expect any particular data structure.
	Rather, it takes the graph's outbound-edge relation as a callable parameter.
	It requires:
		``roots`` is an iterable of nodes;
		each node is hashable;
		and ``successors(aNode)`` returns an iterable of nodes.
	"""
	closure = set(roots)
	queue = deque(closure)
	while queue:
		more = successors(queue.popleft())
		if more is not None:
			for item in more:
				if item not in closure:
					closure.add(item)
					queue.append(item)
	return closure

class BreadthFirstTraversal:
	"""
	This object supports more general breadth-first graph traversal (and discovery) algorithms.
	It also accumulates and exposes data about the traversal path, which is usually useful later.
	
	Initialize the traversal's roots by calling .lookup(rootKey) as many times as necessary,
	then perform the traversal by calling .execute(visit). The "visit" parameter must be callable:
	it will be called once with each key this object encounters in a .lookup(...) call.
	In the end, the fields will have these meanings:
	
	current: the index of whichever key is currently being visited; ``None`` before and after processing.
	traversal: the list of keys in the order seen by .lookup(...)
	catalog: the mapping from key to traversal-index
	earliest_predecessor: reverse links pointing along a shortest/first-encountered path towards the root.
	breadcrumbs: Assuming edge-labels are provided with .lookup(key, breadcrumb=label), these are those labels.
	
	"""
	def __init__(self):
		self.current, self.traversal, self.catalog, self.earliest_predecessor, self.breadcrumbs = None, [], {}, [], []
	def execute(self, visit):
		""" visit(key) should call .lookup(successor_key, breadcrumb), which returns an integer. """
		for self.current, key in enumerate(self.traversal):
			visit(key)
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
	def shortest_path_to(self, index:int) -> list:
		""" Return a minimal list of states traversed, from a root to the given node index, in normal order. """
		path = []
		while index is not None:
			path.append(index)
			index = self.earliest_predecessor[index]
		path.reverse()
		return path

class EquivalenceClassifier:
	"""
	Conceivably you might want to normalize the keys,
	but you can do that in advance of the .classify call,
	so there is no point folding it into this object.
	"""
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
	"""
	Returns an index permutation, such that:
		[seq[i] for i in grade(seq)] == sorted(seq)
	Cribbed from APL's grade_up/grade_down primitives.
	"""
	return sorted(range(len(seq)), key=seq.__getitem__, reverse=descending)

def everted(permutation:Sequence) -> list:
	""" Creates and returns the inverse of a given permutation: like it's been turned inside-out """
	result = [None] * len(permutation)
	for i, x in enumerate(permutation): result[x] = i
	return result

def collation(seq:Sequence, *, descending=False):
	""" The inverse of `grade`: Tells you how a sorted sequence was permuted to get here. """
	return everted(grade(seq, descending=descending))

def strongly_connected_components_by_tarjan(graph):
	"""
	See https://en.wikipedia.org/wiki/Tarjan%27s_strongly_connected_components_algorithm
	Returns a list of strongly-connected components in reverse topological order.
	Each component is a list of member node numbers. Deviating slightly from the wikipedia
	presentation, the low-link is local to the recursive call, eliminating one confusion.
	
	It's expected that graph[q] is the list of arcs from (or perhaps to) node q.
	The linear-time bound assumes all nodes are numbered from 0..last. An isomorphism
	for hashable node keys is provided below.
	"""
	def unvisited(q): return index[q] is None
	def connect(q) -> int:
		low_link = index[q] = allocate(stack, q)
		on_stack[q] = True
		for r in graph[q]:
			if unvisited(r): low_link = min(low_link, connect(r))
			elif on_stack[r]: low_link = min(low_link, index[r])
		if low_link == index[q]:  # i.e. if node q is the root of an SCC:
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

def strongly_connected_components_hashable(graph:dict):
	"""
	Adaptation of Tarjan's SCC algorithm for more kinds of graph node labels than strictly integers.
	The input graph is represented as a dictionary, with values being lists of keys.
	The result will again be lists of keys.
	"""
	table = list(graph.keys())
	index = {key:i for i,key in enumerate(table)}
	prime = [
		[index[arc] for arc in node if arc in index]
		for node in graph.values()
	]
	return [[table[q] for q in component] for component in strongly_connected_components_by_tarjan(prime)]


class Visitor:
	"""
	Visitor-pattern in Python, with fall-back to superclasses along the MRO.

	Actual visitation-algorithms will inherit from Visitor and then each
	`visit_Foo` method must call `self.visit(host.bar)` as appropriate. This
	is so that your visitation-algorithm is in control of which bits of an
	object-graph that it actually visits, and in what order.
	
	Does this really belong here? Perhaps it lacks the gravitas of classical
	algorithms, but it's certainly generic enough and useful in structure-
	directed applications.
	"""
	
	def visit(self, host, *args, **kwargs):
		method_name = 'visit_' + host.__class__.__name__
		try: method = getattr(self, method_name)
		except AttributeError:
			# Searching the MRO incurs whatever cost there is to set up an iterator.
			# NB: Multiple-inheritance with NamedTuple seems to confuse the __mro__.
			for cls in host.__class__.__mro__:
				fallback = 'visit_' + cls.__name__
				if hasattr(self, fallback):
					method = getattr(self, fallback)
					break
			else: raise
		return method(host, *args, **kwargs)

def generate_primes():
	"""
	Generate and yield an unbounded ordered sequence of prime numbers.
	* If you want the first N primes, compose with itertools.islice(..., N).
	* If you want primes less than N, compose with itertools.dropWhile(N.__gt__, ...)

	Various algorithms rely on having a convenient source of prime numbers.
	Although generating primes isn't all that expensive an activity,
	compute-by-need means thinking about thread-safety, so design with care.
	
	There are faster algorithms for large primes, but this wheel-sieve
	(see https://en.wikipedia.org/wiki/Wheel_factorization) is more than
	adequate for general use outside of cryptography and heavy number-theory.
	"""
	yield from (2, 3, 5)  # The basis of the wheel
	
	# Generate a wheel via simple trial division of odd numbers (themselves a sort of minimal wheel):
	# The wheel consists of the non-basis primes less than `2+circumference`.
	# Hard-coded trial division of odd numbers is sufficient to find it:
	offset = circumference = 2 * 3 * 5  # The product of the basis-primes.
	wheel = [n for n in range(7, 2 + circumference, 2) if n % 3 and n % 5]
	yield from wheel
	
	# Henceforth, candidate primes are of the form:
	#     wheel[i] + k * circumference
	# where k ranges from 1..infinity.
	primes, trials, next_trial, next_square = list(wheel), [], 7, 49
	while True:
		for spoke in wheel:
			candidate = spoke + offset
			if candidate >= next_square:
				trials.append(next_trial)
				next_trial = primes[len(trials)]
				next_square = next_trial * next_trial
			if all(candidate % p for p in trials):
				yield candidate
				primes.append(candidate)
		offset += circumference

