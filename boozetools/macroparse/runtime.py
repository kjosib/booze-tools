"""
This module may still be doing too many different things. I'll probably break it up further in the future.

1. It supplies one means to bind rule-actions to driver-objects. (It would be nice to support a few more styles.)
2. It provides a (maybe) convenient runtime interface to the most common use cases.
"""

import functools, sys
from typing import Iterable, Any

from ..support import failureprone
from . import expansion
from ..parsing import shift_reduce
from ..parsing.interface import HandleFindingAutomaton, END_OF_TOKENS, ParseErrorListener, UnexpectedTokenError, SemanticError
from ..scanning.interface import FiniteAutomaton, INITIAL, Bindings, RuleId, ScannerBlocked
from ..scanning.engine import IterableScanner
from .interface import ScanAction

class MissingMethodError(TypeError):
	pass

class MacroScanBindings(Bindings):
	def __init__(self, driver, each_action:Iterable[ScanAction]):
		def bind(act:ScanAction):
			message_name, *args = act.message
			method_name = 'scan_' + message_name
			try: fn = getattr(driver, method_name)
			except AttributeError:
				if default: fn = functools.partial(default, message_name)
				else: raise MissingMethodError(method_name, act.line_number)
			return act.right_context, fn, args
		default = getattr(driver, 'default_scan_action', None)
		self.__rule = [bind(act) for act in each_action]
		if hasattr(driver, "on_stuck"):
			self.__on_stuck = driver.on_stuck
		else:
			self.__on_stuck = super().on_stuck
	
	def on_match(self, yy, rule_id: RuleId):
		right_context, fn, args = self.__rule[rule_id]
		yy.less(right_context)
		fn(yy, *args)
	
	def on_stuck(self, yy):
		return self.__on_stuck(yy)


def parse_action_bindings(driver, each_constructor:Iterable[tuple[Any, set[int]]]):
	"""
	Build a reduction function (combiner) for the parse engine out of an arbitrary Python object.
	Because this checks the message catalog it can be sure the method lookup will never fail.
	"""
	def bind(constructor, mentions:set[int]):
		if constructor is None: return None
		is_mid_rule_action = constructor.startswith(':')
		kind, constructor = ('mid_rule', constructor[1:]) if is_mid_rule_action else ('parse', constructor)
		specific = kind + '_' + constructor
		try: return getattr(driver, specific)
		except AttributeError:
			generic = 'default_'+kind
			try: method = getattr(driver, generic)
			except AttributeError: raise MissingMethodError(specific, min(mentions))
			else: return functools.partial(method, constructor)
	dispatch = [bind(constructor, mentions) for constructor, mentions in each_constructor]
	def combine(cid:int, args):
		message = dispatch[cid]
		if message is None: return tuple(args) # The null check is like one bytecode and very fast.
		try: return message(*args)
		except SemanticError as ex:
			raise ex from None
		except Exception as ex:
			driver.exception_parsing(ex, cid, args)
	return combine


class AbstractTypical(ParseErrorListener):
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
	yy: IterableScanner
	exception: Exception
	
	def __init__(self, *, dfa: FiniteAutomaton, bindings, hfa:HandleFindingAutomaton, combine):
		self.__dfa = dfa
		self.__bindings = bindings
		self.__hfa = hfa
		self.__combine = combine
	
	def parse(self, text: str, *, line_breaks='normal', filename: str = None, start=None, language=None):
		if start is None: start = INITIAL
		self.source = failureprone.SourceText(text, line_breaks=line_breaks, filename=filename)
		self.yy = IterableScanner(text, self.__dfa, self.__bindings, start=start)
		return shift_reduce.parse(self.__hfa, self.__combine, self.yy, language=language, on_error=self)
	
	def unexpected_token(self, kind, semantic, pds):
		self.source.complain(self.yy.slice(), message="Unexpected token %r" % kind)
		stack_symbols = list(map(self.__hfa.get_breadcrumb, pds.path_from_root()))[1:]
		self.exception = UnexpectedTokenError(kind, semantic, pds)
		print("Parsing condition was:\n", stack_symbols, file=sys.stderr)
	
	def unexpected_eof(self, pds):
		self.unexpected_token(END_OF_TOKENS, None, pds)
	
	def will_recover(self, tokens):
		if len(tokens) >= 3: print("Trying to recover.", file=sys.stderr)
		
	def did_not_recover(self):
		print("Could not recover.", file=sys.stderr)
		raise self.exception
	
	def exception_parsing(self, ex: Exception, constructor_id:int, args):
		message = self.__hfa.get_constructor(constructor_id)
		self.source.complain(self.yy.slice(), message="Exception during " + repr(message))
		raise ex from None
	
	def on_stuck(self, yy: IterableScanner):
		self.source.complain(yy.slice(), message="Lexical scan got stuck in condition %r."%yy.condition)
		raise ScannerBlocked(yy.left, yy.condition)
	
	def exception_scanning(self, yy:IterableScanner, rule_id:int, ex:Exception):
		self.source.complain(yy.slice(), "Recognizing")
		raise ex from None

def _upgrade_table_0_0_1(tables):
	action = tables['scanner']['action']
	action['argument'] = action.pop('parameter')
	tables['version'] = (0,0,2)

def _upgrade_table_0_0_2(tables):
	action = tables['scanner']['action']
	action['right_context'] = action.pop("trail")
	message = [[m] for m in action['message']]
	for m,a in zip(message, action.pop('argument')):
		if a is not None:
			m.append(a)
	action['message'] = message
	tables['version'] = (0,0,3)

class TypicalApplication(AbstractTypical):
	"""
	This class specializes for the case of compiled tables such as from MacroParse,
	to provide reasonable default error handling behavior.
	"""
	
	def __init__(self, tables, strict=True):
		def version(): return tuple(tables.get('version', ()))
		if version() == (0, 0, 1): _upgrade_table_0_0_1(tables)
		if version() == (0, 0, 2): _upgrade_table_0_0_2(tables)
		if version() != (0, 0, 3):
			raise ValueError('Installed package cannot understand table version: ' + repr(version()))
		
		scanner_table = tables['scanner']
		each_action = expansion.scan_actions(scanner_table['action'])
		dfa = expansion.CompactDFA(dfa=scanner_table['dfa'], alphabet=scanner_table['alphabet'])
		bindings = self.bind_scan_actions(each_action)
		
		parser_table = tables['parser']
		hfa = expansion.CompactHFA(parser_table)
		combine = self.bind_parse_actions(hfa.each_constructor())
		
		super().__init__(dfa=dfa, bindings=bindings, hfa=hfa, combine=combine)

	def bind_scan_actions(self, each_action:Iterable[ScanAction]):
		return MacroScanBindings(self, each_action)
	
	def bind_parse_actions(self, each_constructor:Iterable[tuple[Any, set[int]]]):
		return parse_action_bindings(self, each_constructor)

def make_tables(source_path, target_path=None):
	import json, os.path
	stem, extension = os.path.splitext(source_path)
	target_path = target_path or stem+'.automaton'
	if os.path.exists(source_path):
		if (not os.path.exists(target_path)) or (os.stat(target_path).st_mtime < os.stat(source_path).st_mtime):
			from .compiler import compile_file
			tables = compile_file(source_path)
			with open(target_path, 'w') as ofh:
				json.dump(tables, ofh, separators=(',', ':'), sort_keys=True)
	with open(target_path, "r") as fh:
		return json.load(fh)
