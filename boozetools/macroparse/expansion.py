"""
Provide a mechanism to read the compacted scanning and parsing tables,
prepared using the algorithms in .compaction.py. If you were to build
a runtime system for another host language, you'd have to port these.
"""

from typing import Callable, Iterable, Any
from .interface import ScanAction
from boozetools.scanning.interface import FiniteAutomaton
from boozetools.scanning import charclass
from boozetools.parsing.interface import HandleFindingAutomaton

def displacement_function(otherwise:callable, *, offset, check, value) -> callable:
	"""
	(make a) Reader for a perfect-hash such as built at compaction.encode_displacement_function.
	If the queried cell is absent, the `otherwise` functional-argument provides the back-up plan.
	I'll admit that form is a bit unusual in Python, but it DOES encapsulate the interpretation.
	"""
	size = len(check)
	def fn(row_id:int, column:int) -> int:
		index = offset[row_id] + column
		if 0 <= index < size and check[index] == row_id:
			return value[index]
		else:
			return otherwise(row_id, column)
	return fn

def boolean_field(row_class, col_class, offset, check) -> Callable[[int, int], bool]:
	"""
	Make a reader for a boolean field. It's used in a couple places.
	They're compressed by equivalence-classification along both dimensions.
	"""
	size = len(check)
	def fn(row:int, col:int) -> bool:
		try: rc, cc = row_class[row], col_class[col]
		except IndexError: return False # The bogus-token is out of range.
		index = offset[rc] + cc
		return 0 <= index < size and check[index] == rc
	return fn

def scanner_delta_function(*, exceptions:dict, bg:dict) -> callable:
	"""
	This function came out of some observations about the statistics of scanner delta functions.
	The best way to understand this function is by reference to the following URL:
	https://github.com/kjosib/booze-tools/issues/8
	
	The basic idea is to first check a table of "unusual" entries in the scanner's transition matrix.
	If that comes up empty, then the "background" table is essentially a bitmap combined with a pair
	of most-common entries per given row. The bitmap compresses very well by means of row- and
	column-equivalence classes; only the 1's (being the less common) need be actually represented.
	
	The very most common entry in a row is usually the error transition (-1), so instead of a
	complete list per state, only the exceptions to this rule are listed.
	"""
	zeros = dict(zip(*bg['zero']))
	broad_pattern = boolean_field(bg['row_class'], bg['col_class'], bg['offset'], bg['check'])
	def general_population(state_id:int, symbol_id:int) -> int:
		if broad_pattern(state_id, symbol_id): return bg['one'][state_id]
		else: return zeros.get(state_id, -1)
	return displacement_function(general_population, **exceptions)

def parser_action_function(*, reduce, fallback, edits) -> callable:
	background = parser_reduce_function(**reduce)
	offset, check, value = edits['offset'], edits['check'], edits['value']
	size = len(check)
	def chase(row, col):
		probe = row
		while probe >= 0:
			index = offset[probe] + col
			if 0 <= index < size and check[index] == probe: return value[index]
			probe = fallback[probe]
		return background(row, col)
	absent = len(edits['check'])
	interactive = [r if o == absent and f==-1 else 0 for r,o,f in zip(reduce['d_reduce'], edits['offset'], fallback)]
	return chase, interactive.__getitem__

def parser_goto_function(*, row_index, col_index, quotient, mark ) -> callable:
	def probe(state_id:int, nonterminal_id:int):
		r, c = row_index[state_id], col_index[nonterminal_id]
		dominant = min(r, c)
		return quotient[dominant] if dominant < mark else quotient[r+c-mark]
	return probe

def parser_reduce_function(*, d_reduce, row_class, col_class, offset, check):
	predicate = boolean_field(row_class, col_class, offset, check)
	def fn(row, col):
		dr = d_reduce[row] # Consulting the predicate costs a few cycles.
		return dr if dr and predicate(row, col) else 0 # Do it only at need.
	return fn

def scan_actions(action:dict) -> Iterable[ScanAction]:
	args = [action[what] for what in ScanAction._fields]
	return map(ScanAction, *args)

class CompactDFA(FiniteAutomaton):
	"""
	This implements the FiniteAutomaton interface (for use with the generic scanner algorithm)
	by reference to a set of scanner tables that have been built using the MacroParse machinery.
	It's not the whole story: Something else needs to interpret the rules (given here only by number),
	and rules can possibly alter the state of the scanner also.
	"""
	def __init__(self, *, dfa:dict, alphabet:dict):
		self.classifier = charclass.MetaClassifier(**alphabet)
		self.delta = scanner_delta_function(**dfa['delta'])
		self.initial = dfa['initial']
		self.final = dict(zip(dfa['final'], dfa['rule']))
	
	def jam_state(self): return -1
	def condition(self, condition_name) -> tuple:
		try: return self.initial[condition_name]
		except KeyError: raise KeyError(condition_name, set(self.initial.keys()))
	def accept(self, state_id: int) -> int: return self.final.get(state_id)

	def transition(self, current_state: int, codepoint: int) -> int:
		return self.delta(current_state, self.classifier.classify(codepoint))
	
class CompactHFA(HandleFindingAutomaton):
	"""
	This implements the HandleFindingAutomaton interface (for use with the generic parse algorithm)
	by reference to a set of parser tables that have been built using the MacroParse machinery.
	It's not the whole story: something needs to provide reduction bindings.
	"""
	def __init__(self, parse_table:dict):
		# Parts devoted to finding handles per-se
		self.get_action, self.interactive_step = parser_action_function(**parse_table['action'])
		self.get_goto = parser_goto_function(**parse_table['goto'])
		self.terminals = parse_table['terminals']
		self.__translation = {symbol:i for i,symbol in enumerate(self.terminals)}
		self.nonterminals = parse_table['nonterminals']
		self.initial = parse_table['initial']
		self.breadcrumbs = parse_table['breadcrumbs']
		
		# Parts devoted to reducing according to rules
		rule = parse_table['rule']
		self.__constructor = rule['constructor']
		self.__line_number = rule['line_number']
		self.__rule = rule['rules']
		self.get_rule = self.__rule.__getitem__
		
		# Parts devoted to generalized LR parsing
		if 'splits' in parse_table:
			self.get_split_offset = parse_table['action']['reduce']['d_reduce'].__len__ # Gets the number of states.
			self.get_split = parse_table['splits'].__getitem__
		
	def get_translation(self, symbol) -> int:
		try: return self.__translation[symbol]
		except KeyError: return len(self.terminals) # Guaranteed to trigger error-processing.
	
	def get_action(self, state_id: int, terminal_id) -> int: assert False, 'See the constructor.'
	def get_goto(self, state_id: int, nonterminal_id) -> int: assert False, 'See the constructor.'
	def get_initial(self, language) -> int: return 0 if language is None else self.initial[language]
	def get_breadcrumb(self, state_id: int) -> str:
		bcid = self.breadcrumbs[state_id]
		if bcid is None: return ''
		if bcid < len(self.terminals): return self.terminals[bcid]
		else: return self.nonterminals[bcid-len(self.terminals)]
	def interactive_step(self, state_id: int) -> int: assert False, 'See the constructor.'
	def get_split_offset(self) -> int: assert False, 'This method gets replaced if there are splits.'
	def get_split(self, split_id: int) -> list: assert False, 'See the constructor.'
	def get_rule(self, rule_id: int) -> tuple: return self.__rule[rule_id]
	def get_constructor(self, constructor_id) -> object: return self.__constructor[constructor_id]
	
	def each_constructor(self) -> Iterable[tuple[Any, set[int]]]:
		mentions = [set() for _ in self.__constructor]
		for line_number, (ntid, size, cid, places) in zip(self.__line_number, self.__rule):
			if cid >= 0:
				mentions[cid].add(line_number)
		return zip(self.__constructor, mentions)


		

def _expand_rules(raw):
	"""
	Implement a proposed interpretation of a tight rules table.
	There's a related idea that might work in a C-like language where the rule IDs
	in the ACTION table are pre-translated to the offset (from the end) of their
	position in the rule data table. Then you just need a sentinel 0 at the end.
	"""
	result = []
	i = 0
	while i < len(raw):
		nonterminal_id, rhs_length, constructor_id = raw[i:i+3]
		view = []
		i += 3
		while i < len(raw) and raw[i] < 0:
			view.append(raw[i])
			i += 1
		result.append((nonterminal_id, rhs_length, constructor_id, tuple(view)))
	return result
