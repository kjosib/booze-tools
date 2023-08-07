"""
Time for a new tack.

A long LONG time ago, I built a parser generator in PHP.
It was partly based on a literal modeling of the ideas in [1],
but portions of that description were impenetrably vague.
I happened across [2] and did a full reverse-engineering job
to go from C code (with plenty of wacky pointer manipulation)
back to something conceptual, and finally understood what was going on.
So that became [3]. I stuck it on source-forge and forgot about it for years.
Eventually, I discovered Richard van Velzen had forked it,
fixed some upward compatibility issues, and put the result on GitHub.
So thank you Mr. van Velzen!

Over time, I wrote a few different LALR implementations.
Either I would misplace the source code or want to try out some new interface idea.
Each time, I tried to do the LALR generation part just a bit more nicely.
At one point, I fell into the trap known as NQLALR and a previous version of this code had that fault.
After finally (years later!) discovering my error, I set about trying to correct it.
Well, there's no easy way back. One must essentially start from scratch.

Bibliography:

1. Chapter 9 of Parsing Techniques: a Practical Guide, by Dick Grune and Ceriel Jacobs.
2. Source code to lemon.c parser generator. See [3] for one copy.
3. Source code to lime.php parser generator. https://github.com/rvanvelzen/lime

================================================================================
"""

from ..support.foundation import allocate, strongly_connected_components_by_tarjan
from .interface import END_OF_TOKENS
from .context_free import ContextFreeGrammar
from .automata import HFA, LR0_State, LookAheadState, reachable
from .lr0 import lr0_construction, ParseItemMap


def lalr_construction(grammar: ContextFreeGrammar) -> HFA[LookAheadState]:
	"""
	Building a non-deterministic LALR(1)-style table is a direct extension of the LR(0)
	construction. LR(0) tables tend to have lots of inadequate states. If we figure out
	which look-ahead tokens are relevant to which reductions, then the automaton gets a
	good deal more capable. In the limit, there is canonical LR(1) as given by Knuth.
	That's traditionally been considered impractical for all but the very smallest
	grammars. Today's workstations have the chops to handle canonical LR(1) even for
	larger grammars, but it's still a chore and, as we will see, a needless one.

	The bulk of the work involved consists of finding the follow-sets for reductions.
	I've chosen to break that work into its own function, rather than code the entire
	LALR construction as one function, for two reasons. First, it's an interesting
	algorithm in its own right. Second, that function provides almost the perfect
	inputs for exploitation later in the minimal-LR(1) construction given later.

	If we stop here, we get a table that's more efficient than LR(0) for generalized
	parsing: it will attempt many fewer dead-end reductions before look-ahead tokens
	that LALR determines not to be in the reduction's follow-set. In fact, if you
	plan to use generalized parsing, LALR is probably your best choice to generate
	the parse table. A "stronger" table means more states to track and slow the parse.
	"""
	lr0 = lr0_construction(ParseItemMap.from_grammar(grammar))
	terminal_sets, reduce_set_id = find_lalr_sets(lr0, grammar)
	def make_lalr_state(q:int, node:LR0_State) -> LookAheadState:
		reduce = {}
		for rule_id in node.reduce:
			for terminal in terminal_sets[reduce_set_id[q, rule_id]]:
				if terminal not in reduce: reduce[terminal] = [rule_id]
				else: reduce[terminal].append(rule_id) # This branch represents an R/R conflict...
				
		# At this point, `LookAheadState(node.shift, reduce)` would be a nice, potentially
		# non-deterministic HFA state incorporating information about LALR follow sets.
		# We can do better: Calling upon the "reachable" function causes the resulting
		# non-deterministic HFA to respect precedence and associativity (P&A) declarations.
		# This parallels the corresponding call in the true-LR(1) algorithm, simplifies
		# the construction of a deterministic table, does not change the deterministic
		# semantics, and may have some subtle implications for GLR semantics in the presence
		# of P&A declarations. In particular, an invasive high-precedence reduction could
		# cause trouble. I've not taken the time to work out if that's even a thing, though.
		# For now, if you want to do GLR parsing with P&A, use the minimal_lr1(...) construction.
		
		step = reachable(node.shift, reduce, grammar)
		
		# That may leave unreachable states in the HFA graph, but a later pass can remove them.
		
		return LookAheadState(step, reduce)
	
	return HFA(
		graph=[make_lalr_state(q, node) for q, node in enumerate(lr0.graph)],
		initial=lr0.initial, accept=lr0.accept, bft=lr0.bft
	)
	
def find_lalr_sets(lr0:HFA[LR0_State], grammar:ContextFreeGrammar) -> tuple[list, dict[tuple[int,int], int]]:
	"""
	This is a variant of the channel algorithm as described (colorfully and frankly not
	very clearly) in chapter 9 of Parsing Techniques: a Practical Guide, by Dick Grune
	and Ceriel Jacobs. In essence the idea is to build a directed graph by certain rules
	and then "flow" terminal symbols around the nodes in that graph until updates cease.
	You may recognize this as a fix-point over the set-union operation. It turns out we
	can do better: using Tarjan's Strongly-Connected-Components algorithm and orienting
	the edges in the correct direction, we need only ever consider each edge once.

	:returns (terminal_sets, reduce_set_id) such that:
		1. terminal_sets[state_id] is equal to the "first" set of state_id
		2. terminal_sets[reduce_set_id[state_id, rule_id]] is the set of tokens which the LALR
		   algorithm determines can trigger reduction.
	"""
	graph = lr0.graph
	terminals = grammar.apparent_terminals()
	
	# Prepare to find first-sets:
	nullable = grammar.find_nullable()
	terminal_sets = [terminals.intersection(node.shift) for node in graph]
	for q in lr0.accept:terminal_sets[q].add(END_OF_TOKENS)
	inbound = [[dst for symbol, dst in node.shift.items() if symbol in nullable] for node in graph]
	
	# Now do something about follow-sets and reduce-sets.
	
	# There is one follow-set for each nonterminal-edge in the graph.
	# There is one reduce-set for each reducing parse-item in a parse-item-core.
	# One must not confuse these two distinct ideas, lest one end up with NQ-LALR.
	nonterminals = frozenset(grammar.symbol_rule_ids)
	follow_set_id: dict[tuple[int, str], int] = {}
	reduce_set_id = {}
	for q_src, node in enumerate(graph):
		for rule_id in node.reduce:
			reduce_set_id[q_src, rule_id] = allocate(terminal_sets, set())
			inbound.append([])
		for symbol, q_dst in node.shift.items():
			if symbol in nonterminals:
				# A follow-set always contains the FIRST-set of the successor-state...
				follow_set_id[q_src, symbol] = allocate(terminal_sets, set())
				inbound.append([q_dst])
	
	# And, there is some kind of inclusion relation between them.
	prefix, suffix = prepare_rule_affixes(grammar.rules, nullable, nonterminals)
	for (q_src, lhs), src_fs_id in follow_set_id.items():
		for rule_id in grammar.symbol_rule_ids[lhs]:
			# A prefix of the RHS symbols does not "see" this follow-set:
			q_mid = lr0.traverse(q_src, prefix[rule_id])
			# Suffix symbols can "see" this follow-set, so they must be connected up:
			for symbol in suffix[rule_id]:
				inbound[follow_set_id[q_mid, symbol]].append(src_fs_id)
				q_mid = graph[q_mid].shift[symbol]
			# The reduce-set is a union of follow-sets
			inbound[reduce_set_id[q_mid, rule_id]].append(src_fs_id)
			
	# Destructive-update to perform a union closure on terminal_sets.
	for component in strongly_connected_components_by_tarjan(inbound):
		union = set()
		for k in component:
			union.update(terminal_sets[k])
			union.update(*[terminal_sets[j] for j in inbound[k]])
			terminal_sets[k] = union
	
	return terminal_sets, reduce_set_id
	
def prepare_rule_affixes(rules, epsilon, nonterminals):
	"""
	The right-hand side of each rule can be divided into two parts, prefix and suffix.
	The suffix contains all those symbols which "see" the follow-set of the corresponding
	left-hand side as it sits in the grammar graph.
	"""
	# Incidentally, it seems likely that this same treatment could simplify some of the LR(1) code.
	# I'll have to think about it.
	def divide(rhs):
		if not rhs:
			return (), ()
		prefix, suffix = list(rhs), []
		while prefix and prefix[-1] in epsilon:
			suffix.insert(0, prefix.pop())
		if prefix and prefix[-1] in nonterminals:
			suffix.insert(0, prefix.pop())
		return prefix, suffix
	return zip(*[divide(rule.rhs) for rule in rules])

