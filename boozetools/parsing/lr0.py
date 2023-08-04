"""
Of all the LR-style parsing methods, LR(0) is the least sophisticated and the easiest to understand.
It's also the functional foundation for all the rest, so it makes sense to start reading here.
"""

from typing import NamedTuple
from collections import defaultdict

from ..support.foundation import transitive_closure, BreadthFirstTraversal
from .context_free import ContextFreeGrammar
from .automata import HFA, LR0_State

class ParseItemMap(NamedTuple):
	"""
	The key to the whole LR genera is the notion of a parse-item (and subsets of them).
	Normally, we think of a parse-item as a pair: a rule (or its ID, or its right-hand side)
	crossed with an index into (or just past) that right-hand side. And this is well-enough.
	However, it's an ungainly structure. I propose an alternative based on sentinels,
	so that a small integer refers to a parse-item, and the next higher integer is the
	successor parse-item. We index an array (symbol_at) to find the symbol at the dot,
	or None for the end of a rule. Other mappings facilitate each step in the dance.
	
	There's a subtle idea lurking in here:
	This structure is an interesting representation of all the rules in a context-free grammar.
	With it, the fact that parse-items are also just numbers is ALMOST completely hidden.
	"""
	symbol_at : list[str]
	rule_found : dict[int, int]
	symbol_front : dict[str: list[int]]
	language_front : list[int]
	nr_rules : int
	
	@staticmethod
	def from_grammar(grammar: ContextFreeGrammar):
		
		symbol_at, rule_found, language_front = [], {}, []
		symbol_front = {N: [] for N in grammar.symbol_rule_ids}
		
		def plonk(where, rhs):
			where.append(len(symbol_at))
			symbol_at.extend(rhs)
			rule_found[len(symbol_at)] = len(rule_found)
			symbol_at.append(None)
		
		for rule in grammar.rules:
			plonk(symbol_front[rule.lhs], rule.rhs)
		
		for symbol in grammar.start:
			plonk(language_front, [symbol])
		
		return ParseItemMap(symbol_at, rule_found, symbol_front, language_front, len(grammar.rules))


def lr0_construction(pim:ParseItemMap) -> HFA[LR0_State]:
	"""
	In broad strokes, this is a subset-construction with a sophisticated means
	to identify successor-states. The keys (by which nodes are identified) are
	core-sets of LR0 parse items. (See also _prepare_parse_items.)

	Additionally, during the full-elaboration step in visiting a core, completed
	parse-items correspond to a state's `reduce` entries. We don't worry about
	look-ahead in this construction: hence the '0' in LR(0). The net result is
	a compact table generated very quickly, but with somewhat limited power.
	In practical systems, LR(0) is normally just a first step, but some few
	grammars are deterministic in LR(0).
	
	Note that the core-item sets may be found at hfa.bft.traversal.
	"""
	
	def build_state(core_item_set: frozenset):
		def visit_parse_item(item):
			next_symbol = symbol_at[item]
			if next_symbol is None:
				rule_id = rule_found[item]
				if rule_id < nr_rules:
					reduce.append(rule_id)
			else:
				shifted_cores[next_symbol].append(item + 1)
				return symbol_front.get(next_symbol)
		
		shifted_cores, reduce = defaultdict(list), []
		transitive_closure(core_item_set, visit_parse_item)
		
		shift = {
			symbol: bft.lookup(frozenset(item_set), breadcrumb=symbol)
			for symbol, item_set in shifted_cores.items()
		}
		graph.append(LR0_State(shift=shift, reduce=reduce))

	symbol_at, rule_found, symbol_front, language_front, nr_rules = pim
	
	bft = BreadthFirstTraversal()
	initial = [bft.lookup(frozenset([item])) for item in language_front]
	graph = []
	bft.execute(build_state)
	accept = [graph[qi].shift[symbol_at[item]] for item, qi in zip(language_front, initial)]
	return HFA(graph=graph, initial=initial, accept=accept, bft=bft)

