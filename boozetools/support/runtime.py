"""
This module may still be doing too many different things. I'll probably break it up further in the future.

1. It supplies one means to bind rule-actions to driver-objects. (It would be nice to support a few more styles.)
2. It provides a (maybe) convenient runtime interface to the most common use cases.
"""

import inspect, functools, sys

from boozetools.support.interfaces import Scanner

from . import interfaces, expansion, failureprone
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
					raise interfaces.DriverError("IterableScanner driver has neither method %r nor %r." % (method_name, default_method_name))
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
		if hasattr(driver, 'blocked_scan'): self.blocked = driver.blocked_scan
		
	def get_trailing_context(self, rule_id: int):
		""" NB: This gets overwritten by a direct bound-method on the trailing-context list. """
		return self._trail[rule_id]
	
	def invoke(self, scan_state: interfaces.Scanner, rule_id:int):
		try: return self.__methods[rule_id](scan_state)
		except interfaces.LanguageError: raise
		except Exception as e: raise interfaces.DriverError("Trying to scan rule "+str(rule_id)) from e

class TypicalErrorChannel(interfaces.ErrorChannel):
	def __init__(self, table:interfaces.ParseTable, scanner:interfaces.Scanner, source:failureprone.SourceText):
		self.table = table
		self.scanner = scanner
		self.source = source
		self.exception = None
	
	def unexpected_token(self, kind, semantic, pds):
		self.source.complain(*self.scanner.current_span(), message="Unexpected token %r"%kind)
		# stack_symbols = list(map(self.table.get_breadcrumb, pds.path_from_root()))[1:]
		# self.exception = interfaces.ParseError(stack_symbols, kind, semantic)
		# print("Parsing condition was:\n", self.exception.condition(), file=sys.stderr)
	
	def unexpected_eof(self, pds):
		self.unexpected_token(interfaces.END_OF_TOKENS, None, pds)
	
	def will_recover(self, tokens):
		self.source.complain(*self.scanner.current_span(), message="Recovered parsing approximately here:")
		
	def did_not_recover(self):
		print("Could not recover.", file=sys.stderr)
		# raise self.exception
	
	def cannot_recover(self):
		self.did_not_recover()
	
	def scan_exception(self, e: Exception):
		self.source.complain(*self.scanner.current_span())
		raise e
	
	def rule_exception(self, e: Exception, message, args):
		self.source.complain(*self.scanner.current_span(), message="During "+repr(message))
		raise e


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
		return message(*args)
	return combine

def the_simple_case(tables, scan_driver, parse_driver, *, start='INITIAL', language=None, on_error=TypicalErrorChannel):
	"""
	Builds and returns a function for parsing texts based on a set of tables and supplied drivers.
	For now it's the same driver object if you call the resulting parser multiple times.
	
	PS: Yes, Virginia. Lexical closures ARE magical!
	
	:param tables: Generally the output of boozetools.macroparse.compiler.compile_file, but maybe deserialized.
	:param scan_driver: needs .scan_foo(...) methods.
	:param parse_driver: needs .parse_foo(...) methods. This may be the same object as scan_driver.
	:param start: Optionally, the start-state for the scanner DFA.
	:param language: Optionally, the start-symbol for the parser.
	:return: a callable object.
	"""
	scanner_tables = tables['scanner']
	dfa = expansion.CompactDFA(dfa=scanner_tables['dfa'], alphabet=scanner_tables['alphabet'])
	rules = BoundScanRules(action=scanner_tables['action'], driver=scan_driver)
	hfa = expansion.CompactHandleFindingAutomaton(tables['parser'])
	combine = parse_action_bindings(parse_driver, hfa.message_catalog)
	def parse(text:str, line_breaks='normal', filename:str=None):
		source = failureprone.SourceText(text, line_breaks=line_breaks, filename=filename)
		scanner = recognition.IterableScanner(text=source.content, automaton=dfa, rules=rules, start=start or dfa.default_initial_condition())
		error_channel = on_error(hfa, scanner, source)
		return shift_reduce.parse(hfa, combine, scanner, language=language, error_channel=error_channel)
	return parse

