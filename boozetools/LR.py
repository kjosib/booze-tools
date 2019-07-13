"""
Building a deterministic parse table can be seen as first building one that admits
non-determinism then taking a further step. That further step is the bulk of this module.

The basic plan is to transcribe a Handle-Finding Automaton into a form useful for the
deterministic-parse algorithm, taking the deterministic parts verbatim and consulting
the grammar's precedence declarations otherwise. If that provides a resolution, all is
well. Otherwise, a non-resolved ambiguity is reported and the chosen deterministic-action
becomes a matter of policy: The usual convention is to shift when possible, or otherwise
reduce using the earliest-defined applicable rule.
"""
import collections
from . import interfaces, pretty, GLR

class DragonBookTable(interfaces.ParseTable):
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
	
	BreadthFirstTraversal.traversal[x] was used to grab the core parse items in order to
	visualize the state reached by shifting the lookahead token if that shift is viable.
	Such really belongs as a method on the state: soon it will move there.
	
	The "options" list contains numeric candidate ACTION instructions which are interpreted
	in the usual way: This does represent a data-coupling, but one that's unlikely to change,
	so I'm not too worried about it just now.
	
	In conclusion: Let the objects defined in GLR.py format parse-states for human consumption.
	"""
	hfa.display_situation(q, lookahead)
	for x in options:
		if x > 0:
			print("Do we shift into:")
			left_parts, right_parts = [], []
			for r, p, *_ in hfa.bft.traversal[x]:
				rhs = hfa.grammar.rules[r].rhs
				left_parts.append(' '.join(rhs[:p]))
				right_parts.append(' '.join(rhs[p:]))
			align = max(map(len, left_parts)) + 10
			for l, r in zip(left_parts, right_parts):
				print(' ' * (align - len(l)) + l + '  ' + pretty.DOT + '  ' + r)
		else:
			rule = hfa.grammar.rules[-x - 1]
			print("Do we reduce:  %s -> %s" % (rule.lhs, ' '.join(rule.rhs)))


def determinize(hfa:GLR.HFA[GLR.LA_State], *, strict: bool) -> DragonBookTable:
	"""
	This function does NOT worry about precedence and associativity declarations:
	It assumes that concern has already been taken care of in the input HFA.
	"""
	grammar = hfa.grammar
	assert GLR.END not in grammar.symbols
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
			idx = translate[symbol]
			if rule_ids is ():
				# This is how GLR.reachable(...) communicates a non-association situation.
				essential_errors.add((q,idx))
				continue
			if len(rule_ids) > 1:
				conflict[symbol].update(-1-r for r in rule_ids)
				rule_id = min(rule_ids)
			else: rule_id = rule_ids[0]
			reduce = -1 - rule_id
			prior = action_row[idx]
			if prior == 0: action_row[idx] = reduce
			else: conflict[symbol].update([prior, reduce])
		if conflict:
			pure = False
			for symbol, options in conflict.items(): consider(hfa, q, symbol, options)
		action.append(action_row)
	for q, t in essential_errors: action[q][t] = 0
	if strict and not pure: raise interfaces.PurityError()
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


