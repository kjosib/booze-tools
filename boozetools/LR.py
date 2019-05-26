"""
As all the non-deterministic LR mechanism is in module GLR, so this module deals with
the pure-deterministic side of things. It also understands about resolving grammar
conflicts by means of the precedence declarations which may accompany our basic
context-free structures.

In the short run, this will mean disentangling all the too-tightly-coupled bits.
"""
import collections
from . import interfaces, pretty, context_free, foundation, GLR

class DragonBookTable(interfaces.ParserTables):
	"""
	This is the classic textbook view of a set of parse tables. It's also a reasonably quick implementation
	if you have a modern amount of RAM in your machine. In days of old, it would be necessary to compress
	the parse tables. Today, that's still not such a bad idea. The compaction submodule contains
	some code for a typical method of parser table compression.
	"""
	
	def __init__(self, *, initial: dict, action: list, goto: list, essential_errors: set, rules: list, terminals: list,
	             nonterminals: list, breadcrumbs: list):
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
		for q, t in essential_errors: interactive[q] = False
		self.interactive_step = self.interactive_rule_for = interactive.__getitem__
	
	def get_translation(self, symbol) -> int: return self.translate[symbol]  # This gets replaced ...
	
	def get_action(self, state_id, terminal_id) -> int: return self.action_matrix[state_id][terminal_id]
	
	def get_goto(self, state_id, nonterminal_id) -> int: return self.goto_matrix[state_id][nonterminal_id]
	
	def get_initial(self, language) -> int: return 0 if language is None else self.initial[language]
	
	def get_breadcrumb(self, state_id) -> str: return self.breadcrumbs[state_id]
	
	def display(self):
		size = len(self.action_matrix)
		print('Action and Goto: (%d states)' % size)
		head = ['', ''] + self.terminals + [''] + self.nonterminals
		body = []
		for i, (b, a, g) in enumerate(zip(self.breadcrumbs, self.action_matrix, self.goto_matrix)):
			body.append([i, b, *a, '', *g])
		pretty.print_grid([head] + body)
	
	def make_csv(self, pathstem):
		""" Generate action and goto tables into CSV files suitable for inspection in a spreadsheet program. """
		
		def mask(q, row, essential):
			return [
				s if s or (q, t) in essential else None
				for t, s in enumerate(row)
			]
		
		def typical_grid(top, matrix, essential):
			head = [None, None, *top]
			return [head] + [[q, self.breadcrumbs[q]] + mask(q, row, essential) for q, row in enumerate(matrix)]
		
		pretty.write_csv_grid(pathstem + '.action.csv',
			typical_grid(self.terminals, self.action_matrix, self.essential_errors))
		pretty.write_csv_grid(pathstem + '.goto.csv', typical_grid(self.nonterminals, self.goto_matrix, frozenset()))
	
def consider(hfa, q, lookahead, options):
	"""
	This function was originally intended as a way to visualize the branches of a conflict.
	In its original form a bunch of context was available; I've gratuitously stripped that away
	and now I want to break this down to the bits we actually need.
	
	I had been using BreadthFirstTraversal.breadcrumbs[q] as a way to know
	the accessing symbol of each state. This is still perfectly valid and also needed for the
	strategy of illustrating parse errors by displaying the so-called "symbols on the stack" which
	requires the very same information. Therefore, I conclude that a valid complete set of (G)LR-ish
	parse tables MUST INCLUDE the "breadcrumb" field, but a better name would be a fine thing.
	
	bft.earliest_predecessor[...] is involved in determining an example path to reach any
	given parse state. It's shortest by construction (being breadth-first and all) but it may
	not be unique. The path-finding logic should go to the BFT object, and the rest ought to be
	up to the GLR0 object.
	
	BreadthFirstTraversal.traversal[x] was used to grab the core LR(0) parse items
	(in the form of rule_id/position pairs) in order to visualize the state reached by
	shifting the lookahead token if that shift is viable.
	
	The "options" list contains numeric candidate ACTION instructions which are interpreted
	in the usual way: This does represent a data-coupling, but one that's unlikely to change,
	so I'm not too worried about it just now.
	
	In conclusion: Let the GLR... objects format parse-states for human consumption.
	"""
	hfa.display_situation(q, lookahead)
	for x in options:
		if x > 0:
			print("Do we shift into:")
			left_parts, right_parts = [], []
			for r, p in hfa.bft.traversal[x]:
				rhs = hfa.grammar.rules[r].rhs
				left_parts.append(' '.join(rhs[:p]))
				right_parts.append(' '.join(rhs[p:]))
			align = max(map(len, left_parts)) + 10
			for l, r in zip(left_parts, right_parts): print(
				' ' * (align - len(l)) + l + '  ' + pretty.DOT + '  ' + r)
		else:
			rule = hfa.grammar.rules[-x - 1]
			print("Do we reduce:  %s -> %s" % (rule.lhs, ' '.join(rule.rhs)))

def lalr_construction(grammar:context_free.ContextFreeGrammar, *, strict: bool = False) -> DragonBookTable:
	assert GLR.END not in grammar.symbols
	hfa = GLR.glalr_construction(grammar)
	terminals = [GLR.END]+sorted(grammar.apparent_terminals())
	translate = {t:i for i,t in enumerate(terminals)}
	nonterminals = sorted(grammar.symbol_rule_ids.keys())
	##### Determinize the result:
	action, goto, essential_errors = [], [], set()
	pure = True
	conflict = collections.defaultdict(set)
	for q, state in enumerate(hfa.graph):
		goto.append([state.shift.get(s, 0) for s in nonterminals])
		action_row = [state.shift.get(s, 0) for s in terminals]
		conflict.clear()
		for symbol, rule_ids in state.reduce.items():
			if len(rule_ids) > 1:
				rule_id = grammar.decide_reduce_reduce(rule_ids)
				if rule_id is None:
					conflict[symbol].update(-1-r for r in rule_ids)
					rule_id = min(rule_ids)
			else: rule_id = rule_ids[0]
			reduce = -1 - rule_id
			idx = translate[symbol]
			prior = action_row[idx]
			if prior == 0: action_row[idx] = reduce
			else:
				decision = grammar.decide_shift_reduce(symbol, rule_id)
				if decision == context_free.LEFT: action_row[idx] = reduce
				elif decision == context_free.RIGHT: pass
				elif decision == context_free.NONASSOC: essential_errors.add((q, idx))
				elif decision == context_free.BOGUS: raise context_free.RuleProducesBogusToken(rule_id)
				else: conflict[symbol].update([prior, reduce])
		if conflict:
			pure = False
			for symbol, options in conflict.items(): consider(hfa, q, symbol, options)
		action.append(action_row)
	for q, t in essential_errors: action[q][t] = 0
	if strict: assert pure
	for q in hfa.accept: action[q][0] = q
	return DragonBookTable(
		initial=dict(zip(grammar.start, hfa.initial)),
		action=action,
		goto=goto,
		essential_errors=essential_errors,
		rules=grammar.rules,
		terminals=terminals,
		nonterminals=nonterminals,
		breadcrumbs=hfa.bft.breadcrumbs,
	)


