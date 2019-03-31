"""
This module is the dual of `compaction.py`:
It provides a runtime interface to compacted scanner and parser tables.
"""
from boozetools.interfaces import ScanState
from . import interfaces, charclass

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

def scanner_delta_function(*, index, data, default) -> callable:
	""" This adds the relevant smarts for dealing with the scanner-table compaction. """
	probe = sparse_table_function(index=index, data=data)
	def fn(state_id:int, symbol_id:int) -> int:
		if state_id<0: return state_id
		q = probe(state_id, symbol_id)
		if q is None:
			d = default[state_id]
			return d if d > -2 else fn(-2-d, symbol_id)
		else: return q
	return fn

def parser_action_function(*, index, data, default) -> callable:
	probe = sparse_table_function(index=index, data=data)
	def fn(state_id:int, symbol_id:int) -> int:
		q = probe(state_id, symbol_id)
		return default[state_id] if q is None else q
	return fn

def parser_goto_function(*, state_class, class_list ) -> callable:
	""" The compressed goto function is good, fast, and cheap: """
	def probe(state_id:int, nonterminal_id:int):
		cls = state_class[state_id]
		return 0-cls if cls < 0 else class_list[cls][nonterminal_id]
	return probe

class CompactDFA(interfaces.FiniteAutomaton):
	"""
	This sets up using information
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
	def __init__(self, *, action:dict, driver:object):
		self._parameter   = action['parameter']
		self._trail       = action['trail']
		self._line_number = action['line_number']
		self.__methods = [getattr(driver, 'scan_'+message) for message in action['message']]
		
	def get_trailing_context(self, rule_id: int): return self._trail[rule_id]
	
	def invoke(self, scan_state: ScanState, rule_id:int):
		return self.__methods[rule_id](scan_state, self._parameter[rule_id])

def mangle(message):
	if message is None: return None
	if message.startswith(':'): return 'action_'+message[1:]
	return 'parse_'+message

class SymbolicParserTables(interfaces.ParserTables):
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
	""" Build a reduction function for the parse engine out of an arbitrary Python object. """
	def combine(message, attribute_stack):
		method, view = message
		if method is not None: return getattr(driver, method)(*(attribute_stack[x] for x in view))
		elif len(view) == 1: return attribute_stack[view[0]] # Bracketing rule
		else: return tuple(attribute_stack[x] for x in view) # Tuple Collection Rule
	return combine
	