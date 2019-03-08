# Welcome to the `MacroParse` Tutorial [JSON](http://www.json.org/) Syntax Description!
* [JSON](http://www.json.org/) has just enough structure to be an excellent introductory example.
* It does not exercise every `MacroParse` feature, but there are (to be) further examples.

The format of a `MacroParse` syntax description is literate, meaning that exposition is given
prominence at least equal to implementation. To that end, a valid syntax description
is also a valid [markdown](https://en.wikipedia.org/wiki/Markdown) document,
and *this* markdown document (the one you are reading right now) is a valid
`MacroParse` syntax description.

* A stripped, "just-the-facts" version of this file is at [json_stripped.py](json_stripped.py).

The header and code-block structures indicate the major
components of the definition. Normal text (like this paragraph)
is ignored by the `MacroParse` compiler, but presumably useful for people to read
if they want to make use of your syntax description most effectively.

The sections significant to the `MacroParse` compiler are those distinguished by keywords
drawn from the set {`Definitions`, `Conditions`, `Patterns`, `Precedence`, `Productions`}.
Sections may appear in any order, and except for `Patterns`, each ought to appear at most once.
(This is not enforced.)

* `Patterns` sections are distinguished by an optional pattern-group name following the keyword.
* `Productions` sections are adorned with the name of the start symbol (or alternatives)
for the context-free language(s) defined therein. (The feature works the same way as `miniparse`.)

Headers that do not begin with a known keyword result in the section being ignored.
Noise punctuation in a header is allowed and treated sensibly, but additional unexpected
alphanumerics may result in undefined behavior.
Sections without any code blocks are also ignored.
The header level is not (currently) significant, but good style puts all compiled sections
at the same header level.

## Definitions:
A few named subexpressions make the rest considerably easier to read (and write).
The `Definitions` section is where to put them.

The name comes first, then whitespace, and finally a regular expression on a line
for each definition. Leading and trailing whitespace is ignored.

```
wholeNumber     [1-9]\d*
signedInteger   -?(0|{wholeNumber})
```

One definition may be referenced inside of another, later definition.
They are treated in the order of appearance. Any given name may be defined
at most once. Case is significant. Names must start with a letter and
be composed only of letters, digits, and underlines. The same names are
predefined as for the `miniscan` module, because the same code builds the
predefinitions.

Additional code-blocks may be used as needed in any section.
```
fractionalPart  \.\d+
exponent        [Ee][-+]?\d+
```

## Conditions:
Real-world syntaxes often contain zones ('scan conditions') where different scanning rules apply.

Often, each zone is relatively self-contained and unlike the others. In such cases, the `Conditions`
header may be left out and the `MacroParse` compiler will treat each `Patterns` section as a
separate scan condition.

There are times when it seems prudent to specify a more complex relationship between scan conditions
and rule groups: inclusion, embedding, extension, and automatic fall-back.

Unfortunately for this tutorial, JSON does not require such gymnastics for a clear exposition,
and anyway the code for that sort of thing is yet to be defined. When the time comes, additional
examples will be prepared. For now, your suggestions are welcome.

## Patterns:

Scanner rules are defined within a `Patterns` section.

Rules here each contain two or three fields specifying:

* a pattern in the exact same syntax as `miniscan`,
* an action, consisting of one or two 'words' matching `:{letter}{word}*(\h+{word}+)?` in `miniscan` syntax,
* Optionally, a rule rank number matching `:(0|{wholeNumber})` (considering the definition given above).

The match tie-breaking rule is the same as described for `miniscan`:
* Highest rank first,
* then longest-match (including trailing context, if any),
* and finally, earliest-defined.

Following are the rules (pattern:action pairs) that apply outside of string constants:

```
{signedInteger}                               :integer
{signedInteger}{fractionalPart}?{exponent}?   :float
\s+                                           :ignore_whitespace
[][{}:,]                                      :punctuation
true|false|null                               :reserved_word
"                                             :enter_string

```

If non-blank lines do not fit the pattern, then it is considered a syntax error.

## Patterns in_string:

If a word or token follows the keyword `Patterns`, it gives the name of an alternate rule
group this section defines. As described above, this will result in a named scan condition
unless directives in the `Conditions` section override that default behavior.

To clarify: the identifier here is `in_string`, without the colon.

Here are the rules that apply within a JSON string value:

```
"               :leave_string
[^\\"]+         :stringy_bit
\\["/\\]        :escaped_literal
\\[bfnrt]       :shorthand_escape
\\u{xdigit}{4}  :unicode_escape

```

You'll notice nothing has been coded about transitions between scan conditions.
That part needs to be specified in plain language, and then a conforming implementation
is required to obey.

For the sake of the JSON example, in addition to emitting a double-quote token to the parser,
the `:enter_string` message must result in a transition
to the `in_string` condition, while `:leave_string` performs the reverse. By convention,
the identifier for the initial scan condition is `INITIAL`, and this identifier is
implied if the `Patterns` header does not provide an explicit pattern-group identifier.

## Precedence

JSON does not require precedence declarations. They will be explained in another tutorial, perhaps
describing a simple programming language.

## Productions: value
There are various conventions for rendering the "produces" arrow in plain text. Because
these production rules are known to be context-free, the exact shape of the arrow is quite
unimportant. Therefore, any blob of punctuation marks will be treated as the arrow.

Nonterminals must have identifier names. Terminals are much freer.
Letter case is not enforced as a distinguishing feature.


Here, then, is the context-free portion of the grammar for JSON syntax:

```
value => string | number | object | array | true | false | null

object ::= '{' .list_of(key_value_pair) '}' :object

array = '[' .list_of(value) ']' :array

key_value_pair -> .string ':' .value :pair

string : '"' .text '"'

text ==> :empty
  | text character :append

```

This is also the section where production-rule macros would be defined.
They are known by the parenthetical arguments they operate on.

```
list_of(item) -> :empty | one_or_more(item)

one_or_more(item) -> item :first
  | .one_or_more(item) `, .item :append
```

As may be inferred, `item` is here a formal-parameter to the macros `list_of` and `one_or_more`.
The macro expansion machinery does the right thing at the context-free-grammar level, but it
is up to the application to deal properly with, say, message `:first` applying either to a `value`
or a `key_value_pair` as appropriate. If you're working in a dynamic language, that won't be
any trouble at all. In one with strict static typing, you'll doubtless have some sort
of "parse stack entry" type defined: it needs a variant for "list-of-entries".


# Notes:

The semantics of scan actions differ slightly from (current) `miniscan`: Specifically, no particular
scan/parse integration strategy is implied.

Many languages have a convenient 1:1 relation between patterns and tokens, which facilitates a
scanner-as-iterator approach: return values from the scan actions and they are implicitly emitted.

Some languages are not so simple. For example, indent-grammars need to calculate
the indent level on each line and potentially emit several tokens to open or close indented blocks.
For these, a scanner-as-delegator approach is better: the scanner simply invokes the functionality
associated with the pattern's action, and that functionality is responsible to feed zero, one, or
more tokens to a parser object method.

Within `algorithms.py`, allowance shall be made for either approach, and any integration issues
may then be described in plain language within the normal-text of the grammar definition file.

Part of the compilation process ought to warn about unreachable rules and/or the potential for
blocked scanners. That is currently reserved for future work.