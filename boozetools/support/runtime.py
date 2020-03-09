"""
This module may still be doing too many different things. I'll probably break it up further in the future.

1. It supplies one means to bind rule-actions to driver-objects. (It would be nice to support a few more styles.)
2. It provides a (maybe) convenient runtime interface to the most common use cases.
"""

import inspect, functools
from . import interfaces, expansion
from ..scanning import recognition
from ..parsing import shift_reduce


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
					raise interfaces.DriverError("Scanner driver has neither method %r nor %r." % (method_name, default_method_name))
				else:
					fn = functools.partial(default_method, message)
					method_name = "%s(%r, ...)"%(default_method_name, message)
			arity = len(inspect.signature(fn).parameters)
			if arity == 1:
				if parameter is None: return fn
				else: raise interfaces.DriverError("Message %r is used with parameter %r but handler %r only takes one argument (the scan state) and needs to take a second (the message parameter)." % (message, parameter, method_name))
			elif arity == 2: return lambda scan_state: fn(scan_state, parameter)
			else: raise interfaces.DriverError("Scan handler %r takes %d arguments, but needs to take %s." % (method_name, arity, ['two', 'one or two'][parameter is None]))
		
		default_method_name = 'default_scan_action'
		default_method = getattr(driver, default_method_name, None)
		self._trail       = action['trail']
		self._line_number = action['line_number']
		self.__methods = list(map(bind, action['message'], action['parameter']))
		self.get_trailing_context = self._trail.__getitem__
		
	def get_trailing_context(self, rule_id: int):
		""" NB: This gets overwritten by a direct bound-method on the trailing-context list. """
		return self._trail[rule_id]
	
	def invoke(self, scan_state: interfaces.ScanState, rule_id:int):
		try: return self.__methods[rule_id](scan_state)
		except interfaces.LanguageError: raise
		except Exception as e: raise interfaces.DriverError("Trying to scan rule "+str(rule_id)) from e

def parse_action_bindings(driver, message_catalog):
	"""
	Build a reduction function (combiner) for the parse engine out of an arbitrary Python object.
	Because this checks the message catalog it can be sure the method lookup will never fail.
	"""
	assert isinstance(message_catalog, list), type(message_catalog)
	def bind(message):
		if message is None: return None
		attr = 'action_' + message[1:] if message.startswith(':') else 'parse_' + message
		try: return getattr(driver, attr)
		except AttributeError:
			def fail(*items): raise interfaces.DriverError("No such method %r on driver" % attr)
			return fail
	dispatch = [bind(message) for message in message_catalog]
	def combine(cid:int, args):
		message = dispatch[cid]
		if message is None: return tuple(args) # The null check is like one bytecode and very fast.
		try: return message(*args)
		except Exception as e:
			raise interfaces.DriverError("while parsing "+repr(message), list(map(type, args))) from e
	return combine

def the_simple_case(tables, scan_driver, parse_driver, *, start='INITIAL', language=None):
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
	:return: a callable object.
	"""
	scan = simple_scanner(tables, scan_driver, start=start)
	parse = simple_parser(tables, parse_driver, language=language)
	def fn(text):
		nonlocal fn
		fn.scanner = scan(text)
		return parse(fn.scanner)
	return fn

def simple_scanner(tables, scan_driver, *, start=None):
	"""
	Builds and returns a function which converts strings into a token-iterators by way of
	the algorithms.Scanner class and your provided scan_driver object. It's the
	same driver object for every scan, so any sequencing discipline is up to you.
	
	:param tables: Generally the output of boozetools.macroparse.compiler.compile_file, but maybe deserialized.
	:param driver: needs .scan_foo(...) methods.
	"""
	scanner_tables = tables['scanner']
	dfa = expansion.CompactDFA(dfa=scanner_tables['dfa'], alphabet=scanner_tables['alphabet'])
	rules = BoundScanRules(action=scanner_tables['action'], driver=scan_driver)
	return lambda text: recognition.Scanner(text=text, automaton=dfa, rules=rules, start=start or dfa.default_initial_condition())

def simple_parser(tables, parse_driver, *, language=None):
	"""
	Builds and returns a function which converts a stream of tokens into a semantic value
	by way of the algorithms.parse(...) function and your provided driver. It's the same
	driver object for each parse, so any sequencing discipline is up to you.

	:param tables: Generally the output of boozetools.macroparse.compiler.compile_file, but maybe deserialized.
	:param driver: needs .parse_foo(...) methods.
	"""
	hfa = expansion.CompactHandleFindingAutomaton(tables['parser'])
	combine = parse_action_bindings(parse_driver, hfa.message_catalog)
	return lambda each_token: shift_reduce.parse(hfa, combine, each_token, language=language)
