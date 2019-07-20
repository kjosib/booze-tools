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

from ..support import failureprone, interfaces
from ..scanning import miniscan
from ..parsing import context_free, miniparse

NONDET = object()

class DefinitionError(Exception): pass

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

class Symbol(Element):
	def __init__(self, name): self.name = name
	
	def implement(self, ebnf: "EBNF_Definition", head: str, bindings: dict) -> str:
		return head if self.name == '_' else bindings.get(self.name, self.name)


class InlineRenaming(Element):
	def __init__(self, alternatives):
		self.alternatives = tuple(alternatives)
		for a in self.alternatives: assert isinstance(a, Element) and not isinstance(a, Action)
	
	def implement(self, ebnf: "EBNF_Definition", head: str, bindings: dict) -> str:
		alts = [a.implement(ebnf, head, bindings) for a in self.alternatives]
		symbol = "[%s]"%("|".join(alts))
		if ebnf.implementing(symbol):
			for a in alts:
				ebnf.plain_cfg.rule(symbol, [a], None, None)
		return symbol
		

class MacroCall(Element):
	def __init__(self, name, actual_parameters):
		self.name, self.actual_parameters = name, tuple(actual_parameters)
		assert isinstance(self.name, str)
		for a in self.actual_parameters: assert isinstance(a, Element), type(a)
	def canonical_symbol(self, bindings:dict) -> str: return
	
	def implement(self, ebnf: "EBNF_Definition", head: str, bindings: dict) -> str:
		args = [a.implement(ebnf, head, bindings) for a in self.actual_parameters]
		symbol = "%s(%s)"%(self.name, ",".join(args))
		if ebnf.implementing(symbol): ebnf.must_elaborate.append((symbol, self.name, args))
		return symbol


class Rewrite:
	def __init__(self, elements:list, precsym:str=None):
		self.elements = elements
		self.precsym = precsym
		self.line_nr = 0
		self.message:Action = self.elements.pop(-1) if isinstance(self.elements[-1], Action) else None
		self.__args = args = []
		self.size = len(self.elements)
		for i,elt in enumerate(self.elements):
			if hasattr(elt, 'capture'): args.append(i)
		if not args: args.extend(range(self.size)) # Pick up everything if nothing is special.
	
	def prefix_capture(self, size:int):
		return tuple(c - size for c in self.__args if c < size)
	
	def install(self, ebnf:"EBNF_Definition", head, bindings):
		ebnf.error_help.current_line_nr = self.line_nr # Because MACROS.
		rhs = [elt.implement(ebnf, head, bindings) for elt in self.elements]
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
				ebnf.internal_action(placeholder, self.prefix_capture(i))
			else:
				assert isinstance(elt, Element)
				raw_bnf.append(elt.implement(ebnf, head, bindings))
		
		raw_message = None if self.message is None else self.message.name
		if len(raw_bnf) == 1 and raw_message is None: attribute = None
		else:
			offsets = self.prefix_capture(len(raw_bnf))
			attribute = (raw_message, offsets, ebnf.error_help.current_line_nr)
		ebnf.plain_cfg.rule(head, raw_bnf, attribute, self.precsym)

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

METAGRAMMAR.rule('production', '.head .' + list_of('rewrite', '|'))(None)

METAGRAMMAR.rule('head', '|')(None) # "use prior" is represented by a null "head".
METAGRAMMAR.rule('head', '.name arrow', )(None) # This will come across as a string.
METAGRAMMAR.rule('head', '.name ( .%s ) arrow' % list_of('name', ','))(None) # Represent macro heads with (name, args) tuples.

ELEMENTS = one_or_more('element')
METAGRAMMAR.rule('rewrite', ELEMENTS)(Rewrite)
METAGRAMMAR.rule('rewrite', '.' + ELEMENTS + ' pragma_prec .terminal')(Rewrite)

METAGRAMMAR.renaming('terminal', 'name', 'literal')

METAGRAMMAR.renaming('element', 'positional_element')
@METAGRAMMAR.rule('element', 'capture .positional_element')
def _capture_(positional_element:Element) -> Element:
	positional_element.capture = True
	return positional_element

METAGRAMMAR.renaming('positional_element', 'actual_parameter')
METAGRAMMAR.rule('positional_element', 'message')(Action)

METAGRAMMAR.renaming('actual_parameter', 'symbol') # alternation brackets should not nest directly...
METAGRAMMAR.rule('actual_parameter', '[ .' + one_or_more('symbol') + ' ]')(InlineRenaming)

METAGRAMMAR.rule('symbol', 'name')(Symbol)    # Normal symbol
METAGRAMMAR.rule('symbol', 'literal')(Symbol) # Also a normal symbol with a funny name
METAGRAMMAR.rule('symbol', 'topic')(Symbol)   # Topic symbol; gets its name fixed later.
METAGRAMMAR.rule('symbol', '.name ( .' + list_of('actual_parameter', ',') + ' )')(MacroCall)

# Sub-language: For specifying precedence and associativity rules:
NAMES = one_or_more('name')
METAGRAMMAR.rule('precedence', '.associativity .'+one_or_more('terminal'))(None)
METAGRAMMAR.rule('precedence', 'pragma_nondeterministic .'+NAMES)(lambda x:(NONDET, x))

METAGRAMMAR.rule('associativity', 'pragma_left')(lambda x: context_free.LEFT)
METAGRAMMAR.rule('associativity', 'pragma_right')(lambda x: context_free.RIGHT)
METAGRAMMAR.rule('associativity', 'pragma_nonassoc')(lambda x: context_free.NONASSOC)
METAGRAMMAR.rule('associativity', 'pragma_bogus')(lambda x: context_free.BOGUS)

# Sub-language: For specifying the connections between scan conditions:
METAGRAMMAR.rule('condition', 'name')(lambda x:(x,[]))
METAGRAMMAR.rule('condition', '.name arrow .'+NAMES)(None)

### The lexeme definitions for production rule lines are as follows:
LEX = miniscan.Definition()
LEX.on(r'\s+')(None) # Ignore whitespace
LEX.on(r'\l\w*')('name') # Identifiers as token type "name".
LEX.on(r'_/\W')('topic') # Bare underline means "the current production rule head".
LEX.on(r':\l\w*')(lambda scanner:('message', scanner.matched_text()[1:])) # Strip out the colon for message names
LEX.on(r'%\l+')(lambda scanner:('pragma_'+scanner.matched_text()[1:], None)) # Build pragma token types from the text.
LEX.on(r'[.]/\S')('capture') # a dot prefixes a captured element, so it needs to be followed by something.
LEX.on(r'[][(),|]')(lambda scanner:(scanner.matched_text(), None)) # Punctuation is represented directly, with null semantic value.
LEX.on(r"'\S+'")(lambda scanner:('literal', scanner.matched_text()[1:-1])) # Literals are allowed two ways, so you can
LEX.on(r'"\S+"')(lambda scanner:('literal', scanner.matched_text()[1:-1])) # easily contain whichever kind of quote.
LEX.on(r'[-=>:<]+')('arrow') # Arrows in grammar definitions tend to look all different ways. This is flexible.

class ErrorHelper:
	"""
	Right now I'm not sure what else to call this. Naming things is hard, after all.
	The concept is to get the error reporting strategy defined once and accessible throughout.
	"""
	def __init__(self): self.current_line_nr = 0
	def gripe(self, message): raise DefinitionError('At line %d: %s.'%(self.current_line_nr, message))
	def gripe_about(self, line:str, column:int, message): self.gripe(message +"\n" + failureprone.illustration(line, column, prefix='\t'))
	def parse(self, line:str, line_nr:int, language:str):
		""" Factoring out the commonalities of half-decent error reporting... """
		assert isinstance(line_nr, int), type(line_nr)
		self.current_line_nr = line_nr
		metascan = LEX.scan(line)
		try: return METAGRAMMAR.parse(metascan, language=language)
		except interfaces.ScanError as e: self.gripe_about(line, e.args[0], "The MacroParse MetaScanner got confused by %r" % e.args[1])
		except interfaces.ParseError as e:
			self.gripe_about(
				line, metascan.current_position(),
				'The MacroParse MetaParser got confused about:\n\t'+e.condition()
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

def illustrate_position(line:str, column:int): return line[:column]+'<<_here_>>'+line[column:]

class EBNF_Definition:
	def __init__(self, error_help:ErrorHelper):
		self.plain_cfg = context_free.ContextFreeGrammar()
		self.current_head = None # This bit of state facilitates the feature of beginning a line with an alternation symbol.
		self.inferential_start = None # Use this to infer a start symbol if necessary.
		self.macro_definitions = {} # name -> MacroDefinition
		self.implementations = {} # canonical symbol -> line number of first elaboration
		self.must_elaborate = []
		self.error_help = error_help
		self.nondeterministic_symbols = set()
	
	def read_precedence_line(self, line:str, line_nr:int):
		direction, symbols = self.error_help.parse(line, line_nr, 'precedence')
		if direction is NONDET: self.nondeterministic_symbols.update(symbols)
		else: self.plain_cfg.assoc(direction, symbols)

	def read_production_line(self, line:str, line_nr:int):
		""" This is the main interface to defining grammars. Call this repeatedly for each line of the grammar. """
		head, rewrites = self.error_help.parse(line, line_nr, 'production')
		for R in rewrites: R.line_nr = line_nr
		# Set the current head field, or use it unchanged if not specified on this line:
		if head is None:
			if self.current_head is None:
				self.error_help.gripe('Confused about what the current head nonterminal is')
			head = self.current_head
		else:
			if isinstance(head, tuple): # Do we need to enter a macro declaration?
				name, formals = head
				if name in self.macro_definitions: # Prevent re-declarations.
					self.error_help.gripe("Cannot re-declare macro %r, which was orginally declared on line %d."%(name, self.macro_definitions[name].line_nr))
				elif len(set(formals)|{name}) <= len(formals):
					self.error_help.gripe("All the names used in a macro head declaration must be distinct.")
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
				R.install(self, head, {})
		pass
	
	def validate(self):
		unused_macros = sorted(name+' at line '+str(definition.rewrites[0].line_nr) for name, definition in self.macro_definitions.items() if not definition.actually_used)
		if unused_macros: raise DefinitionError('The following macro(s) were defined but never used:\n\t'+'\n\t'.join(unused_macros))
		if not self.inferential_start: raise DefinitionError("No production rules have been given, so how am I to compile a grammar? (You could give a trivial one...)")
		if not self.plain_cfg.start:
			print('Inferring CFG start symbol %r from earliest production because none was given explicitly.'%self.inferential_start)
			self.plain_cfg.start.append(self.inferential_start)
		self.plain_cfg.validate()
	
	def sugarless_form(self) -> context_free.ContextFreeGrammar:
		if self.inferential_start: # In other words, if any rules were ever given...
			while self.must_elaborate:
				(symbol, name, args) = self.must_elaborate.pop()
				try: definition = self.macro_definitions[name]
				except KeyError: raise DefinitionError("At line %d macro \"%s\" is called but never defined."%(self.implementations[symbol], name))
				else: definition.elaborate(self, symbol, args)
			self.validate()
			return self.plain_cfg
	
	def internal_action(self, placeholder:str, capture:tuple):
		if self.implementing(placeholder):
			attribute = (placeholder, capture, self.error_help.current_line_nr)
			self.plain_cfg.rule(placeholder, [], attribute, None)
		else:
			self.error_help.gripe(
				'Internal action %s was first elaborated on line %d; reuse is not (presently) supported.' %
				(placeholder, self.implementations[placeholder])
			)

	def implementing(self, symbol) -> bool:
		""" Tells if the current instantiation of a macro-rule is the first; notes the line number where it happened. """
		if symbol in self.implementations:
			return False
		else:
			self.implementations[symbol] = self.error_help.current_line_nr
			return True
