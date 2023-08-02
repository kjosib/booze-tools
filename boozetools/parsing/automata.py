"""
G-for-Generalized: GLR is basically the non-deterministic version of LR parsing.

As a parsing strategy, GLR means non-determinism is embraced and resolved as necessary at
in the context of actual parse runs. You can do GLR with any viable LR-style HFA, though
better tables naturally result in fewer blind alleys. In principle, the "trivial" table
is just the set of all grammar rules at every point: this yields classical Earley parsing.

Within this module, various handle-finding automaton (HFA) construction functions return a
(mostly) standardized structure which properly represents any remaining non-determinism.
Transmuting these to fully-deterministic structures is the LR module's job.

The HFA class itself contains a trial-parse routine which exercises these constructions
by determining whether they recognize a string as "in the language". It's great for testing
and illustrates one method to perform a parallel-parse, but it does not bother to recover a
parse tree or semantic value. Such things could be added, but preferably atop good means
for persisting ambiguous parse tables.
"""
import collections, sys
from pprint import pprint
from typing import Iterable, TypeVar, Generic, Any
from typing import NamedTuple
from ..support import foundation, pretty
from .interface import HandleFindingAutomaton, END_OF_TOKENS, ERROR_SYMBOL, ParseError
from .context_free import ContextFreeGrammar, Rule, SemanticAction, LEFT, RIGHT, NONASSOC, BOGUS

T = TypeVar('T')

class PurityError(ValueError):
	""" Raised if a grammar has the wrong/undeclared conflicts. """

class HFA(Generic[T]):
	"""
	HFA is short for "Handle-Finding Automaton", which is clunky to repeat all over the place.
	
	What is a handle?
	
	A handle is that point in the text where the right end of a rule has been matched and
	recognition of the corresponding non-terminal symbol could be performed.
	
	There is a common base structure for these, and certain operations are largely similar
	regardless of which sort of table-construction algorithm is underway.
	
	The main difference between HFAs is what sort of object they use for states.
	To participate in the generic operations, states must have a "shift" dictionary mapping
	symbols to successor state numbers (not objects) and support state.reductions_before(lexeme)
	which must return an Iterable of zero or more rule-IDs.
	
	Fields are:
	graph: a list of state objects; their index is implicitly their node ID.
	initial: a list of initial-state ID numbers (graph node indices) corresponding
		to the start-symbols of the CFG.
	accept: a list of final/accepting-state ID numbers (graph node indices) also
		corresponding to the start-symbols of the CFG.
	bft: The BreadthFirstTraversal object which was used for the construction.
		This happens to be greatly useful in various diagnostic and other capacities.
	"""
	graph: list[T]
	initial: list[int]
	accept: list[int]
	bft: foundation.BreadthFirstTraversal
	
	def __init__(self, *, graph, initial, accept, bft):
		""" I don't want exactly named-tuple semantics. """
		self.graph, self.initial,self.accept, self.bft = graph, initial, accept, bft
	
	def traverse(self, q: int, symbols:Iterable) -> int:
		""" Starting in state q, follow the shifts for symbols, and return the resulting state ID. """
		for s in symbols: q = self.graph[q].shift[s]
		return q
	
	def make_dot_file(self, path):
		""" Make a file suitable for the "dot" application from the Graphviz package. """
		# FIXME: This fails to take reductions into account.
		with open(path, 'w') as fh:
			fh.write("digraph {\n")
			for q, state in enumerate(self.graph):
				sym = self.bft.breadcrumbs[q] or ''
				sym = sym.replace('"', r'\"')
				if sym.endswith('\\'): sym = sym + ' '
				fh.write("%d [label=\"%d: %s\"]\n"%(q, q, sym))
				for i in state.shift.values():
					fh.write("\t%d -> %d\n"%(q,i))
			fh.write('}\n')
		pass
	
	def trial_parse(self, rules: list[Rule], sentence: Iterable[str]):
		"""
		This is intended to be a super-simplistic non-deterministic recognizer: It exists only for
		unit-testing the GLR table-construction algorithms, and therefore doesn't try to build a
		semantic value or worry about pathological grammars.

		The approach taken is a lock-step parallel simulation with a cactus-stack of viable states:
		each entry is a cons cell consisting of a state id and prior stack. Because it explores
		every possible parse, it will diverge if faced with an infinitely-ambiguous situation.
		There are ways to cope with such cases, but in practice they are normally the result of
		mistakes, so the more useful response is to reject infinitely-ambiguous grammars.

		To play along, HFA states must support the .reductions_before(lexeme) method.
		"""
		
		language_index = 0  # Or perhaps: grammar.start.index[language_symbol]
		initial, accept = self.initial[language_index], self.accept[language_index]
		
		def reduce(stack, rule_id):
			""" To perform a reduction, roll the stack to before the RHS and then shift the LHS. """
			rule = rules[rule_id]
			for i in range(len(rule.rhs)): stack = stack[1]
			return self.graph[stack[0]].shift[rule.lhs], stack
		
		root = (initial, None)
		alive = [root]
		for lexeme in sentence:
			next = []
			for stack in alive:
				state = self.graph[stack[0]]
				if lexeme in state.shift: next.append((state.shift[lexeme], stack))
				for rule_id in state.reductions_before(lexeme): alive.append(reduce(stack, rule_id))
			alive = next
			if not alive: raise ParseError("Parser died midway at something ungrammatical.")
		for stack in alive:
			q = stack[0]
			if q == accept: return True
			for rule_id in self.graph[q].reductions_before(END_OF_TOKENS):
				alive.append(reduce(stack, rule_id))
		raise ParseError("Parser recognized a viable prefix, but not a complete sentence.")

	def has_shift_reduce_conflict(self):
		return any(state.has_shift_reduce_conflict() for state in self.graph)

	def has_reduce_reduce_conflict(self):
		return any(state.has_reduce_reduce_conflict() for state in self.graph)


class LR0_State(NamedTuple):
	"""
	The LR(0) construction completely ignores right-context.
	Therefore, an LR(0) state tracks which rules it may recognize,
	but does not differentiate this information any further.
	"""
	shift: dict[str, int]  # symbol => state-id
	reduce: list[int]  # rule-id
	
	def reductions_before(self, lexeme):
		""" Did I mention LR(0) doesn't worry about look-ahead? """
		return self.reduce

	def has_shift_reduce_conflict(self):
		return bool(self.shift and self.reduce)
	
	def has_reduce_reduce_conflict(self):
		return len(self.reduce)>1


class LookAheadState(NamedTuple):
	"""
	An LR(1) or LALR(1) table needs to take a token of right-context
	into account when recognizing a rule. Therefore, the .reduce field
	is a dictionary keyed by look-ahead token.
	"""
	shift: dict[str, int]  # symbol => state-id
	reduce: dict[str, list[int]]  # LALR
	
	def reductions_before(self, lexeme):
		return self.reduce.get(lexeme, ())

	def has_shift_reduce_conflict(self):
		return bool(self.shift.keys() & self.reduce.keys())
	
	def has_reduce_reduce_conflict(self):
		return any(len(r)>1 for r in self.reduce.values())

def reachable(step: dict, reduce: dict, grammar:ContextFreeGrammar) -> dict:
	"""
	This function exists so that parse-table construction algorithms can respect operator
	precedence and associativity declarations in a grammar specification. It is a vital
	part of minimal-LR1 mode, but it also works for LALR and canonical-LR1.
	
	The object of this function is to prevent the exploration of useless/unreachable states.
	It does this by deleting a shift from the "step" dictionary whenever said shift becomes
	impossible by virtue of P&A declarations. It also deletes useless reductions similarly
	rendered unavailable, and denotes non-associativity errors by a sentinel empty-tuple.

	NOTE: When shift/reduce/reduce conflicts arise in connection with operator-precedence
	specifications, the intended semantics for a generalized parse are not always clearly
	defined. The code below should either behave sensibly or toss an exception.

	The problem with the bizarre corner cases is they cannot be understood solely in terms
	of actions the parser might (or might not) take in this state. If they come up, you
	get a warning printed on STDERR but otherwise the operator-precedence declarations
	are ignored in that instance.
	
	FIXME: This function should not perform I/O directly.
	"""
	for token, rule_id_list in list(reduce.items()):
		if token not in step: continue
		decide = [grammar.decide_shift_reduce(token, rule_id) for rule_id in rule_id_list]
		ways = set(decide)
		assert BOGUS not in ways, "This is guaranteed by grammar.validate(...), called earlier."
		if len(ways) == 1:
			decision = ways.pop()
			if decision == LEFT:
				del step[token]
			elif decision == RIGHT:
				del reduce[token]
			elif decision == NONASSOC:
				del step[token]
				reduce[token] = ()
			else:
				assert decision is None
		elif ways == {LEFT, NONASSOC}:
			del step[token]
			reduce[token] = tuple(r for r, d in zip(rule_id_list, decide) if d == LEFT)
		elif ways == {RIGHT, None}:
			reduce[token] = tuple(r for r, d in zip(rule_id_list, decide) if d != RIGHT)
		else:
			print("Fair Warning:", token, "triggers a bizarre operator-precedence corner case.", file=sys.stderr)
	return step



class DragonBookTable(HandleFindingAutomaton):
	"""
	This is the classic textbook view of a set of parse tables: a pair of dense matrices
	(implemented here as lists-of-lists) representing the "ACTION" and "GOTO" tables, along
	with information about the reduction rules. The contents of these matrices are just
	numbers representing parse actions.
	
	This is a reasonable implementation as-is if you have a modern amount of RAM in your
	machine. In days of old, it would be necessary to compress the parse tables. Today,
	that's still not such a bad idea if you can pre-compute the tables. The compaction
	submodule contains some code for a typical method of parser table compression, and
	the runtime submodule implements the HandleFindingAutomaton interface atop a compressed table.
	
	Design note: There's a temptation to make the constructor take an HFA object, but
	that limits the ways you can instantiate this class. See the function `tabulate(...)`.
	"""
	
	def __init__(self, *, initial: dict, action: list, goto: list, nonassoc_errors: set, rules: list, terminals: list,
	             nonterminals: list, breadcrumbs: list, splits=()):
		self.initial = initial
		self.action_matrix = action
		self.goto_matrix = goto
		self.nonassoc_errors = nonassoc_errors
		self.translate = {symbol: i for i, symbol in enumerate(terminals)}
		nontranslate = {symbol: i for i, symbol in enumerate(nonterminals)}
		self.terminals, self.nonterminals = terminals, nonterminals
		self.breadcrumbs = breadcrumbs
		
		def translate_rule(rule:Rule):
			"""
			The current approach to storing rule actions is:
			Each rule gets a constructor number and a list of "places".
			A negative constructor-number means a bracketing-rule,
			with an offset from the stack pointer telling where to find the semantic item.
			A non-negative points into a table of semantic actions
			for use with a translated ``places`` vector, which gives argument offsets.
			Perhaps the ``places`` vector should also be part of the equivalence relationship?
			"""
			size = len(rule.rhs)
			if isinstance(rule.action, int):
				assert rule.action < size
				cid,places = rule.action-size, ()
			else:
				assert isinstance(rule.action, SemanticAction)
				cid,places = messages.classify(rule.action.message), tuple(x-size for x in rule.action.indices)
			return nontranslate[rule.lhs], size, cid, places
		
		messages = foundation.EquivalenceClassifier()
		self.rule_table = list(map(translate_rule, rules))
		self.constructors = messages.exemplars
		
		self.rule_provenance = [rule.provenance for rule in rules]
		self.splits = splits # A non-deterministic table just needs one extra bit: this list of lists.
		
		interactive = []
		for row in action:
			k = set(row)
			k.discard(0)
			if len(k) == 1: interactive.append(min(k.pop(), 0))
			else: interactive.append(0)
		for q, t in nonassoc_errors: interactive[q] = False
		self.interactive_step = interactive.__getitem__
	
	def get_rule(self, rule_id: int) -> tuple:
		return self.rule_table[rule_id]
	
	def get_translation(self, symbol) -> int:
		try: return self.translate[symbol]
		except KeyError: return len(self.terminals) # Guaranteed to trigger error-processing.
		
	def get_action(self, state_id, terminal_id) -> int:
		try: return self.action_matrix[state_id][terminal_id]
		except IndexError: return 0 # And this needs to not panic if a bad token is observed; just cry foul.
	
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
		if self.splits:
			print("Splits:")
			pprint(self.splits)
	
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
			typical_grid(self.terminals, self.action_matrix, self.nonassoc_errors))
		pretty.write_csv_grid(pathstem + '.goto.csv', typical_grid(self.nonterminals, self.goto_matrix, frozenset()))
	
	def get_split_offset(self) -> int:
		return len(self.action_matrix)
	
	def get_split(self, split_id: int) -> list:
		assert split_id>0
		return self.splits[split_id]

	def get_constructor(self, constructor_id) -> Any: return self.constructors[constructor_id]
	
	def each_constructor(self):
		mentions = [set() for _ in self.constructors]
		for provenance, (ntid, size, cid, places) in zip(self.rule_provenance, self.rule_table):
			if cid >= 0:
				mentions[cid].add(provenance)
		return zip(self.constructors, mentions)


class ParsingStyle:
	"""
	There are three main ways to deal with inadequacies (non-determinism) remaining
	after application of any P&A declarations:
		1. Pure: Inadequacies are considered a grammar bug.
		2. Deterministic: Inadequacies are resolved to shift, or to use the earliest-defined rule.
		3. Generalized: Inadequacies are converted to parser-split entries.
	
	Probably the correct choice of style should be reflected in the grammar definition somehow.
	"""
	
	def decide_inadequacy(self, q:int, look_ahead:str, shift:int, rule_ids:Iterable, rules:list) -> int:
		""" Called in all non-deterministic situations. """
		raise NotImplementedError(type(self))
	
	def any_splits(self):
		""" Return nothing, or a list of splits for use in non-deterministic parsing algorithms. """
		raise NotImplementedError(type(self))

	def report(self, hfa, rules):
		""" Give user-feedback about any observed challenges. """
		raise NotImplementedError(type(self))

class DeterministicStyle(ParsingStyle):
	
	def __init__(self, strict:bool):
		self._conflict_rules = {}
		self._conflict_shift = set()
		self._strict = strict
	
	def decide_inadequacy(self, q:int, look_ahead: str, shift: int, rule_ids: Iterable, rules:list) -> int:
		key = (q, look_ahead)
		self._conflict_rules[key] = rule_ids
		if shift:
			self._conflict_shift.add(key)
			return shift
		else:
			return encode_reduce(min(rule_ids))
	
	def any_splits(self):
		pass
	
	def report(self, hfa, rules):
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
		
		In conclusion: Let the objects defined in automata.py format parse-states for human consumption.
		"""
		if not self._conflict_rules:
			# print("Grammar specification is fully deterministic.")
			pass
		else:
			print(("  "+pretty.DOT)*20)
			print(
				"Grammar entails %d shift/reduce conflicts and %d reduce/reduce conflicts."%
				(len(self._conflict_shift), len(self._conflict_rules) - len(self._conflict_shift)),
			)
			bft = hfa.bft
			for key, rule_ids in sorted(self._conflict_rules.items()):
				print()
				(q, look_ahead) = key
				print(' '.join(bft.breadcrumbs[k] for k in bft.shortest_path_to(q)[1:]), pretty.DOT, look_ahead)
				if key in self._conflict_shift:
					print("<shift>")
				for rule_id in rule_ids:
					print("\t\t\t",rules[rule_id])
			print()
			print(("  "+pretty.DOT)*20)
			if self._strict:
				raise PurityError(self._conflict_rules)

class GeneralizedStyle(ParsingStyle):
	
	def __init__(self, splits_offset:int):
		self.offset = splits_offset
		self.splits = []
	
	def decide_inadequacy(self, q: int, look_ahead: str, shift: int, rule_ids: Iterable, rules:list) -> int:
		split = []
		if shift: split.append(shift)
		for r in sorted(rule_ids, key=lambda i:len(rules[i].rhs)): split.append(-1-r)
		return self.offset + foundation.allocate(self.splits, split)
	
	def any_splits(self):
		return self.splits
	
	def report(self, hfa, rules):
		print(len(self.splits), "non-deterministic situation(s) encountered.")


def encode_reduce(rule_id:int) -> int:
	""" See interface.HandleFindingAutomaton.get_action. """
	return -1 - rule_id

def tabulate(hfa: HFA[LookAheadState], grammar:ContextFreeGrammar, *, style:ParsingStyle) -> DragonBookTable:
	"""
	Having an HFA based on State objects, this function produces a corresponding
	dense-matrix-style parse table of the sort typically shown in textbook descriptions
	of LR-style parsing automata.

	This function does NOT worry about precedence and associativity declarations:
	It assumes that concern has already been taken care of in the input HFA -
	principally by the interaction of function `reachable(...)` with the P&A bits.

	Any residual inadequacies of the grammar are delegated to the `style` object for
	resolution.
	"""
	assert isinstance(grammar, ContextFreeGrammar), grammar
	assert END_OF_TOKENS not in grammar.symbols
	assert ERROR_SYMBOL not in grammar.symbol_rule_ids
	terminals = [END_OF_TOKENS] + sorted(grammar.apparent_terminals())
	translate = {t:i for i,t in enumerate(terminals)}
	nonterminals = sorted(grammar.symbol_rule_ids.keys())
	
	##### Tabulate the states into dense matrices ACTION and GOTO:
	action, goto, nonassoc_errors = [], [], set()
	for q, state in enumerate(hfa.graph):
		goto.append([state.shift.get(s, 0) for s in nonterminals])
		action_row = [state.shift.get(s, 0) for s in terminals]
		for symbol, rule_ids in state.reduce.items():
			idx = translate[symbol]
			shift = action_row[idx]
			if rule_ids == ():
				# This is how function `reachable(...)` communicates a non-association situation.
				assert shift == 0
				nonassoc_errors.add((q,idx))
			elif shift == 0 and len(rule_ids) == 1:
				action_row[idx] = encode_reduce(rule_ids[0])
			else: action_row[idx] = style.decide_inadequacy(q, symbol, shift, rule_ids, grammar.rules)
		action.append(action_row)
	
	for q, t in nonassoc_errors: action[q][t] = 0
	for q in hfa.accept: action[q][0] = q
	style.report(hfa, grammar.rules)
	return DragonBookTable(
		initial=dict(zip(grammar.start, hfa.initial)),
		action=action,
		goto=goto,
		nonassoc_errors=nonassoc_errors,
		rules=grammar.rules,
		terminals=terminals,
		nonterminals=nonterminals,
		breadcrumbs=hfa.bft.breadcrumbs,
		splits=style.any_splits()
	)


