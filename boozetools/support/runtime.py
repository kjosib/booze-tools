"""
This module may still be doing too many different things. I'll probably break it up further in the future.

1. It supplies one means to bind rule-actions to driver-objects. (It would be nice to support a few more styles.)
2. It provides a (maybe) convenient runtime interface to the most common use cases.
"""

import inspect, functools, sys

from . import interfaces, expansion, failureprone
from ..scanning import recognition
from ..parsing import shift_reduce


class BoundScanRules(interfaces.ScanRules):
	"""
	This binds symbolic scan-action specifications to a specific "driver" or
	context object. It cannot act alone, but works in concert with the
	CompactDFA (in module support.expansion) and the generic scan algorithm.
	
	Also, it needs to be more like parse_action_bindings, not a class.
	"""
	def __init__(self, *, action:dict, driver:object):
		
		def bind(message, parameter):
			method_name = 'scan_' + message
			if hasattr(driver, method_name):
				fn = getattr(driver, method_name)
			elif default_method is None:
				raise ValueError("IterableScanner driver has neither method %r nor %r." % (method_name, default_method_name))
			else:
				fn = functools.partial(default_method, message)
				method_name = "%s(%r, ...)"%(default_method_name, message)
			arity = len(inspect.signature(fn).parameters)
			if arity == 1:
				if parameter is None: return fn
				else: raise ValueError("Message %r is used with parameter %r but handler %r only takes one argument (the scan state) and needs to take a second (the message parameter)." % (message, parameter, method_name))
			elif arity == 2: return lambda scan_state: fn(scan_state, parameter)
			else: raise ValueError("Scan handler %r takes %d arguments, but needs to take %s." % (method_name, arity, ['two', 'one or two'][parameter is None]))
		
		default_method_name = 'default_scan_action'
		default_method = getattr(driver, default_method_name, None)
		self._trail       = action['trail']
		self._line_number = action['line_number']
		self.__methods = list(map(bind, action['message'], action['parameter']))
		self.get_trailing_context = self._trail.__getitem__
		
	def get_trailing_context(self, rule_id: int):
		""" NB: This gets overwritten by a direct bound-method on the trailing-context list. """
		return self._trail[rule_id]
	
	def invoke(self, scan_state: interfaces.Scanner, rule_id:int):
		return self.__methods[rule_id](scan_state)

class TypicalApplication(interfaces.ScanErrorListener, interfaces.ParseErrorListener):
	"""
	This class aims to provide a simple basis for extension and reasonable
	defaults for a variety of common parsing applications. Those with unusual
	requirements should consider taking this to bits.
	
	THIS MAY SEEM like a method-as-object (anti)pattern. HOWEVER, the real
	point is a whole mess of configuration and cooperation in one place.
	"""
	
	source: failureprone.SourceText
	yy: interfaces.Scanner
	exception: Exception
	
	def __init__(self, tables):
		assert list(tables.get('version', [])) == [0,0,1], 'Data table version mismatch: '+repr(tables.get('version'))
		scanner_tables = tables['scanner']
		self.__dfa = expansion.CompactDFA(dfa=scanner_tables['dfa'], alphabet=scanner_tables['alphabet'])
		self.__rules = BoundScanRules(action=scanner_tables['action'], driver=self)
		self.__hfa = expansion.CompactHandleFindingAutomaton(tables['parser'])
		self.__combine = parse_action_bindings(self, self.__hfa.message_catalog)
	
	def parse(self, text: str, *, line_breaks='normal', filename: str = None, start=None, language=None):
		if start is None: start = interfaces.DEFAULT_INITIAL_CONDITION
		self.source = failureprone.SourceText(text, line_breaks=line_breaks, filename=filename)
		self.yy = recognition.IterableScanner(text=text, automaton=self.__dfa, rules=self.__rules, start=start, on_error=self)
		return shift_reduce.parse(self.__hfa, self.__combine, self.yy, language=language, on_error=self)
	
	def unexpected_token(self, kind, semantic, pds):
		self.source.complain(*self.yy.current_span(), message="Unexpected token %r" % kind)
		# stack_symbols = list(map(self.table.get_breadcrumb, pds.path_from_root()))[1:]
		# self.exception = interfaces.ParseError(stack_symbols, kind, semantic)
		# print("Parsing condition was:\n", self.exception.condition(), file=sys.stderr)
	
	def unexpected_eof(self, pds):
		self.unexpected_token(interfaces.END_OF_TOKENS, None, pds)
	
	def will_recover(self, tokens):
		if len(tokens) >= 3: print("Trying to recover.", file=sys.stderr)
		
	def did_not_recover(self):
		print("Could not recover.", file=sys.stderr)
	
	def rule_exception(self, ex: Exception, message, args):
		self.source.complain(*self.yy.current_span(), message="During " + repr(message))
		raise ex from None
	
	# TODO: By the way, it's no longer clear the scanner should pass `self` as a parameter.
	
	def scan_blocked(self, yy: interfaces.Scanner):
		self.source.complain(yy.current_position(), "Lexical scan got stuck.")
	
	def scan_exception(self, yy:interfaces.Scanner, rule_id:int, ex:Exception):
		self.source.complain(*yy.current_span())
		raise ex from None


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
		except AttributeError as ex:
			def fail(*items): raise ex
			return fail
	dispatch = [bind(message) for message in message_catalog]
	def combine(cid:int, args):
		message = dispatch[cid]
		if message is None: return tuple(args) # The null check is like one bytecode and very fast.
		return message(*args)
	return combine

