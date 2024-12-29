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
from ..parsing.interface import END_OF_TOKENS, ParseErrorListener, UnexpectedTokenError, SemanticError
from ..scanning.interface import INITIAL, Bindings, RuleId, ScannerBlocked
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

def upgrade_tables_in_place(tables):
	"""
	The compact-table format has changed once or twice in booze-tools history.
	This routine compensates for the possibility of some older format living
	on disk while a newer version of the package is in use.
	"""
	def version(): return tuple(tables.get('version', ()))
	if version() == (0, 0, 1): _upgrade_table_0_0_1(tables)
	if version() == (0, 0, 2): _upgrade_table_0_0_2(tables)
	if version() != (0, 0, 3):
		raise ValueError('Installed package cannot understand table version: ' + repr(version()))

class TypicalApplication(ParseErrorListener):
	"""
	This class aims to provide a common basis of reasonable default behavior
	for typical MacroParse applications, yet remain easy to customize as you
	add more sophisticated requirements.
	
	Consider using the make_tables(...) routine (defined below) to build
	tables on-demand and store them next to the grammar definition file.

	THIS MAY SEEM like a method-as-object (anti)pattern. However, the real
	point is a whole mess of configuration and cooperation in one place.
	"""
	
	def __init__(self, tables):
		upgrade_tables_in_place(tables)
		scanner_table = tables['scanner']
		self.dfa = expansion.CompactDFA(dfa=scanner_table['dfa'], alphabet=scanner_table['alphabet'])
		each_action = expansion.scan_actions(scanner_table['action'])
		self.__bindings = self.bind_scan_actions(each_action)
		
		parser_table = tables['parser']
		self.hfa = expansion.CompactHFA(parser_table)
		self.__combine = self.bind_parse_actions(self.hfa.each_constructor())
	
	def bind_scan_actions(self, each_action: Iterable[ScanAction]):
		return MacroScanBindings(self, each_action)
	
	def bind_parse_actions(self, each_constructor: Iterable[tuple[Any, set[int]]]):
		return parse_action_bindings(self, each_constructor)
	
	source: failureprone.SourceText
	yy: IterableScanner
	exception: Exception
	
	def parse(self, text: str, *, line_breaks='normal', filename: str = None, start=None, language=None):
		if start is None: start = INITIAL
		self.source = failureprone.SourceText(text, line_breaks=line_breaks, filename=filename)
		self.yy = IterableScanner(text, self.dfa, self.__bindings, start=start)
		return shift_reduce.parse(self.hfa, self.__combine, self.yy, language=language, on_error=self)
	
	@staticmethod
	def log_error(*parts):
		""" Simple place to override if you'd rather use a logging framework. """
		print(*parts, file=sys.stderr)
	
	def unexpected_token(self, kind, semantic, pds):
		self.log_error(self.source.complaint(self.yy.slice(), message="Unexpected token %r" % kind))
		self.exception = UnexpectedTokenError(kind, semantic, pds)
		self.log_error("Parsing condition was:\n", self.stack_symbols(pds))
		self.log_error("Expected:", self.expected_tokens(pds))
	
	def expected_tokens(self, pds) -> list[str]:
		"""
		Handy for generating informative parse-error messages.
		
		This may behave imperfectly with LALR tables, for they lack the
		immediate-error-detection property which LR(1)-style tables have.
		LALR may indicate reductions which, once performed, lead back to
		an error state. You could work around this deficiency, but you
		are better off just using (minimal) LR(1).
		"""
		return sorted(self.hfa.expected_terminals_at_state(pds.state))
	
	def stack_symbols(self, pds) -> list[str]:
		return list(map(self.hfa.get_breadcrumb, pds.path_from_root()))[1:]
	
	def unexpected_eof(self, pds):
		self.unexpected_token(END_OF_TOKENS, None, pds)
	
	def will_recover(self, tokens):
		if len(tokens) >= 3: self.log_error("Trying to recover.")
		
	def did_not_recover(self):
		self.log_error("Could not recover.")
		raise self.exception
	
	def exception_parsing(self, ex: Exception, constructor_id:int, args):
		message = self.hfa.get_constructor(constructor_id)
		self.log_error(self.source.complaint(self.yy.slice(), message="Exception during " + repr(message)))
		raise ex from None
	
	def on_stuck(self, yy: IterableScanner):
		self.log_error(self.source.complaint(yy.slice(), message="Lexical scan got stuck in condition %r."%yy.condition))
		raise ScannerBlocked(yy.left, yy.condition)
	
	def exception_scanning(self, yy:IterableScanner, rule_id:int, ex:Exception):
		self.log_error(self.source.complaint(yy.slice(), "Recognizing"))
		raise ex from None

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
