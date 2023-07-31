"""
This module implements the macro-enabled enhanced-BNF context-free grammar semantics.
There is exactly zero concern for where the production rules come from.

Because the production rules support a no-kidding macro language, this module gets a
good bit of hair all by itself.

The MetaParse definition object works with structured rewriting-rule objects, so this
file begins with definitions of some semantic objects. Next come a grammar and scanner
(implemented via the "mini" infrastructure) which build those semantics up. Last is a
class definition for a grammar object which supplies the necessary bits to make
the extensions over BNF work properly.
"""
import string
import sys
from typing import List
from ..parsing.interface import ERROR_SYMBOL, SemanticError
from ..scanning import miniscan
from ..scanning.interface import ScannerBlocked
from ..parsing import context_free, miniparse
from ..parsing.interface import ParseError
from ..parsing.all_methods import PARSE_TABLE_METHODS
from ..support.failureprone import illustration

NONDET = object()
NONSTRICT = object()
METHOD = object()
VOID = object()
VOID_SET = object()

SET_PATTERNS = {
	"upper" : lambda x: x.isalpha() and x.isupper(),
	"lower" : lambda x: x.isalpha() and x.islower(),
	"punct" : lambda x: all(c in string.punctuation for c in x),
}

class DefinitionError(SemanticError): pass

### Semantic categories for the breakdown of rewrite rules:
class Action:
	def __init__(self, name): self.name = name

class Element:
	"""
	Base class of RHS elements.
	What you do NOT see here is reflected in the constructor for class Rewrite:
		Specifically, any Element may have a 'capture' attribute added; this makes the value
		available to any action to its right.
		Please note: 'capturing' a rule-final action makes no sense and is presently ignored.
	"""
	def implement(self, ebnf:"EBNF_Definition", head:str, bindings:dict) -> str:
		""" Interpreting the MacroParse EBNF variant now seems to require a proper environment... """
		raise NotImplementedError(type(self))
	
	def is_void_for(self, ebnf:"EBNF_Definition", head: str) -> bool:
		raise NotImplementedError(type(self))

class Symbol(Element):
	def __init__(self, name): self.name = name
	
	def implement(self, ebnf: "EBNF_Definition", head: str, bindings: dict) -> str:
		return head if self.name == '_' else bindings.get(self.name, self.name)
	
	def is_void_for(self, ebnf: "EBNF_Definition", head: str) -> bool:
		key = head if self.name == '_' else self.name
		return ebnf.is_symbol_void(key)


class InlineRenaming(Element):
	def __init__(self, alternatives):
		self.alternatives = tuple(alternatives)
		for a in self.alternatives: assert isinstance(a, Element) and not isinstance(a, Action)
	
	def implement(self, ebnf: "EBNF_Definition", head: str, bindings: dict) -> str:
		alts = [a.implement(ebnf, head, bindings) for a in self.alternatives]
		symbol = "[%s]"%("|".join(alts))
		if ebnf.implementing(symbol):
			for a in alts:
				ebnf.plain_cfg.add_rule(context_free.Rule(
					lhs = symbol,
					rhs = (a,),
					prec_sym=None,
					action=0,
					provenance=None,
				))
		return symbol
	
	def is_void_for(self, ebnf: "EBNF_Definition", head: str) -> bool:
		return all(a.is_void_for(ebnf, head) for a in self.alternatives)

class MacroCall(Element):
	def __init__(self, name, actual_parameters):
		self.name, self.actual_parameters = name, tuple(actual_parameters)
		assert isinstance(self.name, str)
		for a in self.actual_parameters: assert isinstance(a, Element), type(a)
	
	def implement(self, ebnf: "EBNF_Definition", head: str, bindings: dict) -> str:
		args = [a.implement(ebnf, head, bindings) for a in self.actual_parameters]
		symbol = "%s(%s)"%(self.name, ",".join(args))
		if ebnf.implementing(symbol): ebnf.must_elaborate.append((symbol, self.name, args))
		return symbol
	
	def is_void_for(self, ebnf: "EBNF_Definition", head: str) -> bool:
		return ebnf.is_symbol_void(self.name)


class Rewrite:
	def __init__(self, elements:list, precsym:str=None):
		self.elements = elements
		self.precsym = precsym
		self.line_nr = 0
		self.message:Action = self.elements.pop(-1) if isinstance(self.elements[-1], Action) else None
		self.size = len(self.elements)
	
	
	def install(self, ebnf:"EBNF_Definition", head, bindings):
		# Work out which places on the stack (relative to the left edge of the rule)
		# contain "significant" data (for the action rule):
		args = [i for i,elt in enumerate(self.elements) if hasattr(elt, 'capture')]
		if not args: # If no RHS elements specifically have capture marks, respect the void-symbols set.
			args = [i for i,elt in enumerate(self.elements) if not elt.is_void_for(ebnf, head)]
		
		
		ebnf.error_help.current_line_nr = self.line_nr # Because MACROS.
		"""
		Install one rewrite rule:
		Does everything necessary to interpret extension forms down to plain BNF,
		and then enters that into self.plain_bnf as an option for `head`.
		"""
		raw_bnf = []
		for i, elt in enumerate(self.elements):
			if isinstance(elt, Action):
				placeholder = ':'+elt.name
				raw_bnf.append(placeholder)
				ebnf.internal_action(placeholder, prefix_capture(args, i), self.line_nr)
			else:
				assert isinstance(elt, Element)
				raw_bnf.append(elt.implement(ebnf, head, bindings))
		
		if self.message is None:
			action = args[0] if len(args) == 1 else context_free.SemanticAction(None, args)
		else:
			action = context_free.SemanticAction(self.message.name, args)
		ebnf.plain_cfg.add_rule(context_free.Rule(
			head, tuple(raw_bnf), self.precsym, action, ebnf.error_help.current_line_nr
		))

def prefix_capture(args:List[int], size: int):
	# This is returning offsets from the size of the stack as seen
	# by an intermediate action (which is really a special kind of
	# epsilon-rule).
	return tuple(c - size for c in args if c < size)


"""
The MacroParse metagrammar contains various repetition constructs. The following functions
act as rudimentary macros to relieve some redundancy; they essentially mean something like:

	list_of(what, sep) -> what :first | .list_of(what, sep) sep .what :append
	one_or_more(what) -> what :first | .one_or_more(what) .what :append

Doing macros for real is a little more complicated and will be dealt with further down.
"""
def list_of(what, sep):
	head = 'list_of(%r,%r)'%(what,sep)
	METAGRAMMAR.rule(head, '.%s' % what)(FIRST)
	METAGRAMMAR.rule(head, '.%s %s .%s' % (head, sep, what))(APPEND)
	return head
def one_or_more(what):
	head = 'one_or_more(%r)' % (what)
	METAGRAMMAR.rule(head, '.%s' % what)(FIRST)
	METAGRAMMAR.rule(head, '.%s .%s' % (head, what))(APPEND)
	return head
def FIRST(element): return [element]
def APPEND(the_list, element):
	the_list.append(element)
	return the_list


### The MacroParse metagrammar for individual production lines is as follows.
METAGRAMMAR = miniparse.MiniParse('production', 'precedence', 'condition')
METAGRAMMAR.void_symbols.update('arrow capture ( ) [ ] , pragma_prec pragma_nondeterministic'.split())

METAGRAMMAR.rule('production', 'head ' + list_of('rewrite', '|'))(None)

METAGRAMMAR.rule('head', '|')(None) # "use prior" is represented by a null "head".
METAGRAMMAR.rule('head', 'name arrow', )(None) # This will come across as a string.
METAGRAMMAR.rule('head', 'name ( %s ) arrow' % list_of('name', ','))(None) # Represent macro heads with (name, args) tuples.

ELEMENTS = one_or_more('element')
METAGRAMMAR.rule('rewrite', ELEMENTS)(Rewrite)
METAGRAMMAR.rule('rewrite', ELEMENTS + ' pragma_prec terminal')(Rewrite)

METAGRAMMAR.renaming('terminal', 'name', 'literal')

METAGRAMMAR.renaming('element', 'positional_element')
@METAGRAMMAR.rule('element', 'capture positional_element')
def _capture_(positional_element:Element) -> Element:
	positional_element.capture = True
	return positional_element

METAGRAMMAR.renaming('positional_element', 'actual_parameter')
METAGRAMMAR.rule('positional_element', 'message')(Action)
METAGRAMMAR.rule('positional_element', 'err_token')(lambda x:Symbol(ERROR_SYMBOL))

METAGRAMMAR.renaming('actual_parameter', 'symbol') # alternation brackets should not nest directly...
METAGRAMMAR.rule('actual_parameter', '[ ' + one_or_more('symbol') + ' ]')(InlineRenaming)

METAGRAMMAR.rule('symbol', 'name')(Symbol)    # Normal symbol
METAGRAMMAR.rule('symbol', 'literal')(Symbol) # Also a normal symbol with a funny name
METAGRAMMAR.rule('symbol', 'topic')(Symbol)   # Topic symbol; gets its name fixed later.
METAGRAMMAR.rule('symbol', 'name ( ' + list_of('actual_parameter', ',') + ' )')(MacroCall)

# Sub-language: For specifying precedence and associativity rules:
NAMES = one_or_more('name')
METAGRAMMAR.rule('precedence', 'associativity '+one_or_more('terminal'))(None)
METAGRAMMAR.rule('precedence', 'pragma_nondeterministic')(lambda : (NONDET, ()))
METAGRAMMAR.rule('precedence', 'pragma_nonstrict')(lambda : (NONSTRICT, ()))
@METAGRAMMAR.rule('precedence', 'pragma_method name')
def parse_method(_, method):
	try:
		return METHOD, PARSE_TABLE_METHODS[method]
	except KeyError:
		error_message = "Unrecognized parse method %r. Options are %r." % (method, list(PARSE_TABLE_METHODS))
		raise DefinitionError(error_message)

METAGRAMMAR.rule('associativity', 'pragma_left')(lambda _: context_free.LEFT)
METAGRAMMAR.rule('associativity', 'pragma_right')(lambda _: context_free.RIGHT)
METAGRAMMAR.rule('associativity', 'pragma_nonassoc')(lambda _: context_free.NONASSOC)
METAGRAMMAR.rule('associativity', 'pragma_bogus')(lambda _: context_free.BOGUS)
METAGRAMMAR.rule('associativity', 'pragma_void')(lambda _: VOID)
METAGRAMMAR.rule('associativity', 'pragma_void_set')(lambda _: VOID_SET)

# Sub-language: For specifying the connections between scan conditions:
METAGRAMMAR.rule('condition', 'name')(lambda x:(x,[]))
METAGRAMMAR.rule('condition', 'name arrow '+NAMES)(None)

### The lexeme definitions for production rule lines are as follows:
LEX = miniscan.Definition()
LEX.ignore(r'\s+') # Ignore whitespace
LEX.token('name', r'\l\w*') # Identifiers as token type "name".
LEX.token('err_token', r'\$error\$') # the error token is a bit special: it can't be an LHS or have precedence.
LEX.token('topic', r'_/\W') # Bare underline means "the current production rule head".
LEX.token_map('message', r':\l\w*', lambda tx:tx[1:]) # Strip out the colon for message names
@LEX.on(r'%\l[\l_]*') # Build pragma token types from the text.
def pragma(yy): yy.token('pragma_'+yy.match()[1:])
LEX.token('capture', r'[.]/\S') # a dot prefixes a captured element, so it needs to be followed by something.
@LEX.on(r'[\][(),|]') # Punctuation is represented directly, with null semantic value.
def punctuate(yy): yy.token(yy.match())
LEX.token_map('literal', r"'\S+'", lambda text:text[1:-1]) # Literals are allowed two ways, so you can
LEX.token_map('literal', r'"\S+"', lambda text:text[1:-1]) # easily contain whichever kind of quote.
LEX.token('arrow', r'[-=>:<]+') # Arrows in grammar definitions tend to look all different ways. This is flexible.

class ErrorHelper:
	"""
	Right now I'm not sure what else to call this. Naming things is hard, after all.
	The concept is to get the error reporting strategy defined once and accessible throughout.
	"""
	def __init__(self, filename:str):
		self.current_line_nr = 0
		self.filename = filename
	def gripe_about(self, line:str, column:int, message):
		print("%s -- line %d column %d: %s"%(self.filename, self.current_line_nr, column+1, message), file=sys.stderr)
		print(illustration(line, column, prefix='\t'), file=sys.stderr)
		raise
	def parse(self, line:str, line_nr:int, language:str):
		""" Factoring out the commonalities of half-decent error reporting... """
		assert isinstance(line_nr, int), type(line_nr)
		self.current_line_nr = line_nr
		metascan = LEX.scan(line)
		try: return METAGRAMMAR.parse(metascan, language=language)
		except ScannerBlocked as e:
			self.gripe_about(line, e.args[0], "The MacroParse MetaScanner got confused by %r" % e.args[1])
		except DefinitionError as e:
			self.gripe_about(line, metascan.left, e.args[0])
		except ParseError:
			self.gripe_about(
				line, metascan.left,
				'The MacroParse MetaParser got confused about:\n\t'+metascan.match()
			)


class MacroDefinition:
	def __init__(self, name:str, formals):
		self.name = name
		self.formals = tuple(formals)
		self.rewrites = []
		self.actually_used = False
	
	def elaborate(self, ebnf:"EBNF_Definition", head:str, args:list):
		if len(args) != len(self.formals):
			raise DefinitionError("Macro \"%s\" called with wrong number of arguments."%self.name)
		self.actually_used = True
		for rewrite in self.rewrites:
			rewrite.install(ebnf, head, dict(zip(self.formals, args)))

### Grammar object:
# Please note: The format of an action entry shall be the tuple <message_name, tuple-of-offsets, line_number>.
# These are a pass-through into the ContextFreeGrammar and eventually the parse tables themselves.

class EBNF_Definition:
	def __init__(self, error_help:ErrorHelper, strict:bool):
		self.plain_cfg = context_free.ContextFreeGrammar()
		self.current_head = None # This bit of state facilitates the feature of beginning a line with an alternation symbol.
		self.inferential_start = None # Use this to infer a start symbol if necessary.
		self.macro_definitions = {} # name -> MacroDefinition
		self.implementations = {} # canonical symbol -> line number of first elaboration
		self.must_elaborate = []
		self.error_help = error_help
		self.is_nondeterministic = False
		self.is_strict = strict
		self.__void_symbols = set()
		self.__void_sets = {self.__void_symbols.__contains__}
		self.method = PARSE_TABLE_METHODS["LR1"]
		self.__schedule = []
	
	def is_symbol_void(self, symbol:str):
		return any(predicate(symbol) for predicate in self.__void_sets)
	
	def read_precedence_line(self, line:str, line_nr:int):
		direction, symbols = self.error_help.parse(line, line_nr, 'precedence')
		if direction is NONDET:
			self.is_nondeterministic = True
			self.method = PARSE_TABLE_METHODS["LALR"]
		elif direction is NONSTRICT: self.is_strict = False
		elif direction is METHOD: self.method = symbols
		elif direction is VOID: self.__void_symbols.update(symbols)
		elif direction is VOID_SET:
			try: self.__void_sets.update(SET_PATTERNS[k.lower()] for k in symbols)
			except KeyError: self.error_help.gripe_about(line, 10, "The only valid void_set patterns are %r"%(list(SET_PATTERNS)))
		else: self.plain_cfg.assoc(direction, symbols)

	def read_production_line(self, line:str, line_nr:int):
		""" This is the main interface to defining grammars. Call this repeatedly for each line of the grammar. """
		head, rewrites = self.error_help.parse(line, line_nr, 'production')
		for R in rewrites: R.line_nr = line_nr
		# Set the current head field, or use it unchanged if not specified on this line:
		if head is None:
			if self.current_head is None:
				self.error_help.gripe_about(line, 1, 'Confused about what the current head nonterminal is')
			head = self.current_head
		else:
			if isinstance(head, tuple): # Do we need to enter a macro declaration?
				name, formals = head
				if name in self.macro_definitions: # Prevent re-declarations.
					self.error_help.gripe_about(line, 1, "Cannot re-declare macro %r, which was orginally declared on line %d."%(name, self.macro_definitions[name].line_nr))
				elif len(set(formals)|{name}) <= len(formals):
					self.error_help.gripe_about(line, 1, "All the names used in a macro head declaration must be distinct.")
				else:
					head = self.macro_definitions[name] = MacroDefinition(name, formals)
			self.current_head = head
		# Proceed to do the right thing with supplied rewrite rules on this line:
		if isinstance(self.current_head, MacroDefinition):
			self.current_head.rewrites.extend(rewrites)
		else:
			assert isinstance(head, str)
			if self.inferential_start is None: self.inferential_start = head
			for R in rewrites:
				self.__schedule.append((head, R))
		pass
	
	def __validate(self):
		unused_macros = sorted(name+' at line '+str(definition.rewrites[0].line_nr) for name, definition in self.macro_definitions.items() if not definition.actually_used)
		if unused_macros: raise DefinitionError('The following macro(s) were defined but never used:\n\t'+'\n\t'.join(unused_macros))
		if not self.inferential_start: raise DefinitionError("No production rules have been given, so how am I to compile a grammar? (You could give a trivial one...)")
		if not self.plain_cfg.start:
			print('Inferring CFG start symbol %r from earliest production because none was given explicitly.'%self.inferential_start)
			self.plain_cfg.start.append(self.inferential_start)
		self.plain_cfg.validate()
	
	def sugarless_form(self) -> context_free.ContextFreeGrammar:
		if self.inferential_start: # In other words, if any rules were ever given...
			for head,rewrite in self.__schedule:
				rewrite.install(self, head, {})
				
			while self.must_elaborate:
				(symbol, name, args) = self.must_elaborate.pop()
				try: definition = self.macro_definitions[name]
				except KeyError: raise DefinitionError("At line %d macro \"%s\" is called but never defined."%(self.implementations[symbol], name))
				else: definition.elaborate(self, symbol, args)
				
			self.__validate()
			return self.plain_cfg
	
	def internal_action(self, placeholder:str, capture:tuple, line_nr):
		""" These are implemented internally much like an epsilon rule, but able to capture certain left-context. """
		if self.implementing(placeholder):
			self.plain_cfg.add_rule(context_free.Rule(
				lhs = placeholder,
				rhs = (),
				prec_sym = None,
				action = context_free.SemanticAction(placeholder, capture),
				provenance = line_nr,
			))
		else:
			error_message = 'Internal action %s was first elaborated on line %d; reuse is not supported.' % (placeholder, self.implementations[placeholder])
			raise DefinitionError(error_message)

	def implementing(self, symbol) -> bool:
		""" Tells if the current instantiation of a macro-rule is the first; notes the line number where it happened. """
		if symbol in self.implementations:
			return False
		else:
			self.implementations[symbol] = self.error_help.current_line_nr
			return True
