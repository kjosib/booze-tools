"""
Of all the LR-style parsing methods, LR(0) is the least sophisticated and the easiest to understand.
It's also the functional foundation for all the rest, so it makes sense to start reading here.
"""

from typing import NamedTuple, Optional
from collections import defaultdict

from ..support.foundation import transitive_closure, BreadthFirstTraversal
from .context_free import ContextFreeGrammar
from .automata import HFA, LR0_State

class ParseItem(NamedTuple):
	""" It's quite handy to be able to work symbolically with parse-items. """
	
	next_symbol : Optional[str]  # None means end-of-rule.
	rule_id : Optional[int]  # None means it's a pseudo-rule for the augmented grammar
	offset : int
	read_set: set[str]

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
	parse_items : list[ParseItem]
	symbol_front : dict[str: list[int]]
	language_front : list[int]
	transparent : frozenset[int]  # Parse-item indices where all symbols after the dot are nullable.
	
	@staticmethod
	def from_grammar(grammar: ContextFreeGrammar):
		parse_item = []
		language_front = []
		transparent = set()
		symbol_front = {nonterminal: [] for nonterminal in grammar.symbol_rule_ids}
		
		def plonk(where, rhs):
			where.append(len(parse_item))
			for offset, symbol in enumerate(rhs):
				parse_item.append(ParseItem(symbol, rule_id, offset, set()))
			parse_item.append(ParseItem(None, rule_id, len(rhs), set()))
		
		for rule_id, rule in enumerate(grammar.rules):
			plonk(symbol_front[rule.lhs], rule.rhs)
		
		rule_id = None
		for language in grammar.start:
			plonk(language_front, [language])
		
		nullable = grammar.find_nullable()
		symbol_first_set = grammar.find_first()
		for index in reversed(range(len(parse_item))):
			pi = parse_item[index]
			if pi.next_symbol is None:
				transparent.add(index)
			elif pi.next_symbol in symbol_front:
				pi.read_set.update(symbol_first_set[pi.next_symbol])
				if pi.next_symbol in nullable:
					pi.read_set.update(parse_item[index + 1].read_set)
					if index + 1 in transparent:
						transparent.add(index)
			else:
				pi.read_set.add(pi.next_symbol)
		
		return ParseItemMap(parse_item, symbol_front, language_front, frozenset(transparent))


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
		def visit_parse_item(i):
			pi = parse_items[i]
			if pi.next_symbol is None:
				if pi.rule_id is not None:
					reduce.append(pi.rule_id)
			else:
				shifted_cores[pi.next_symbol].append(i + 1)
				return symbol_front.get(pi.next_symbol)
		
		shifted_cores, reduce = defaultdict(list), []
		closure = transitive_closure(core_item_set, visit_parse_item)
		
		shift = {
			symbol: bft.lookup(frozenset(item_set), breadcrumb=symbol)
			for symbol, item_set in shifted_cores.items()
		}
		graph.append(LR0_State(shift=shift, reduce=reduce, closure=closure))

	parse_items, symbol_front, language_front, transparent = pim
	
	bft = BreadthFirstTraversal()
	initial = [bft.lookup(frozenset([item_index])) for item_index in language_front]
	graph = []
	bft.execute(build_state)
	accept = [graph[qi].shift[parse_items[i].next_symbol] for i, qi in zip(language_front, initial)]
	return HFA(graph=graph, initial=initial, accept=accept, bft=bft)

