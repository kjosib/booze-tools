"""
By now we've seen two ways each to do both recognition and semantic recovery:

In module parsing.shift_reduce, the trial_parse(...) and parse(...) functions
show the linear-time approach appropriate to unambiguous parse tables -- i.e.
those which either have no CF-grammar inadequacies, or for which all such are
suitably resolved with operator-precedence/associativity declarations.

In module parsing.automata, the trial_parse(...) method of class HFA shows
a simple recognizer, whereas parsing.general.brute_force shows a simple
semantic recovery method, both suitable principally for getting our feet wet
with the issues involved in dealing with ambiguous parse tables.

It's time to do better.

In 1988, Tomita showed the world how to use a "graph-structured stack" to
avoid the exponential behaviour associated with the brute-force approach.
Tomita's original algorithm did not work properly with epsilon rules. Getting
them absolutely right is more than a bit tricky. Nozohoor-Farshi contributed
a method. I'm not 100% sure the method here is identical, but it does work.

This module contains that recognizer.

There are two things to bear in mind:

First,

Secondly, timings showed the brute-force approach to be slightly faster than
this for inputs with only mild levels of ambiguity, providing the grammars
don't have hidden left recursion (which sends the brute-force method into
an infinite loop).
"""

from typing import Dict
from ...support import interfaces


class GNode:
	# Nodes in the main portion of a graph-structured stack are simple enough.
	# You need to know what state number they are, and what their predecessor linkages are.
	# Any semantic values are associated with the linkages, not with the states themselves.
	# For this application I'm not second-guessing Python and just using dictionaries.
	state_id: int
	arcs: Dict["GNode", object]
	
	def __init__(self, state_id:int, arcs:Dict["GNode", object]):
		self.state_id, self.arcs = state_id, arcs
	
	def all_paths(self, depth: int):
		"""
		A previous version of this subroutine had potentially exponential
		behavior. It was just a naive depth-first traversal. A GSS can
		branch and merge, so a level-by-level approach seems better.
		"""
		frontier = {self}
		for _ in range(depth):
			frontier = set().union(*(n.arcs for n in frontier))
		return frontier
	
	def __repr__(self): return "<%d / %s>" % (self.state_id, ",".join(str(e.state_id) for e in self.arcs))

def gss_trial_parse(table: interfaces.ParseTable, sentence, *, language=None):
	def act_on(node: GNode, step: int):
		if step == 0: return
		elif step < 0: primary_reduction(node, -1-step)
		elif step < nr_states: shifts.append((node, step))
		else: split_stacks(node, table.get_split(step - nr_states))
	def split_stacks(node:GNode, steps):
		for s in steps: act_on(node, s)
	
	def primary_reduction(reach:GNode, rule_id:int):
		ners, fwd = books[reach]
		nonterminal_id, length, cid, view = table.get_rule(rule_id)
		if length: ners.append(rule_id)
		for prior_node in cook_paths(reach, length):
			perform_goto(prior_node, nonterminal_id)
	
	def secondary_reduction(chop:int, via:GNode, rule_id:int):
		nonterminal_id, length, cid, view = table.get_rule(rule_id)
		if length >= chop:
			for prior_node in cook_paths(via, length-chop):
				# Presumably capturing the parse tree would involve the REACH node somehow.
				perform_goto(prior_node, nonterminal_id)
	
	def perform_goto(prior_node:GNode, nonterminal_id:int):
		goto_id = table.get_goto(prior_node.state_id, nonterminal_id)
		if goto_id in arena:
			goto_node = arena[goto_id]
			if prior_node in goto_node.arcs: print('pun')  # Manage puns here.
			else:
				goto_node.arcs[prior_node] = None
				if goto_node in books: secondary.append((goto_node, prior_node))
		else:
			arena[goto_id] = GNode(goto_id, {prior_node: None})
			frontier.append(goto_id)
	
	def cook_paths(origin:GNode, depth:int):
		"""
		Why not just blindly take all paths N steps back from the origin?
		Because I want to capture certain data along the way: this data is
		only rarely useful, and only if the grammar has certain features.
		"""
		if depth == 0: yield origin
		else:
			for prior in list(origin.arcs):
				if prior in books:
					fwd = books[prior][1]
					if origin not in fwd: fwd.append(origin)
					yield from cook_paths(prior, depth-1)
				else: yield from prior.all_paths(depth-1)
	
	def drain_queues():
		shifts.clear()
		books.clear()
		frontier.extend(arena.keys())
		while frontier:
			drain_frontier()
			drain_secondary()
	
	def drain_frontier():
		while frontier:
			state_id = frontier.pop()
			node = arena[state_id]
			books[node] = ([], [])
			act_on(node, table.get_action(state_id, terminal_id))
	
	def drain_secondary():
		while secondary:
			goto_node, via = secondary.pop()
			rq, chop, ahead = [goto_node], 1, set()
			while rq:
				for node in rq:
					ners, fwd = books[node]
					for rule_id in ners: secondary_reduction(chop, via, rule_id)
					ahead.update(fwd)
				rq, chop, ahead = ahead, chop+1, set()
				
		
	
	def apply_shifts(semantic):
		arena.clear()
		for node, step in shifts:
			assert isinstance(node, GNode), type(node)
			assert isinstance(step, int), type(step)
			if step not in arena: arena[step] = GNode(step, {})
			arena[step].arcs[node] = semantic
	
	nr_states = table.get_split_offset()
	q0 = table.get_initial(language)
	arena = {q0: GNode(q0, {})}
	shifts, frontier, books, secondary = [], [], {}, []
	for symbol in sentence:
		terminal_id = table.get_translation(symbol)
		drain_queues()
		apply_shifts(None)
		if not shifts: raise interfaces.GeneralizedParseError("Parser died midway at something ungrammatical.")
	# Now deal with the end-of-input:
	terminal_id = 0
	drain_queues()
	if not shifts: raise interfaces.GeneralizedParseError("Parser recognized a viable prefix, but not a complete sentence.")
	return True


