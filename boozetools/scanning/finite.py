"""
Algorithms and data structures for constructing, determinizing, and minimizing
finite state machines. These make no attempt at clever internal storage: they
follow the maxim "When in doubt, use brute force."
"""

import operator
from typing import NamedTuple
from ..support import foundation, pretty
from ..scanning import charclass, charset
from .interface import Classifier, FiniteAutomaton, State, CodePoint, RuleId

class DFA(FiniteAutomaton):

	def __init__(self, *, alphabet: Classifier, initial:dict, final:dict, states:list):
		self.alphabet = alphabet
		self.width = self.alphabet.cardinality()
		self.initial = initial
		self.final = final
		metric = [len(row) for row in states]
		assert all(m==self.width for m in metric), (self.width, metric)
		self.states = states
		
	def jam_state(self): return -1
	def condition(self, condition_name) -> tuple: return self.initial[condition_name]
	def transition(self, state: State, codepoint: CodePoint) -> State: return self.states[state][self.alphabet.classify(codepoint)]
	def accept(self, state: State) -> RuleId: return self.final.get(state)
	
	def append_state(self, row) -> int:
		assert len(row) == self.width, [len(row), self.width]
		return foundation.allocate(self.states, row)
	
	def display(self):
		print('Finite Automaton:')
		self.alphabet.display()
		print('Initial:', self.initial)
		head = ['*', '', ]+list(range(self.alphabet.cardinality()))
		body = [[self.final.get(i,''), i, *[s if s >= 0 else '' for s in row]] for i, row in enumerate(self.states)]
		pretty.print_grid([head] + body)
	
	def minimize_states(self) -> "DFA":
		""" Let's try Moore's Algorithm: It's easier to get right. """
		buckets = []
		partition_id_of_state = []
		def establish_initial_partitioning():
			""" Every state goes into a partition numbered according to its finality: """
			finality = {}
			for n in range(len(self.states)):
				rule_id = self.final.get(n)
				if rule_id not in finality: finality[rule_id] = foundation.allocate(buckets, [])
				b = finality[rule_id]
				partition_id_of_state.append(b)
				buckets[b].append(n)
			pass
		def translate(q) -> tuple: return tuple(-1 if x < 0 else partition_id_of_state[x] for x in self.states[q])
		def refine_partitions() -> bool:
			splitting_happened = False
			for b, bucket in enumerate(buckets):
				if len(bucket) < 2: continue
				exemplar = translate(bucket[0])
				same, different = [], []
				for q in bucket: (same if all(map(operator.eq, exemplar, translate(q))) else different).append(q)
				if different:
					buckets[b] = same
					n = foundation.allocate(buckets, different)
					for q in different: partition_id_of_state[q] = n
					splitting_happened = True
			return splitting_happened
		def interpretation() -> DFA:
			return DFA(
				alphabet=self.alphabet,
				initial={condition: (partition_id_of_state[q0], partition_id_of_state[q1]) for condition, (q0, q1) in self.initial.items()},
				final = {partition_id_of_state[q]:rule_id for q,rule_id in self.final.items()},
				states = [translate(bucket[0]) for bucket in buckets],
			)
		establish_initial_partitioning()
		while refine_partitions(): pass
		return interpretation()
		
	def minimize_alphabet(self) -> "DFA":
		assert isinstance(self.alphabet, charclass.SimpleClassifier)
		ec = foundation.EquivalenceClassifier()
		classes = [ec.classify(column) for column in zip(*self.states)]
		return DFA(
			alphabet=charclass.MetaClassifier(self.alphabet.bounds, classes),
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
	
	def make_csv(self, pathstem):
		pretty.write_csv_grid(pathstem + '.dfa.csv', [
			[q, self.final.get(q), '', *row]
			for q, row in enumerate(self.states)
		])
		pass

class NFA:
	def __init__(self):
		self.states, self.initial, self.final = [], {}, {}
		self.all_bounds = {0} # There is at least an "end-of-file" marker, which is distinct from all else.

	class Edge(NamedTuple):
		label: list
		target: int

	class Node(NamedTuple):
		edges: list
		epsilons: set
		rank: int
	
	def new_node(self, rank) -> int:
		return foundation.allocate(self.states, NFA.Node(edges=[], epsilons=set(), rank=rank))
	def condition(self, name):
		if name not in self.initial: self.initial[name] = (self.new_node(0), self.new_node(0))
		return self.initial[name]
	def link(self, src :int, dst :int, label :list):
		self.states[src].edges.append(NFA.Edge(label, dst))
		self.all_bounds.update(label)
	def link_epsilon(self, src :int, dst :int): self.states[src].epsilons.add(dst)
	def link_condition(self, main_condition, included_condition):
		"""
		Precondition: Both conditions exist, and are known to the NFA `self`.
		Postcondition: It is as if all the rules in `included_condition` are also defined in `main_condition`,
		and in the same relative order.
		"""
		for src, dst in zip(self.initial[main_condition], self.initial[included_condition]):
			self.link_epsilon(src, dst)
	def subset_construction(self) -> DFA:
		"""
		The standard plan to convert an NFA to a DFA, in plain English, is to consider
		that a deterministic state represents a particular and distinct subset of NFA states.
		That general plan is embodied by the interplay between the generic BreadthFirstTraversal(...)
		and `visit(key)`: the "key" is composed principally of a `frozenset` of NFA state ID numbers.
		
		This module also supports "rule ranks" -- about which more is written elsewhere. To implement
		the concept, an extra bit of data rides along with the subset: specifically, a rank number.
		"""
		def close(ns, min_rank:int):
			assert all(isinstance(n, int) for n in ns)
			tc = foundation.transitive_closure(ns, lambda n :self.states[n].epsilons)
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
						active.append(list(charset.expand(e.label, all_bounds)))
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
		# Main routine:
		all_bounds = sorted(self.all_bounds|{-1})
		dfa = DFA(alphabet=charclass.SimpleClassifier(all_bounds[1:]), initial={}, final={}, states=[])
		bft = foundation.BreadthFirstTraversal()
		def initial(q:int): return close([q], 0)
		dfa.initial = {k :(bft.lookup(initial(a)), bft.lookup(initial(b))) for k, (a, b) in self.initial.items()}
		bft.execute(visit)
		return dfa
