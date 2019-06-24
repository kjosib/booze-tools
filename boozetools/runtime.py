"""
This module is the dual of `compaction.py`:
It provides a runtime interface to compacted scanner and parser tables.
"""
from boozetools.interfaces import ScanState
from . import interfaces, charclass, algorithms
import inspect, functools

def displacement_function(otherwise:callable, *, offset, check, value) -> callable:
	"""
	(make a) Reader for a perfect-hash such as built at compaction.encode_displacement_function.
	If the queried cell is absent, the `otherwise` functional-argument provides the back-up plan.
	I'll admit that form is a bit unusual in Python, but it DOES encapsulate the interpretation.
	"""
	size = len(check)
	def fn(state_id:int, symbol_id:int) -> int:
		index = offset[state_id] + symbol_id
		if 0 <= index < size and check[index] == state_id:
			probe = value[index]
			if probe is not None: return probe
		return otherwise(state_id, symbol_id)
	return fn

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
	def general_population(state_id:int, symbol_id:int) -> int:
		rc, cc = background['row_class'][state_id], background['column_class'][symbol_id]
		offset = background['offset'][rc] + cc
		if 0 <= offset < len(background['check']) and background['check'][offset] == rc:
			return background['one'][state_id]
		else: return zeros.get(state_id, -1)
	return displacement_function(general_population, **exceptions)

def parser_action_function(*, reduce, fallback, edits) -> callable:
	def otherwise(state_id:int, symbol_id:int) -> int:
		""" This deals with chasing the fallback links connected to the "similar rows" concept. """
		fb = fallback[state_id]
		return look_at(fb, symbol_id) if fb >= 0 else None # Note the recursion here...
	look_at = displacement_function(otherwise, **edits)
	def fn(state_id:int, symbol_id:int) -> int:
		""" This part adds the "default reductions" layer. """
		step = look_at(state_id, symbol_id)
		return step if step is not None else reduce[state_id]
	# The somewhat-clever way eager-to-reduce states are denoted is recovered this way:
	interactive = [r if displacement==len(edits['check']) else 0 for r,displacement in zip(reduce, edits['offset'])]
	return fn, interactive.__getitem__

def parser_goto_function(*, row_index, col_index, quotient, mark ) -> callable:
	def probe(state_id:int, nonterminal_id:int):
		r, c = row_index[state_id], col_index[nonterminal_id]
		dominant = min(r, c)
		return quotient[dominant] if dominant < mark else quotient[r+c-mark]
	return probe

class CompactDFA(interfaces.FiniteAutomaton):
	"""
	This implements the FiniteAutomaton interface (for use with the generic scanner algorithm)
	by reference to a set of scanner tables that have been built using the MacroParse machinery.
	It's not the whole story; BoundScanRules (defined below) are involved in binding the
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

class BoundScanRules(interfaces.ScanRules):
	"""
	This binds symbolic scan-action specifications to a specific "driver" or context object.
	It cannot act alone, but works in concert with the CompactDFA (above) and the generic scan algorithm.
	"""
	def __init__(self, *, action:dict, driver:object):
		
		def bind(message, parameter):
			method_name = 'scan_' + message
			try: fn = getattr(driver, method_name)
			except AttributeError:
				if default_method is None:
					raise interfaces.MetaError("Scanner driver has neither method %r nor %r."%(method_name, default_method_name))
				else:
					fn = functools.partial(default_method, message)
					method_name = "%s(%r, ...)"%(default_method_name, message)
			arity = len(inspect.signature(fn).parameters)
			if arity == 1:
				if parameter is None: return fn
				else: raise interfaces.MetaError("Message %r is used with parameter %r but handler %r only takes one argument (the scan state) and needs to take a second (the message parameter)."%(message, parameter, method_name))
			elif arity == 2: return lambda scan_state: fn(scan_state, parameter)
			else: raise interfaces.MetaError("Scan handler %r takes %d arguments, but needs to take %s."%(method_name, arity, ['two', 'one or two'][parameter is None]))
		
		default_method_name = 'default_scan_action'
		default_method = getattr(driver, default_method_name, None)
		self._trail       = action['trail']
		self._line_number = action['line_number']
		self.__methods = list(map(bind, action['message'], action['parameter']))
		self.get_trailing_context = self._trail.__getitem__
		
	def get_trailing_context(self, rule_id: int):
		""" NB: This gets overwritten by a direct bound-method on the trailing-context list. """
		return self._trail[rule_id]
	
	def invoke(self, scan_state: ScanState, rule_id:int): return self.__methods[rule_id](scan_state)

def mangle(message):
	""" Describes the relation between parse action symbols (from parse rule data) to driver method names. """
	if message is None: return None
	if message.startswith(':'): return 'action_'+message[1:]
	return 'parse_'+message

class CompactHandleFindingAutomaton(interfaces.ParseTable):
	"""
	This implements the ParseTable interface (for use with the generic parse algorithm)
	by reference to a set of parser tables that have been built using the MacroParse machinery.
	It's not the whole story: the function `symbolic_reducer(driver)` is involved to build a
	"combiner" function which the parse algorithm then uses for semantic reductions.
	"""
	def __init__(self, parser:dict):
		self.get_action, self.interactive_step = parser_action_function(**parser['action'])
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

def parse_action_bindings(driver):
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
	Builds and returns a function for parsing texts based on a set of tables and supplied drivers.
	
	It is simple in that it uses the simple version of the parse algorithm which means at most one
	token per scan pattern match. That is fine for many applications.
	
	To facilitate error reporting and lexical tie-ins, the returned function supplies a custom
	attribute (called `.scanner`) which exposes the current state of the scanner. Thus, you can
	catch any old exception and see where in some input-text things went pear-shaped.
	
	PS: Yes, Virginia. Lexical closures ARE magical!
	
	:param tables: Generally the output of boozetools.macroparse.compiler.compile_file, but maybe deserialized.
	:param scan_driver: needs .scan_foo(...) methods.
	:param parse_driver: needs .parse_foo(...) methods. This may be the same object as scan_driver.
	:param start: Optionally, the start-state for the scanner DFA.
	:param language: Optionally, the start-symbol for the parser.
	:param interactive: True if you want the parser to opportunistically reduce whenever lookahead would not matter.
	:return: a callable object.
	"""
	scan = simple_scanner(tables, scan_driver, start=start)
	parse = simple_parser(tables, parse_driver, language=language, interactive=interactive)
	def fn(text):
		nonlocal fn
		fn.scanner = scan(text)
		return parse(fn.scanner)
	return fn

def simple_scanner(tables, scan_driver, *, start='INITIAL'):
	"""
	Builds and returns a function which converts strings into a token-iterators by way of
	the algorithms.Scanner class and your provided scan_driver object. It's the
	same driver object for every scan, so any sequencing discipline is up to you.
	
	:param tables: Generally the output of boozetools.macroparse.compiler.compile_file, but maybe deserialized.
	:param driver: needs .scan_foo(...) methods.
	"""
	scanner_tables = tables['scanner']
	dfa = CompactDFA(dfa=scanner_tables['dfa'], alphabet=scanner_tables['alphabet'])
	rules = BoundScanRules(action=scanner_tables['action'], driver=scan_driver)
	return lambda text: algorithms.Scanner(text=text, automaton=dfa, rules=rules, start=start)

def simple_parser(tables, parse_driver, *, language=None, interactive=False):
	"""
	Builds and returns a function which converts a stream of tokens into a semantic value
	by way of the algorithms.parse(...) function and your provided driver. It's the same
	driver object for each parse, so any sequencing discipline is up to you.

	:param tables: Generally the output of boozetools.macroparse.compiler.compile_file, but maybe deserialized.
	:param driver: needs .parse_foo(...) methods.
	"""
	hfa = CompactHandleFindingAutomaton(tables['parser'])
	combine = parse_action_bindings(parse_driver)
	return lambda each_token: algorithms.parse(hfa, combine, each_token, language=language, interactive=interactive)
