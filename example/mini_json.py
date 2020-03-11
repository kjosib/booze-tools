""" JSON is JavaScript Object Notation. See http://www.json.org/ for more.
Python has a standard library for JSON, so this is just a worked example. """

from boozetools.parsing import miniparse
from boozetools.scanning import miniscan
from boozetools.support.interfaces import Scanner

###################################################################################
#  Begin with a scanner definition:
###################################################################################

# Define a scanner.
lexemes = miniscan.Definition()

# A few named subexpressions make the rest considerably easier to read (and write).
lexemes.let('wholeNumber', r'[1-9]\d*')
lexemes.let('signedInteger', r'-?(0|{wholeNumber})')
lexemes.let('fractionalPart', r'\.\d+')
lexemes.let('exponent', r'[Ee][-+]?\d+')

# Now we can write some pattern/action pairs.
# The miniscan module offers several ways.
# One way is as a decorator for an arbitrary function:
# This is  convenient if significant computation determines which token
# (or indeed, how many tokens) to emit.
@lexemes.on('{signedInteger}')
def match_integer(yy:Scanner):
	# It's sort of assumed you'll be connecting a mini-scanner up to a mini-parser.
	# The parser module expects to get (token, value, start, end) quads, but the
	# scanner handles the start and end. You just call the `.token(...)` method
	# on the parameter, which is a scanning context.
	yy.token('number', int(yy.matched_text()))

# The above pattern is fairly common: take the matched text and
# the semantic value is some function of the matched text, while the token kind
# is constant for the pattern. There's a shortcut for this sort of thing:
lexemes.token_map('number', '{signedInteger}{fractionalPart}?{exponent}?', float)

# It's easy to ignore whitespace:
lexemes.ignore('\s+')

# Punctuation will appear as such in the production rules.
@lexemes.on(r'[][{}:,]')
def punctuation(yy):
	# Note that `None` is the default semantic value for a token
	# if all you supply is a token kind.
	yy.token(yy.matched_text())

# You can dynamically generate your pattern...
reserved_words = {'true': True, 'false': False, 'null': None}
@lexemes.on('|'.join(reserved_words.keys()))
def match_reserved_word(yy):
	word = yy.matched_text()
	yy.token(word, reserved_words[word])

# You can make alternate scan conditions just by asking for them:
in_string = lexemes.condition('seen_double_quote')

# We'll need a way in and back out again:
@lexemes.on('"')
def enter_string(yy):
	yy.enter('seen_double_quote')
	yy.token('"')

@in_string.on('"')
def leave_string(yy):
	yy.enter(None)
	yy.token('"')

# Match normal characters in bulk:
# .token is similar to .token_map, but the match text is exactly the semantic value.
in_string.token('character', r'[^\\"]+')

# Simple escapes: quote, solidus, reverse solidus:
in_string.token_map('character', r'\\["/\\]', lambda text:text[1])

# Shorthand letter escapes:
escapes = {'b': 8, 't': 9, 'n': 10, 'f': 12, 'r': 13, }
in_string.token_map('character', r'\\[bfnrt]', lambda text: chr(escapes[text[1]]))

# Arbitrary Unicode BMP code point:
in_string.token_map('character', r'\\u{xdigit}{4}', lambda text:chr(int(text[2:],16)))

###################################################################################
#  Follow that up with a context-free grammar. It's made a bit less wonderful by not having grammar macros yet...
###################################################################################

grammar = miniparse.MiniParse('value', method='LALR')
grammar.renaming('value', 'string', 'number', 'object', 'array', 'true', 'false', 'null')

grammar.rule('object', '{ }')(dict)
grammar.renaming('object', '{ .key_value_pairs }')

grammar.rule('array', '[ ]')(list)
grammar.renaming('array', '[ .comma_separated_values ]')

@grammar.rule('key_value_pairs', '.string : .value')
def first_pair(key, value): return {key:value}
@grammar.rule('key_value_pairs', '.key_value_pairs , .string : .value')
def next_pair(the_object, key, value):
	the_object[key] = value
	return the_object

@grammar.rule('comma_separated_values', 'value')
def first_value(value): return [value]
@grammar.rule('comma_separated_values', '.comma_separated_values , .value')
def next_value(the_array, value):
	the_array.append(value)
	return the_array

# It's a bit more efficient to collect a list of string components and then
# join them (via the empty string) at the end. Here's an illustrative approach:
grammar.rule('string', '" .text "')(''.join) # Bound methods are a handy thing in Python...
grammar.rule('text', '')(list) # The epsilon rule gives us our initial list.
@grammar.rule('text', 'text character')
def more_text(the_list, a_substring):
	the_list.append(a_substring)
	return the_list

###################################################################################
#  And finally, tie it up in a nice neat bow:
###################################################################################

def parse(text): return grammar.parse(lexemes.scan(text))
