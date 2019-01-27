""" JSON is JavaScript Object Notation. See http://www.json.org/ for more. Python has a standard library for JSON, so this is just a worked example. """

import miniscan, miniparse

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

# Now we can write some pattern/action pairs. The parser module expects to get (token, value) pairs, which
# we can return from the action. You can write it as a decorator, which is convenient if significant
# computation determines which token to return...
@lexemes.on('{signedInteger}')
def match_integer(scanner):
	return 'number', int(scanner.matched_text())

# Or take advantage of lambda notation:
lexemes.on('{signedInteger}{fractionalPart}?{exponent}?')(lambda scanner: ('number', float(scanner.matched_text())))

# It's easy to ignore whitespace:
lexemes.on('\s+')(None)

# Punctuation will appear as such in the production rules.
lexemes.on(r'[][{}:,]')(lambda scanner: (scanner.matched_text(), None))

# You can dynamically generate your pattern...
reserved_words = {'true': True, 'false': False, 'null': None}
@lexemes.on('|'.join(reserved_words.keys()))
def match_reserved_word(scanner):
	word = scanner.matched_text()
	return word, reserved_words[word]

# You can make alternate scan conditions just by asking for them:
in_string = lexemes.condition('seen_double_quote')

# We'll need a way in and back out again:
@lexemes.on('"')
def enter_string(scanner):
	scanner.enter('seen_double_quote')
	return '"', None

@in_string.on('"')
def leave_string(scanner):
	scanner.enter(None)
	return '"', None

# Match normal characters in bulk:
in_string.on(r'[^\\"]+')(lambda scanner:('character', scanner.matched_text()))

# Simple escapes: quote, solidus, reverse solidus:
in_string.on(r'\\["/\\]')(lambda scanner:('character', scanner.matched_text()[1]))

# Shorthand letter escapes:
escapes = {'b': 8, 't': 9, 'n': 10, 'f': 12, 'r': 13, }
in_string.on(r'\\[bfnrt]')(lambda scanner:('character', chr(escapes[scanner.matched_text()[1]])))

# Arbitrary Unicode BMP code point:
@in_string.on(r'\\u{xdigit}{4}')
def unicode_escape(scanner):
	hex = scanner.matched_text()[2:]
	value = int(hex, 16)
	return 'character', chr(value)


###################################################################################
#  Follow that up with a context-free grammar. It's made a bit less wonderful by not having grammar macros yet...
###################################################################################

grammar = miniparse.MiniParse('value')
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
