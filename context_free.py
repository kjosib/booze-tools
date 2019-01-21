import typing, collections
from foundation import *
import interfaces
import pretty

LEFT, RIGHT, NONASSOC = object(), object(), object()



class ContextFreeGrammar:
	class Fault(ValueError): pass
	class DuplicateRule(Fault): pass
	class UnreachableSymbols(Fault): pass
	class NonproductiveSymbols(Fault): pass
	class Rule(typing.NamedTuple):
		lhs: str
		rhs: tuple
		attribute: object
		prec_sym: typing.Optional[str]
	
	def __init__(self):
		self.rules, self.token_precedence, self.level_assoc = [], {}, []
		self.symbols = set()
		self.symbol_rule_ids = {}
	def display(self):
		head = ['', 'Symbol', 'Produces', 'Using']
		body = [[i, rule.lhs, rule.rhs, rule.attribute] for i,rule in enumerate(self.rules)]
		pretty.print_grid([head]+body)

	def rule(self, lhs, rhs, attribute, prec_sym=None):
		assert lhs not in self.token_precedence
		assert attribute is not None or len(rhs) == 1, 'There are no shortcuts at this layer.'
		if prec_sym is not None: assert prec_sym in self.token_precedence
		self.symbols.add(lhs)
		self.symbols.update(rhs)
		if lhs not in self.symbol_rule_ids: self.symbol_rule_ids[lhs] = []
		sri = self.symbol_rule_ids[lhs]
		if any(self.rules[rule_id].rhs == rhs for rule_id in sri): raise ContextFreeGrammar.DuplicateRule(lhs, rhs)
		sri.append(allocate(self.rules, ContextFreeGrammar.Rule(lhs, rhs, attribute, prec_sym)))
	
	def validate(self, start:(str, list, tuple)):
		if isinstance(start, str): start = [start]
		produces = collections.defaultdict(set)  # nt -> set[t]
		produced_by = collections.defaultdict(set)
		for rule in self.rules:
			assert rule.attribute is not None or len(rule.rhs) == 1
			produces[rule.lhs].update(rule.rhs)
			for symbol in rule.rhs: produced_by[symbol].add(rule.lhs)
		unreachable = self.symbols - transitive_closure(start, produces.get)
		if unreachable: raise ContextFreeGrammar.UnreachableSymbols(unreachable)
		nonterminals = set(produces.keys())
		nonproductive = self.symbols - transitive_closure(self.symbols-nonterminals, produced_by.get)
		if nonproductive: raise ContextFreeGrammar.NonproductiveSymbols(nonproductive)
		pass
	
	def assoc(self, direction, symbols):
		assert direction in (LEFT, NONASSOC, RIGHT)
		assert symbols
		level = allocate(self.level_assoc, direction)
		for symbol in symbols:
			assert symbol not in self.symbol_rule_ids
			self.token_precedence[symbol] = level
			
	def decide_shift_reduce(self, symbol, rule_id):
		try: sp = self.token_precedence[symbol]
		except KeyError: return None
		rule = self.rules[rule_id]
		prec_sym = rule.prec_sym or self.infer_prec_sym(rule.rhs)
		if not prec_sym: return None
		rp = self.token_precedence[prec_sym]
		if rp < sp: return LEFT
		# NB: Bison and Lemon both treat later declarations as higher-precedence,
		# which is unintuitive, in that you perform higher-precedence operations
		# first so it makes sense to list them first. Please excuse my dear aunt Sally!
		if rp == sp: return self.level_assoc[rp]
		return RIGHT
	
	def infer_prec_sym(self, rhs): # The first RHS member assigned a precedence level, which is generally the only...
		for symbol in rhs:
			if symbol in self.token_precedence: return symbol

	def lalr_construction(self, start: (str, list, tuple), *, strict:bool=False):
		class State(typing.NamedTuple):
			shifts: dict
			complete: set  # rule_id
			follow: dict  # rule_id -> set_id
		
		##### Start by arranging most of the grammar data in a convenient form:
		if isinstance(start, str): start = [start]
		assert start
		RHS, unit_rules = [], set()
		for rule_id, rule in enumerate(self.rules):
			RHS.append(rule.rhs)
			if rule.attribute is None and len(rule.rhs) == 1: unit_rules.add(rule_id)
		
		end = '<END>'
		terminals = [end] + sorted(self.symbols - self.symbol_rule_ids.keys())
		translate = {symbol:i for i,symbol in enumerate(terminals)}
		nonterminals = sorted(self.symbol_rule_ids.keys())
		
		##### The LR(0) construction:
		def front(rule_ids): return frozenset([(r,0) for r in rule_ids])
		symbol_front = {symbol: front(rule_ids) for symbol, rule_ids in self.symbol_rule_ids.items()}
		def build_state(core: frozenset):
			step, check, complete = collections.defaultdict(set), {}, set()
			def visit_item(item):
				r, p = item
				if p < len(RHS[r]):
					s = RHS[r][p]
					step[s].add((r,p+1)) # For the record,
					if r in unit_rules and p == 0: check[s] = r
					return symbol_front.get(s)
				else: complete.add(r)
			transitive_closure(core, visit_item)
			replace = {s:self.rules[r].lhs for s, r in check.items() if len(step[s]) == 1}
			shifts = {}
			for symbol in step.keys():
				proxy = symbol
				while proxy in replace: proxy = replace[proxy]
				shifts[symbol] = bft.lookup(frozenset(step[proxy]), breadcrumb=proxy)
			hfa.append(State(shifts=shifts, complete=complete, follow={}))
		##### Construct first and follow sets:
		def trace(q, rhs):
			for s in rhs: q = hfa[q].shifts[s]
			return q
		def construct_first_and_follow_sets():
			def link(*, src:int, dst:int): flows[src].append(dst)
			for q, state in enumerate(hfa):
				assert isinstance(state, State)
				for symbol, successor in state.shifts.items():
					if symbol in translate: token_sets[q].add(symbol)
					else:
						follow = allocate(token_sets, set())
						link(src=successor, dst=follow)
						for rule_id in self.symbol_rule_ids[symbol]:
							q_prime = trace(q, RHS[rule_id])
							prime = hfa[q_prime]
							if rule_id in prime.follow: link(src=follow, dst=prime.follow[rule_id])
							elif rule_id in prime.complete: prime.follow[rule_id] = follow
							else: pass # This was an elided unit rule.
				for rule_id in state.complete:
					if rule_id < len(self.rules):
						link(src=state.follow[rule_id], dst=q)
			for rule_id, language in enumerate(start, len(self.rules)):
				q = initial[language]
				final = hfa[q].shifts[language]
				token_sets[final].add(end)

				
		def propagate_tokens():
			work = set(i for i,ts in enumerate(token_sets) if ts)
			while work:
				src = work.pop()
				for dst in flows[src]:
					spill = token_sets[src] - token_sets[dst]
					if spill:
						token_sets[dst].update(spill)
						work.add(dst)
		
		hfa = []
		bft = BreadthFirstTraversal()
		initial = {language: bft.lookup(front([allocate(RHS, [language])])) for language in start}
		bft.execute(build_state)
		
		token_sets = [set() for _ in range(len(hfa))]
		flows = collections.defaultdict(list)
		construct_first_and_follow_sets()
		propagate_tokens()
		##### Determinize the result:
		def consider(q, lookahead, options):
			trail, cursor = [], q
			while True:
				crumb = bft.breadcrumbs[cursor]
				if crumb:
					trail.append(crumb)
					cursor = bft.earliest_predecessor[cursor]
				else: break
			print('==============\nIn language %r, consider:' % start[cursor])
			print('\t'+' '.join(reversed(trail)),'\u25cf',lookahead)
			for x in options:
				if x > 0:
					print("Do we shift into:")
					left_parts, right_parts = [], []
					for r,p in bft.traversal[x]:
						rhs = self.rules[r].rhs
						left_parts.append(' '.join(rhs[:p]))
						right_parts.append(' '.join(rhs[p:]))
					align = max(map(len, left_parts)) + 10
					for l, r in zip(left_parts, right_parts): print(' '*(align-len(l))+l+'  \u25cf  '+r)
				else:
					rule = self.rules[-x - 1]
					print("Do we reduce:  %s -> %s"%(rule.lhs, ' '.join(rule.rhs)))
		
		def determinize():
			pure = True
			conflict =  collections.defaultdict(set)
			for q, state in enumerate(hfa):
				goto.append([state.shifts.get(s, 0) for s in nonterminals])
				action_row = [state.shifts.get(s, 0) for s in terminals]
				conflict.clear()
				for rule_id, follow_set_id in state.follow.items():
					reduce = -1-rule_id
					for symbol in token_sets[follow_set_id]:
						idx = translate[symbol]
						prior = action_row[idx]
						if prior == 0: action_row[idx] = reduce
						elif prior < 0:
							# TODO: if both rules have precedence and they differ, you can resolve
							# TODO: without reporting a conflict. But when does that ever happen?
							conflict[symbol].update([prior, reduce])
							action_row[idx] = max(prior, reduce)
						elif prior > 0:
							decision = self.decide_shift_reduce(symbol, rule_id)
							if decision == LEFT: action_row[idx] = reduce
							elif decision == RIGHT: pass
							elif decision == NONASSOC: essential_errors.add((q, idx))
							else: conflict[symbol].update([prior, reduce])
				if conflict:
					pure = False
					for symbol, options in conflict.items(): consider(q, symbol, options)
				action.append(action_row)
			for q,t in essential_errors: action[q][t] = 0
			if strict: assert pure
			for language, q in initial.items():
				final = hfa[q].shifts[language]
				assert action[final][0] == 0, hfa[final]
				action[final][0] = final

		action, goto, essential_errors = [], [], set()
		determinize()
		return DragonBookTable(
			initial = initial,
			action=action,
			goto=goto,
			essential_errors=essential_errors,
			rules=self.rules,
			terminals=terminals,
			nonterminals=nonterminals,
			breadcrumbs=bft.breadcrumbs,
		)


		
class DragonBookTable(interfaces.ParserTables):
	"""
	This is the classic textbook view of a set of parse tables. It's also a reasonably quick implementation
	if you have a modern amount of RAM in your machine. In days of old, it would be necessary to compress
	the parse tables. Today, that's still not such a bad idea.
	"""
	def __init__(self, *, initial:dict, action:list, goto:list, essential_errors:set, rules:list, terminals:list, nonterminals:list, breadcrumbs:list):
		self.initial = initial
		self.action = action
		self.go = goto
		self.essential_errors = essential_errors
		self.translate = {symbol: i for i, symbol in enumerate(terminals)}
		self.get_translation = self.translate.__getitem__
		nontranslate = {symbol: i for i, symbol in enumerate(nonterminals)}
		self.terminals, self.nonterminals = terminals, nonterminals
		self.breadcrumbs = breadcrumbs
		
		self.rule = [(nontranslate[rule.lhs], len(rule.rhs), rule.attribute) for rule in rules].__getitem__
		
		interactive = []
		for row in action:
			k = set(row)
			k.discard(0)
			if len(k) == 1: interactive.append(min(k.pop(), 0))
			else: interactive.append(0)
		for q,t in essential_errors: interactive[q] = False
		self.interactive_step = self.interactive_rule_for = interactive.__getitem__
	
	def get_translation(self, symbol) -> int: return self.translate[symbol] # This gets replaced ...
	
	def step(self, state_id, terminal_id) -> int: return self.action[state_id][terminal_id]
	
	def goto(self, state_id, nonterminal_id) -> int: return self.go[state_id][nonterminal_id]
	
	def get_initial(self, language) -> int: return 0 if language is None else self.initial[language]
	
	def get_breadcrumb(self, state_id) -> str: return self.breadcrumbs[state_id]
	
	def display(self):
		size = len(self.action)
		print('Action and Goto: (%d states)'%size)
		head = ['','']+self.terminals+['']+self.nonterminals
		body = []
		for i, (b, a, g) in enumerate(zip(self.breadcrumbs, self.action, self.go)):
			body.append([i, b, *a, '', *g])
		pretty.print_grid([head]+body)
