import typing, collections
from .foundation import *
from . import pretty, interfaces

DOT = '\u25cf'

LEFT, RIGHT, NONASSOC, BOGUS = object(), object(), object(), object()

class Fault(ValueError): pass
class DuplicateRule(Fault): pass
class NonTerminalsCannotHavePrecedence(Fault): pass
class FailedToSetPrecedenceOnPrecsym(Fault): pass
class PrecedenceDeclaredTwice(Fault): pass
class RuleProducesBogusToken(Fault): pass # The rule produces a bogus symbol...
class UnreachableSymbols(Fault): pass
class NonproductiveSymbols(Fault): pass

class Rule(typing.NamedTuple):
	lhs: str
	rhs: tuple
	attribute: object
	prec_sym: typing.Optional[str]

class ContextFreeGrammar:
	"""
	Formally, a context free grammar consists of:
		* A set of terminal symbols,
		* A set of non-terminal symbols, disjoint from the terminals,
		* A set of production rules (as described at class Rule),
		* and a start symbol.
	
	As a cool and potentially useful hack, I expand the normal definition to allow
	potentially several "start symbols" to share the same overall definition. This allows
	a single set of tables to be used (with a different initial state) to parse different
	languages (or sub-phrases) while sharing common specification elements.
	
	Practical languages usually have some ambiguities which are ordinarily resolved with
	precedence declarations. If explicit declarations are not provided, the grammar is
	ambiguous -- at least with respect to the power of the table-generation method used.
	There are ways to deal with ambiguity, but for deterministic parsers the convention
	is to shift on a shift-reduce conflict (i.e. assume right-associativity) and, in
	the event of a reduce/reduce conflict, to use the earliest-defined rule.
	"""
	def __init__(self):
		self.symbols = set()
		self.start = [] # The start symbol(s) may be specified asynchronously to construction or the rules.
		self.rules, self.token_precedence, self.level_assoc = [], {}, []
		self.symbol_rule_ids = {}
	def display(self):
		head = ['', 'Symbol', 'Produces', 'Using']
		body = [[i, rule.lhs, rule.rhs, rule.attribute] for i,rule in enumerate(self.rules)]
		pretty.print_grid([head] + body)

	def rule(self, lhs:str, rhs:(list, tuple), attribute:object, prec_sym=None):
		"""
		This is your basic mechanism to install arbitrary plain-jane BNF rules.
		For the sake of simplicity, at this layer symbols are all strings.
		Duplicate rules are rejected by raising an exception.
		
		:param lhs: The "left-hand-side" non-terminal symbol which is declared to produce...
		
		:param rhs: this "right-hand-side" sequence of symbols.
		
		:param attribute: This is uninterpreted, except in one simple manner:
		if the attribute is `None` and the right-hand-side contains only a single symbol,
		then the production is considered a unit/renaming rule, and the parser tables
		will optimize this rule to a zero-cost abstraction (wherever possible).
		
		:param prec_sym: Set the precedence of this reduction explicitly according to that
		of the given symbol as previously declared. If this is not supplied and the table
		construction algorithm finds it necessary, method infer_prec_sym(...) implements
		default processing on the right-hand-side.
		
		:return: Nothing.
		
		Please note: Certain rare constructions make the unit-rule optimization unsound.
		The tables will be constructed correctly but the general parsing algorithm needs
		to be prepared to find a rule with a null attribute. Correct behavior is generally
		to leave the semantic-stack unchanged.
		"""
		if lhs in self.token_precedence: raise NonTerminalsCannotHavePrecedence(lhs)
		assert attribute is not None or len(rhs) == 1, 'There are no shortcuts at this layer.'
		self.symbols.add(lhs)
		self.symbols.update(rhs)
		if lhs not in self.symbol_rule_ids: self.symbol_rule_ids[lhs] = []
		sri = self.symbol_rule_ids[lhs]
		if any(self.rules[rule_id].rhs == rhs for rule_id in sri): raise DuplicateRule(lhs, rhs)
		sri.append(allocate(self.rules, Rule(lhs, rhs, attribute, prec_sym)))
	
	def validate(self):
		"""
		This raises an exception (derived from Fault, above) for the first error noticed.
		It might be nice to get a more complete read-out of problems, but that would mean
		inventing some sort of document structure to talk about faults in grammars.
		Then again, maybe that's in the pipeline.
		"""
		bogons = {sym for sym, prec in self.token_precedence.items() if self.level_assoc[prec] is BOGUS}
		produces = collections.defaultdict(set)  # nt -> set[t]
		produced_by = collections.defaultdict(set)
		for rule_id, rule in enumerate(self.rules):
			assert rule.attribute is not None or len(rule.rhs) == 1
			if rule.prec_sym is not None and rule.prec_sym not in self.token_precedence:
				raise FailedToSetPrecedenceOnPrecsym(rule_id)
			produces[rule.lhs].update(rule.rhs)
			for symbol in rule.rhs:
				produced_by[symbol].add(rule.lhs)
				if symbol in bogons: raise RuleProducesBogusToken(rule_id)
		unreachable = self.symbols - transitive_closure(self.start, produces.get)
		# NB: This shows the bogons are not among the true symbols.
		if unreachable: raise UnreachableSymbols(unreachable)
		nonterminals = set(produces.keys())
		nonproductive = self.symbols - transitive_closure(self.symbols-nonterminals, produced_by.get)
		if nonproductive: raise NonproductiveSymbols(nonproductive)
		pass
	
	def assoc(self, direction, symbols):
		assert direction in (LEFT, NONASSOC, RIGHT, BOGUS)
		assert symbols
		level = allocate(self.level_assoc, direction)
		for symbol in symbols:
			if symbol in self.symbol_rule_ids: raise NonTerminalsCannotHavePrecedence(symbol)
			if symbol in self.token_precedence: raise PrecedenceDeclaredTwice(symbol)
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
	
	def infer_prec_sym(self, rhs):
		"""
		If a rule without an explicit precedence declaration is involved in a shift/reduce conflict,
		the parse table generation algorithm will call this to decide which symbol represents the
		precedence of this right-hand-side.
		
		As a slight refinement to the BISON approach, this returns the first terminal with an
		assigned precedence, as opposed to the first terminal symbol whatsoever. Often that's
		a distinction without a difference, but when it matters I think this makes more sense.
		"""
		for symbol in rhs:
			if symbol in self.token_precedence:
				return symbol

	def lalr_construction(self, *, strict:bool=False) -> 'DragonBookTable':
		class State(typing.NamedTuple):
			shifts: dict
			complete: set  # rule_id
			follow: dict  # rule_id -> set_id
		
		##### Start by arranging most of the grammar data in a convenient form:
		assert self.start
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
			for rule_id, language in enumerate(self.start, len(self.rules)):
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
		initial = {language: bft.lookup(front([allocate(RHS, [language])])) for language in self.start}
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
			print('==============\nIn language %r, consider:' % self.start[cursor])
			print('\t'+' '.join(reversed(trail)),DOT,lookahead)
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
							elif decision == BOGUS: raise RuleProducesBogusToken(rule_id)
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
	the parse tables. Today, that's still not such a bad idea. The compaction submodule contains
	some code for a typical method of parser table compression.
	"""
	def __init__(self, *, initial:dict, action:list, goto:list, essential_errors:set, rules:list, terminals:list, nonterminals:list, breadcrumbs:list):
		self.initial = initial
		self.action_matrix = action
		self.goto_matrix = goto
		self.essential_errors = essential_errors
		self.translate = {symbol: i for i, symbol in enumerate(terminals)}
		self.get_translation = self.translate.__getitem__
		nontranslate = {symbol: i for i, symbol in enumerate(nonterminals)}
		self.terminals, self.nonterminals = terminals, nonterminals
		self.breadcrumbs = breadcrumbs
		self.rule_table = [(nontranslate[rule.lhs], len(rule.rhs), rule.attribute) for rule in rules]
		self.get_rule = self.rule_table.__getitem__
		
		interactive = []
		for row in action:
			k = set(row)
			k.discard(0)
			if len(k) == 1: interactive.append(min(k.pop(), 0))
			else: interactive.append(0)
		for q,t in essential_errors: interactive[q] = False
		self.interactive_step = self.interactive_rule_for = interactive.__getitem__
	
	def get_translation(self, symbol) -> int: return self.translate[symbol] # This gets replaced ...
	
	def get_action(self, state_id, terminal_id) -> int: return self.action_matrix[state_id][terminal_id]
	
	def get_goto(self, state_id, nonterminal_id) -> int: return self.goto_matrix[state_id][nonterminal_id]
	
	def get_initial(self, language) -> int: return 0 if language is None else self.initial[language]
	
	def get_breadcrumb(self, state_id) -> str: return self.breadcrumbs[state_id]
	
	def display(self):
		size = len(self.action_matrix)
		print('Action and Goto: (%d states)'%size)
		head = ['','']+self.terminals+['']+self.nonterminals
		body = []
		for i, (b, a, g) in enumerate(zip(self.breadcrumbs, self.action_matrix, self.goto_matrix)):
			body.append([i, b, *a, '', *g])
		pretty.print_grid([head] + body)
	
	def make_csv(self, pathstem):
		""" Generate action and goto tables into CSV files suitable for inspection in a spreadsheet program. """
		def mask(q, row, essential):
			return [
				s if s or (q,t) in essential else None
				for t, s in enumerate(row)
			]
		def typical_grid(top, matrix, essential):
			head = [None, None, *top]
			return [head]+[  [q, self.breadcrumbs[q]]+mask(q, row, essential)  for q, row in enumerate(matrix)]
		pretty.write_csv_grid(pathstem + '.action.csv', typical_grid(self.terminals, self.action_matrix, self.essential_errors))
		pretty.write_csv_grid(pathstem + '.goto.csv', typical_grid(self.nonterminals, self.goto_matrix, frozenset()))
