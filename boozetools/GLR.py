"""
GLR is basically the non-deterministic version of LR parsing.

As a parsing strategy, it's amenable to the use of parse tables produced by any viable LR algorithm.
The more powerful table-construction algorithms result in comparatively fewer blind alleys for
a GLR runtime to explore.

Building a deterministic parse table can be seen as first building a non-deterministic one and
then taking a further step to resolve any conflicts. That is why I'm going down this alley.

"""
import typing, collections

from . import context_free, foundation

END = '<END>' # An artificial "end-of-text" terminal-symbol.

class GLR0_State(typing.NamedTuple):
	items: set
	shift: dict
	reduce: set

class GLR0_Construction:
	"""
	This is not a method-of-CFG: that would have the wrong connotation. A grammar
	specification is like a model, and this is more like a (complicated) view.
	
	In principle you could drive a Tomita-style parser with this table and the
	grammar definition, but that is not the plan.
	"""
	__slots__ = ['graph', 'initial', 'accept']
	def __init__(self, grammar:context_free.ContextFreeGrammar):
		"""
		Basically, this is a breadth-first graph exploration/construction.
		This variety of parse automaton does not consider look-ahead.
		"""
		
		def optimize_unit_rules(step:dict, check:dict) -> dict:
			# A unit-rule is eligible to be elided (optimized-to-nothing) exactly when
			# the state reached by shifting the RHS would have no other active parse items.
			# We don't actually traverse such states, but instead redirect the corresponding
			# shift-entry, essentially running the unit-rule at table-generation time.
			
			# If performing this task while carrying look-ahead in the parse-items, it sufficient
			# that the criteria would have applied had the look-ahead not been involved.
			replace = {s: grammar.rules[r].lhs for s, r in check.items() if len(step[s]) == 1}
			shifts = {}
			for symbol in step.keys():
				proxy = symbol
				while proxy in replace: proxy = replace[proxy]
				shifts[symbol] = bft.lookup(frozenset(step[proxy]), breadcrumb=proxy)
			return shifts
		
		def build_state(core: frozenset):
			step, check, state = collections.defaultdict(set), {}, GLR0_State(items=set(), shift={}, reduce=set())
			def visit(item):
				rule_id, position = item
				if position < len(RHS[rule_id]):
					next_symbol = RHS[rule_id][position]
					step[next_symbol].add((rule_id,position+1)) # For the record,
					if rule_id in unit_rules and position == 0: check[next_symbol] = rule_id
					return symbol_front.get(next_symbol)
				else: state.reduce.add(rule_id)
			items = foundation.transitive_closure(core, visit)
			self.graph.append(GLR0_State(
				items=items,
				shift=optimize_unit_rules(step, check),
				reduce=set(r for r,p in items if p == len(RHS[r])) # The end-of-rule parse-items.
			))
		
		assert grammar.start
		##### Start by arranging most of the grammar data in a convenient form:
		RHS = [rule.rhs for rule in grammar.rules] # This soon gets augmented internal to this algorithm.
		unit_rules = set(i for i, rule in enumerate(grammar.rules) if rule.attribute is None and len(rule.rhs) == 1)
		def front(rule_ids): return frozenset([(r,0) for r in rule_ids])
		symbol_front = {symbol: front(rule_ids) for symbol, rule_ids in grammar.symbol_rule_ids.items()}
		bft = foundation.BreadthFirstTraversal()
		self.graph = []
		# Initial-state cores refer only to the "augmentation" rule -- which has no LHS in this manifestation.
		self.initial = [bft.lookup(front([foundation.allocate(RHS, [language])])) for language in grammar.start]
		bft.execute(build_state)
		self.accept = [self.graph[self.initial[language]].shift[language] for language in grammar.start]
		
