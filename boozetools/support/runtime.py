"""
This module may still be doing too many different things. I'll probably break it up further in the future.

1. It supplies one means to bind rule-actions to driver-objects. (It would be nice to support a few more styles.)
2. It provides a (maybe) convenient runtime interface to the most common use cases.
"""

import inspect, functools, sys

from . import interfaces, expansion, failureprone
from ..scanning import recognition
from ..parsing import shift_reduce

class BoundScanRules:
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

	def invoke(self, yy: interfaces.Scanner, rule_id:int):
		trail = self._trail[rule_id]
		if trail is not None: yy.less(trail)
		return self.__methods[rule_id](yy)

class AbstractTypical(interfaces.ScanErrorListener, interfaces.ParseErrorListener):
	"""
	Many applications have similar requirements for error reporting and recovery.
	I'd like to be able to provide a common basis of reasonable default behavior
	for applications that involve both scanning and parsing, regardless of whether
	those applications are founded on the 'mini' or the 'macro' framework.
	
	Specialized versions of this class support either of the two frameworks.
	
	THIS MAY SEEM like a method-as-object (anti)pattern. However, the real
	point is a whole mess of configuration and cooperation in one place.
	"""
	
	source: failureprone.SourceText
	yy: interfaces.Scanner
	exception: Exception
	
	def __init__(self, *, dfa: interfaces.FiniteAutomaton, act: interfaces.ScanActor, hfa:interfaces.ParseTable, combine):
		self.__dfa = dfa
		self.__act = act
		self.__hfa = hfa
		self.__combine = combine
	
	def parse(self, text: str, *, line_breaks='normal', filename: str = None, start=None, language=None):
		if start is None: start = interfaces.DEFAULT_INITIAL_CONDITION
		self.source = failureprone.SourceText(text, line_breaks=line_breaks, filename=filename)
		self.yy = recognition.IterableScanner(text=text, automaton=self.__dfa, act=self.__act, start=start, on_error=self)
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
	
	def exception_parsing(self, ex: Exception, message, args):
		self.source.complain(*self.yy.current_span(), message="During " + repr(message))
		raise ex from None
	
	def unexpected_character(self, yy: interfaces.Scanner):
		self.source.complain(yy.current_position(), message="Lexical scan got stuck.")
	
	def exception_scanning(self, yy:interfaces.Scanner, rule_id:int, ex:Exception):
		self.source.complain(*yy.current_span())
		raise ex from None


class TypicalApplication(AbstractTypical):
	"""
	This class specializes for the case of compiled tables such as from MacroParse,
	to provide reasonable default error handling behavior.
	"""
	
	def __init__(self, tables):
		assert list(tables.get('version', [])) == [0,0,1], 'Data table version mismatch: '+repr(tables.get('version'))
		scanner_tables = tables['scanner']
		hfa = expansion.CompactHandleFindingAutomaton(tables['parser'])
		super().__init__(
			dfa = expansion.CompactDFA(dfa=scanner_tables['dfa'], alphabet=scanner_tables['alphabet']),
			act = BoundScanRules(action=scanner_tables['action'], driver=self).invoke,
			hfa = hfa,
			combine = parse_action_bindings(self, hfa.message_catalog)
		)


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
			y = ex # Apparently Py3.8 doesn't close over exception objects unless you assign them.
			def fail(*items): raise y
			return fail
	dispatch = [bind(message) for message in message_catalog]
	def combine(cid:int, args):
		message = dispatch[cid]
		if message is None: return tuple(args) # The null check is like one bytecode and very fast.
		return message(*args)
	return combine

