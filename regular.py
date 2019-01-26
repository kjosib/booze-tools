""" Mechanisms for working with regular languages: finite automata and an AST class-hierarchy for regular expressions. """

import typing, bisect, operator

import interfaces
from foundation import *
import pretty, charclass


class Classifier:
	def classify(self, codepoint:int) -> int: raise NotImplementedError(type(self))
	def cardinality(self) -> int: raise NotImplementedError(type(self))
	def display(self): raise NotImplementedError(type(self))

class SimpleClassifier(Classifier):
	def __init__(self, bounds):
		self.bounds = tuple(bounds)
	def cardinality(self): return 1+len(self.bounds)
	def classify(self, codepoint:int): return bisect.bisect_right(self.bounds, codepoint)
	def display(self): pretty.print_grid([['-', *self.bounds]])

class MetaClassifier(Classifier):
	def __init__(self, bounds, classes):
		self.bounds = tuple(bounds)
		self.classes = tuple(classes)
		assert len(self.bounds) + 1 == len(self.classes)
		assert set(self.classes) == set(range(self.cardinality()))
	def cardinality(self): return max(self.classes)+1
	def classify(self, codepoint): return self.classes[bisect.bisect_right(self.bounds, codepoint)]
	def display(self):
		bound_repr = ["'"+chr(b) if 32 < b < 127 else b for b in self.bounds]
		pretty.print_grid([('-', *bound_repr), self.classes,])

class DFA(interfaces.FiniteAutomaton):
	"""  """
	def __init__(self, *, alphabet:Classifier, initial:dict, final:dict, states:list):
		self.alphabet = alphabet
		self.width = self.alphabet.cardinality()
		self.initial = initial
		self.final = final
		metric = [len(row) for row in states]
		assert all(m==self.width for m in metric), (self.width, metric)
		self.states = states
	def jam_state(self): return -1
	def append_state(self, row) -> int:
		assert len(row) == self.width, [len(row), self.width]
		return allocate(self.states, row)
	def get_condition(self, condition_name) -> tuple: return self.initial[condition_name]
	def get_next_state(self, current_state: int, codepoint: int) -> int: return self.states[current_state][self.alphabet.classify(codepoint)]
	def get_state_rule_id(self, state_id: int): return self.final.get(state_id)
	
	def display(self):
		print('Finite Automaton:')
		self.alphabet.display()
		print('Initial:', self.initial)
		head = ['*', '', ]+list(range(self.alphabet.cardinality()))
		body = [[self.final.get(i,''), i, *[s if s >= 0 else '' for s in row]] for i, row in enumerate(self.states)]
		pretty.print_grid([head]+body)
	
	def minimize_states(self) -> "DFA":
		""" Let's try Moore's Algorithm: It's easier to get right. """
		buckets = []
		P = []
		def establish_initial_partitioning():
			""" Every state goes into a partition numbered according to its finality: """
			finality = {}
			for n in range(len(self.states)):
				rule_id = self.final.get(n)
				if rule_id not in finality: finality[rule_id] = allocate(buckets, [])
				b = finality[rule_id]
				P.append(b)
				buckets[b].append(n)
			pass
		def translate(q): return (-1 if x < 0 else P[x] for x in self.states[q])
		def refine_partitions() -> bool:
			verken = False
			for b, bucket in enumerate(buckets):
				if len(bucket) < 2: continue
				exemplar = list(translate(bucket[0]))
				same, different = [], []
				for q in bucket: (same if all(map(operator.eq, exemplar, translate(q))) else different).append(q)
				if different:
					buckets[b] = same
					n = allocate(buckets, different)
					for q in different: P[q] = n
					verken = True
			return verken
		def interpretation() -> DFA:
			return DFA(
				alphabet=self.alphabet,
				initial={condition: (P[q0], P[q1]) for condition, (q0, q1) in self.initial.items()},
				final = {P[q]:rule_id for q,rule_id in self.final.items()},
				states = [list(translate(bucket[0])) for bucket in buckets],
			)
		establish_initial_partitioning()
		while refine_partitions(): pass
		return interpretation()
		
	def minimize_alphabet(self) -> "DFA":
		assert isinstance(self.alphabet, SimpleClassifier)
		ec = EquivalenceClassifier()
		classes = [ec.classify(column) for column in zip(*self.states)]
		return DFA(
			alphabet=MetaClassifier(self.alphabet.bounds, classes),
			initial=self.initial,
			final=self.final,
			states=list(zip(*ec.exemplars)),
		)
	
	def stats(self):
		Q = len(self.states)
		W = self.width
		X = sum(sum(x != -1 for x in state) for state in self.states)
		print('DFA has %d states and %d character classes, using %d cells.'%(Q, W, Q*W))
		print('%d non-error cells, or %0.2f%%'%(X, 100*X/(Q*W)))

class NFA:
	def __init__(self):
		self.states, self.initial, self.final = [], {}, {}
		self.all_bounds = {0} # There is at least an "end-of-file" marker, which is distinct from all else.

	class Edge(typing.NamedTuple):
		label: list
		target: int

	class Node(typing.NamedTuple):
		edges: list
		epsilons: set
		rank: int
	
	def new_node(self, rank) -> int: return allocate(self.states, NFA.Node(edges=[], epsilons=set(), rank=rank))
	def condition(self, name):
		if name not in self.initial: self.initial[name] = (self.new_node(0), self.new_node(0))
		return self.initial[name]
	def link(self, src :int, dst :int, label :list):
		self.states[src].edges.append(NFA.Edge(label, dst))
		self.all_bounds.update(label)
	def link_epsilon(self, src :int, dst :int): self.states[src].epsilons.add(dst)
	def subset_construction(self) -> DFA:
		all_bounds = sorted(self.all_bounds|{-1})
		dfa = DFA(alphabet=SimpleClassifier(all_bounds[1:]), initial={}, final={}, states=[])
		def close(ns, min_rank:int):
			assert all(isinstance(n, int) for n in ns)
			tc = transitive_closure(ns, lambda n :self.states[n].epsilons)
			ns = frozenset(n for n in tc if self.states[n].rank >= min_rank)
			return ns, min((self.states[n].rank for n in ns), default=0)
		def visit(key):
			ns, min_rank = key
			active, targets = [], []
			final = ns & self.final.keys()
			if final:
				min_rank = max(self.states[n].rank for n in final)
				dfa.final[len(dfa.states)] = min(self.final[n] for n in final if self.states[n].rank == min_rank)
			for n in ns:
				node = self.states[n]
				if node.rank >= min_rank:
					for e in node.edges:
						active.append(list(charclass.expand(e.label, all_bounds)))
						targets.append(e.target)
			# Now, if active[i][j], then targets[i] participates in class[j].
			delta, prior = [], None
			for column in zip(*active):
				register = [t for r,t in zip(column, targets) if r]
				if register != prior: # Save a lot of transitive closure operations...
					prior = register
					subset, subrank = close(register, min_rank)
					successor = bft.lookup((subset, subrank)) if subset else -1
				delta.append(successor)
			dfa.append_state(delta or [-1]*dfa.width)
		bft = BreadthFirstTraversal()
		def initial(q:int): return close([q], 0)
		dfa.initial = {k :(bft.lookup(initial(a)), bft.lookup(initial(b))) for k ,(a ,b) in self.initial.items()}
		bft.execute(visit)
		return dfa

class Regular:
	def encode(self, src:int, dst:int, nfa:NFA, rank): raise NotImplementedError(type(self))
	def length(self): raise NotImplementedError(type(self)) # Can't use __len__ because Python runtime demands an integer.

class CharClass(Regular):
	def __init__(self, cls:list): self.cls = cls
	def encode(self, src:int, dst:int, nfa:NFA, rank): nfa.link(src, dst, self.cls)
	def length(self): return 1

class Alternation(Regular):
	def __init__(self, a:Regular, b:Regular): self.a, self.b = a,b
	def encode(self, src:int, dst:int, nfa:NFA, rank):
		self.a.encode(src, dst, nfa, rank)
		self.b.encode(src, dst, nfa, rank)
	def length(self):
		a, b = self.a.length(), self.b.length()
		if a==b: return a

class Sequence(Regular):
	def __init__(self, a:Regular, b:Regular): self.a, self.b = a,b
	def encode(self, src:int, dst:int, nfa:NFA, rank):
		midpoint = nfa.new_node(rank)
		self.a.encode(src, midpoint, nfa, rank)
		self.b.encode(midpoint, dst, nfa, rank)
	def length(self):
		a,b = self.a.length(), self.b.length()
		if None not in (a,b): return a+b

class Inflection(Regular):
	def __init__(self, sub:Regular): self.sub = sub
	def length(self): return None

class Star(Inflection):
	def encode(self, src:int, dst:int, nfa:NFA, rank):
		loop = nfa.new_node(rank)
		self.sub.encode(loop, loop, nfa, rank)
		nfa.link_epsilon(src, loop)
		nfa.link_epsilon(loop, dst)

class Hook(Inflection):
	def encode(self, src:int, dst:int, nfa:NFA, rank):
		self.sub.encode(src, dst, nfa, rank)
		nfa.link_epsilon(src, dst)

class Plus(Inflection):
	def encode(self, src:int, dst:int, nfa:NFA, rank):
		before, after = nfa.new_node(rank), nfa.new_node(rank)
		self.sub.encode(before, after, nfa, rank)
		nfa.link_epsilon(src, before)
		nfa.link_epsilon(after, before)
		nfa.link_epsilon(after, dst)

class Counted(Regular):
	""" Just too handy not to provide. """
	def __init__(self, sub: Regular, m:int, n):
		assert isinstance(sub, Regular)
		assert isinstance(m, int)
		assert isinstance(n, int) or n is None
		self.sub, self.m, self.n = sub, m, n
	def encode(self, src:int, dst:int, nfa:NFA, rank):
		p1 = nfa.new_node(rank)
		nfa.link_epsilon(src, p1)
		for i in range(self.m):
			p2 = nfa.new_node(rank)
			self.sub.encode(p1, p2, nfa, rank)
			p1 = p2
		nfa.link_epsilon(p1, dst)
		if self.n is None:
			self.sub.encode(p1, p1, nfa,rank)
		else:
			for i in range(self.n - self.m):
				p2 = nfa.new_node(rank)
				self.sub.encode(p1, p2, nfa, rank)
				nfa.link_epsilon(p2, dst)
				p1 = p2
	def length(self):
		if self.m == self.n:
			x = self.sub.length()
			if x is not None: return x * self.m

		
