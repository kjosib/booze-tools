"""
This module is the dual of `compaction.py`:
It provides a runtime interface to compacted scanner and parser tables.
"""
from boozetools.interfaces import ScanState
from . import interfaces, charclass, algorithms

def sparse_table_function(*, index, data) -> callable:
	"""
	The very simplest Python-ish "sparse matrix", and plenty fast on modern hardware, for the
	size of tables this module will probably ever see, is an ordinary Python dictionary from
	<row,column> tuples to significant table entries. There are better ways if you program
	closer to the bare metal, but this serves the purpose.
	
	This routine unpacks "compressed-sparse-row"-style data into an equivalent Python dictionary,
	then returns a means to query said dictionary according to the expected 2-dimensional interface.
	"""
	hashmap = {}
	for row_id, (Cs, Ds) in enumerate(zip(index, data)):
		if isinstance(Ds, int): # All non-blank cells this row have the same value:
			for column_id in Cs: hashmap[row_id, column_id] = Ds
		else:
			for column_id, d in zip(Cs, Ds) if Cs else enumerate(Ds):
				hashmap[row_id, column_id] = d
	return lambda R, C: hashmap.get((R, C))

def scanner_delta_function(*, exceptions:dict, background:dict) -> callable:
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
	zeros = dict(zip(*background['zero']))
	def fn(state_id:int, symbol_id:int) -> int:
		# Is this an "exceptional" case? Let's check:
		offset = exceptions['offset'][state_id] + symbol_id
		if 0 <= offset < len(exceptions['check']) and exceptions['check'][offset] == state_id:
			return exceptions['value'][offset]
		else: # Determined NOT to be exceptional:
			rc, cc = background['row_class'][state_id], background['column_class'][symbol_id]
			offset = background['offset'][rc] + cc
			if 0 <= offset < len(background['check']) and background['check'][offset] == rc:
				return background['one'][state_id]
			else: return zeros.get(state_id, -1)
		pass
	return fn

def parser_action_function(*, index, data, default) -> callable:
	""" This part adds the "default reductions" layer atop the now-sparse action table. """
	probe = sparse_table_function(index=index, data=data)
	def fn(state_id:int, symbol_id:int) -> int:
		q = probe(state_id, symbol_id)
		return default[state_id] if q is None else q
	return fn

def parser_goto_function(*, row_index, col_index, quotient, residue ) -> callable:
	cut = len(quotient)
	def probe(state_id:int, nonterminal_id:int):
		r, c = row_index[state_id], col_index[nonterminal_id]
		dominant = min(r, c)
		return quotient[dominant] if dominant < cut else residue[r-cut][c-cut]
	return probe

	
def old_parser_goto_function(*, state_class, class_list ) -> callable:
	def probe(state_id:int, nonterminal_id:int):
		cls = state_class[state_id]
		return 0-cls if cls < 0 else class_list[cls][nonterminal_id]
	return probe

class CompactDFA(interfaces.FiniteAutomaton):
	"""
	This implements the FiniteAutomaton interface (for use with the generic scanner algorithm)
	by reference to a set of scanner tables that have been built using the MacroParse machinery.
	It's not the whole story; SymbolicScanRules (defined below) are involved in binding the
	action specifications to a specific context object.
	"""
	def __init__(self, *, dfa:dict, alphabet:dict):
		self.classifier = charclass.MetaClassifier(**alphabet)
		self.delta = scanner_delta_function(**dfa['delta'])
		self.initial = dfa['initial']
		self.final = dict(zip(dfa['final'], dfa['rule']))
	
	def jam_state(self): return -1
	def get_condition(self, condition_name) -> tuple:
		try: return self.initial[condition_name]
		except KeyError: raise KeyError(condition_name, set(self.initial.keys()))
	def get_state_rule_id(self, state_id: int) -> int: return self.final.get(state_id)

	def get_next_state(self, current_state: int, codepoint: int) -> int:
		return self.delta(current_state, self.classifier.classify(codepoint))

class SymbolicScanRules(interfaces.ScanRules):
	"""
	This binds symbolic scan-action specifications to a specific "driver" or context object.
	It cannot act alone, but works in concert with the CompactDFA (above) and the generic scan algorithm.
	"""
	def __init__(self, *, action:dict, driver:object):
		self._parameter   = action['parameter']
		self._trail       = action['trail']
		self._line_number = action['line_number']
		self.__methods = [getattr(driver, 'scan_'+message) for message in action['message']]
		
	def get_trailing_context(self, rule_id: int): return self._trail[rule_id]
	
	def invoke(self, scan_state: ScanState, rule_id:int):
		return self.__methods[rule_id](scan_state, self._parameter[rule_id])

def mangle(message):
	""" Describes the relation between parse action symbols (from parse rule data) to driver method names. """
	if message is None: return None
	if message.startswith(':'): return 'action_'+message[1:]
	return 'parse_'+message

class SymbolicParserTables(interfaces.ParserTables):
	"""
	This implements the ParserTables interface (for use with the generic parse algorithm)
	by reference to a set of parser tables that have been built using the MacroParse machinery.
	It's not the whole story: the function `symbolic_reducer(driver)` is involved to build a
	"combiner" function which the parse algorithm then uses for semantic reductions.
	"""
	def __init__(self, parser:dict):
		action_ = parser['action']
		self.get_action = parser_action_function(**action_)
		self.interactive_step = [0 if cols else d for d,cols in zip(action_['default'], action_['index'])].__getitem__
		self.get_goto = parser_goto_function(**parser['goto'])
		self.terminals = parser['terminals']
		self.get_translation = {symbol:i for i,symbol in enumerate(self.terminals)}.__getitem__
		self.nonterminals = parser['nonterminals']
		self.initial = parser['initial']
		self.breadcrumbs = parser['breadcrumbs']
		self.rule = parser['rule']
		messages = [(mangle(m), v) if m or v else None for (m,v) in zip(self.rule['message'], self.rule['view'])]
		self.get_rule = list(zip(self.rule['head'], self.rule['size'], messages)).__getitem__
		
	def get_translation(self, symbol) -> int: assert False, 'See the constructor.'
	def get_action(self, state_id: int, terminal_id) -> int: assert False, 'See the constructor.'
	def get_goto(self, state_id: int, nonterminal_id) -> int: assert False, 'See the constructor.'
	def get_rule(self, rule_id: int) -> tuple: assert False, 'See the constructor.'
	
	def get_initial(self, language) -> int: return self.initial[language]
	def get_breadcrumb(self, state_id: int) -> str:
		bcid = self.breadcrumbs[state_id]
		if bcid < len(self.terminals): return self.terminals[bcid]
		else: return self.nonterminals[bcid-len(self.terminals)]
	
	def interactive_step(self, state_id: int) -> int: assert False, 'See the constructor.'

def symbolic_reducer(driver):
	""" Build a reduction function (combiner) for the parse engine out of an arbitrary Python object. """
	# This is probably reasonably quick as-is, but you're welcome to profile it.
	def combine(message, attribute_stack):
		method, view = message
		if method is not None:return getattr(driver, method)(*(attribute_stack[x] for x in view))
		elif len(view) == 1: return attribute_stack[view[0]] # Bracketing rule
		else: return tuple(attribute_stack[x] for x in view) # Tuple Collection Rule
	return combine

def the_simple_case(tables, scan_driver, parse_driver, *, start='INITIAL', language=None, interactive=False):
	"""
	This generates a function for parsing texts based on a set of tables and supplied drivers.
	
	It is simple in that no special provisions are made querying the state of a failed scan/parse,
	and it uses the simple version of the parse algorithm which means at most one token per scan pattern match.
	But it's fine for many simple applications.
	
	:param tables: Generally the output of boozetools.macroparse.compiler.compile_file, but maybe deserialized.
	:param scan_driver: needs .scan_foo(...) methods.
	:param parse_driver: needs .parse_foo(...) methods. This may be the same object as scan_driver.
	:param start: Optionally, the start-state for the scanner DFA.
	:param language: Optionally, the start-symbol for the parser.
	:param interactive: True if you want the parser to opportunistically reduce whenever lookahead would not matter.
	:return: a callable object.
	"""
	scanner_tables = tables['scanner']
	dfa = CompactDFA(dfa=scanner_tables['dfa'], alphabet=scanner_tables['alphabet'])
	scan_rules = SymbolicScanRules(action=scanner_tables['action'], driver=scan_driver)
	hfa = SymbolicParserTables(tables['parser'])
	combine = symbolic_reducer(parse_driver)
	return lambda text: algorithms.parse(hfa, combine, algorithms.Scanner(text=text, automaton=dfa, rulebase=scan_rules, start=start), language=language, interactive=interactive)
	
