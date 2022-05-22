"""
This module may still be doing too many different things. I'll probably break it up further in the future.

1. It supplies one means to bind rule-actions to driver-objects. (It would be nice to support a few more styles.)
2. It provides a (maybe) convenient runtime interface to the most common use cases.
"""

import inspect, functools, sys, warnings
from typing import Callable, Optional, Iterable

from . import interfaces, expansion, failureprone
from ..scanning import recognition
from ..parsing import shift_reduce


class BindErrorListener:
	""" Factors out the details concerning how we report binding problems. """
	def __init__(self, filename, strict):
		self._filename = filename
		self._strict = strict
		
	def _gripe(self, line_number:int, message:str):
		def blame(*args): raise ValueError(full_message)
		full_message = "For %s line %s: %s"%(self._filename, line_number, message)
		if self._strict: raise ValueError(full_message)
		else:
			warnings.warn(full_message)
			return blame
		
	def missing_methods(self, line_number:int, chain:Iterable):
		phrase = ' nor '.join(map(repr, chain))
		return self._gripe(line_number, "driver has neither method %s." % phrase)
	
	def needs_parameter(self, action:interfaces.ScanAction, method_name:str):
		return self._gripe(action.line_number, "driver method %r only accepts the scan state. It needs another parameter for %r."%(method_name, action.argument))
	
	def wrong_scan_arity(self, action:interfaces.ScanAction, method_name:str, arity:int):
		acceptable = ['two', 'one (or perhaps two)'][action.argument is None]
		return self._gripe(action.line_number, "driver method %r takes %d argument(s), but needs to take %s."%(method_name, arity, acceptable))
	
		
def _bind_trail(function, trail):
	# Deal smartly with the common case of no trailing context.
	def trail_binding(yy):
		yy.less(trail)
		return function(yy)
	return function if trail is None else trail_binding

def _make_scan_actor(binding_list:list[Callable]):
	# A separate context unpins left-over garbage in the caller's stack frame.
	return lambda yy, rule_id: binding_list[rule_id](yy)

def _bind_argument(function, argument):
	# Same concept: leave the caller's stack out of the closure.
	return lambda yy: function(yy, argument)

def scan_action_bindings(*, each_action:Iterable[interfaces.ScanAction], driver:object, on_error:BindErrorListener):
	"""
	Bind symbolic scan-action specifications to a specific "driver" or
	context object. It cannot act alone, but works in concert with the
	CompactDFA (in module support.expansion) and the generic scan algorithm.
	"""
	def bind(action):
		method_name = 'scan_' + action.message
		if hasattr(driver, method_name):
			fn = getattr(driver, method_name)
		elif default_method is None:
			fn = on_error.missing_methods(action.line_number, (method_name, default_method_name))
		else:
			fn = functools.partial(default_method, action.message)
			method_name = "%s(%r, ...)"%(default_method_name, action.message)
		arity = len(inspect.signature(fn).parameters)
		if arity == 1:
			if action.argument is None:return fn
			else: return on_error.needs_parameter(action, method_name)
		elif arity == 2: return _bind_argument(fn, action.argument)
		else:
			return on_error.wrong_scan_arity(action, method_name, arity)
		
	default_method_name = 'default_scan_action'
	default_method = getattr(driver, default_method_name, None)
	return _make_scan_actor([_bind_trail(bind(action), action.trail) for action in each_action])


def parse_action_bindings(driver, each_constructor, on_error:BindErrorListener):
	"""
	Build a reduction function (combiner) for the parse engine out of an arbitrary Python object.
	Because this checks the message catalog it can be sure the method lookup will never fail.
	"""
	def bind(constructor, mentions):
		if constructor is None: return None
		is_mid_rule_action = constructor.startswith(':')
		kind, constructor = ('mid_rule', constructor[1:]) if is_mid_rule_action else ('parse', constructor)
		specfic = kind + '_' + constructor
		try: return getattr(driver, specfic)
		except AttributeError:
			generic = 'default_'+kind
			try: method = getattr(driver, generic)
			except AttributeError: return on_error.missing_methods(min(mentions), (specfic, generic))
			else: return functools.partial(method, constructor)
	dispatch = [bind(constructor, mentions) for constructor, mentions in each_constructor]
	def combine(cid:int, args):
		message = dispatch[cid]
		if message is None: return tuple(args) # The null check is like one bytecode and very fast.
		return message(*args)
	return combine


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
	
	def __init__(self, *, dfa: interfaces.FiniteAutomaton, act: interfaces.ScanActor, hfa:interfaces.HandleFindingAutomaton, combine):
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

def _upgrade_table_0_0_1(tables):
	assert tables['version'] == (0,0,1), tables['version']
	action = tables['scanner']['action']
	action['argument'] = action.pop('parameter')
	tables['version'] = (0,0,2)

class TypicalApplication(AbstractTypical):
	"""
	This class specializes for the case of compiled tables such as from MacroParse,
	to provide reasonable default error handling behavior.
	"""
	
	def __init__(self, tables, strict=True):
		def version(): return tuple(tables.get('version', ()))
		if version() == (0, 0, 1): _upgrade_table_0_0_1(tables)
		if version() != (0, 0, 2):
			raise ValueError('Installed package cannot understand table version: ' + repr(version()))
		
		on_error = BindErrorListener(tables['source'], strict=strict)

		scanner_table = tables['scanner']
		each_action = expansion.scan_actions(scanner_table['action'])
		dfa = expansion.CompactDFA(dfa=scanner_table['dfa'], alphabet=scanner_table['alphabet'])
		act = scan_action_bindings(each_action=each_action, driver=self, on_error=on_error)
		
		parser_table = tables['parser']
		hfa = expansion.CompactHFA(parser_table)
		combine = parse_action_bindings(self, hfa.each_constructor(), on_error)
		
		super().__init__(dfa=dfa, act=act, hfa=hfa, combine=combine)

