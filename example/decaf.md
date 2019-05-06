# Example `Decaf` MacroParse Specification

The Decaf Language is designed for teaching a course on compilers,
so it's perfect as a full-throttle example exercise for MacroParse.
Also, Decaf resembles Java, but with less caffeine.

If this is your first look at MacroParse, I'd like to recommend starting with the
[JSON tutorial example](json.md).

A little
[poking around](https://www.google.com/search?client=firefox-b-1-d&q=decaf+language)
shows that the definition of Decaf depends strongly on which institution you attend.
The [Texas A&M version](https://parasol.tamu.edu/courses/decaf/students/), for example,
appears very similar to the
[Stanford version](https://web.stanford.edu/class/archive/cs/cs143/cs143.1128/)
with the addition of a simplistic macro facility, possibly to pad out the academic year.
Some versions support backslash-escapes in strings.
Some add a foreign-function-call interface. At least one version looks more like Scheme.

I've mainly followed the Stanford version, except that I add support for:
* Character
[escape sequences](https://docs.oracle.com/javase/specs/jls/se7/html/jls-3.html#jls-3.10.6)
in the Java style, and
* Multi-line triple-quoted strings in the Python style.

(The real purpose of these additions is to exercise the `conditions` block.)

## Conditions

The Decaf scanner can be in one of four conditions: `INITIAL`, `IN_COMMENT`, `IN_STRING`,
or `IN_LONG_STRING`. Either of the last two conditions shares a group of patterns called
`CHARACTER_ESCAPES`, as well as a few special patterns of their own.

I had contemplated 

```
INITIAL
IN_COMMENT
IN_STRING > CHARACTER_ESCAPES
IN_LONG_STRING > CHARACTER_ESCAPES
```

## Patterns

There are a number of keywords. They are all case-sensitive, so I can conveniently
just spell them out as patterns in the scanner. This approach will result in a larger
scan table but no need to consult a separate table of reserved words.

The plan is for reserved words to stand for themselves in the grammar definition,
so the scan action can be the same for all reserved words.

Here, I'm using the special "action" which is just a vertical bar: this means to use
the same action (and priority) as the pattern that follows on the next line.
You do need to specify a proper action before closing the code-block, though.
Otherwise, things could easily get out of hand.
```
void|int|double|bool|string|null|this     |
class|interface|extends|implements        |
for|while|if|else|return|break            |
New|NewArray|Print|ReadInteger|ReadLine   :reserved_word
```
A Decaf-Language identifier is a sequence of letters, digits, and underscores, starting
with a letter. Decaf is case-sensitive, e.g., `if` is a keyword, but `IF` is an identifier;
`binky` and `Binky` are two distinct identifiers. Quoting directly from the specification,
Identifiers can be at most 31 characters long; a longer sequence is truncated and yields
a warning message from a compliant implementation. A good engineered solution is to recognize
the pattern `{alpha}{word}*` and deal with overlong words in the driver, but this is also
an excellent opportunity to show how MacroParse makes it convenient to build the constraint
directly into the scanner (at the cost of a larger scan table).
```
{alpha}{word}{0,30}   :ident
{alpha}{word}{31,}    :overlong_identifier
```

Boolean constants are also reserved. They would overlap with the definition of identifiers
(given above) but the rule priority level `:1` is higher than the default (zero) so these rules win.
```
true|false       :boolean_constant :1
```
Integer constants may be either decimal or hexadecimal using the C-style convention.
Floating point constants require a decimal point, but not necessarily a fractional part.
Strings of the usual kind begin with the double-quote (`"`) character, while triple-quoted
strings begin with `"""`. Aside from the termination requirements which are expressed as
scanner rules, the processing of strings is presumably identical: the only difference
is which scan-condition to enter up front. These rules, then, show how you can provide
such a parameter (any sequence of letters and the underscore) to an action,
directly in the scanner definition.
```
\d+                       :decimal_integer
0[xX]{xdigit}+            :hex_integer
\d+\.\d*([eE][-+]?\d+)?   :double_constant
"                         :begin_string IN_STRING
"""                       :begin_string IN_LONG_STRING
```

Decaf uses various punctuation in its grammar. The following rules pick that up. Since we
can reasonably quote virtually anything in the production rules, all punctuation elements
(quoted) will stand for themselves.
```
{punct}  |
[<>=!]=  |
&&|\|\|  :punctuation
```
For the sake of all that is good and holy, multi-line comments will be handled in the usual
way of entering a special start condition. Single-line comments and all other whitespace are ignored.
```
\/\*            :begin IN_COMMENT
\/\/.*          |
\s+             :ignore
```

## Patterns IN_COMMENT
The idea is to scan decent-sized chunks of commentary without invoking rules too often.
It's hypothetically possible to do this as all one regex, but that would be ungainly.
An end-of-file rule should catch unterminated comments.
```
\*+\/     :begin INITIAL
\*+/[^/]  |
[^*]+     :ignore
<<EOF>>   :error unterminated_comment
```

## Patterns CHARACTER_ESCAPES
The character escape rules are a fine example of something that can be done once for more than one
scan condition, and then included into the right places by reference. (See the `conditions` header.)
```
\\t   :escape tab
\\b   :escape backspace
\\n   :escape newline
\\r   :escape carriage_return
\\f   :escape form_feed
\\'   :escape single_quote
\\"   :escape double_quote
\\\\  :escape backslash
\\[0-3]?[0-7]{1,2}  :octal_escape
```
I've presumed that the "escape" routine will look something up in a table, but the
octal escapes will require something more sophisticated.

Additionally, in Java, there are
[unicode escape sequences](https://docs.oracle.com/javase/specs/jls/se7/html/jls-3.html#jls-3.3),
but Java processes them in an earlier phase. For the sake of playing well with others,
I don't mind defining them as a feature of the string constants.
```
\\[uU]{xdigit}{4}  :unicode_escape
```

## Patterns IN_STRING
Having established the character escapes, it's now necessary to describe the bits which
are unique to the two string delimiting syntaxes. Also, it's necessary to explain,
*IN HUMAN LANGUAGE*, that we mean for the scanner-driver to accumulate a sequence of
zero-or-more `literal_text` and various `escape FOO` to emit as a single parser token
of category `string_constant` whenever the end of the string is encountered.
```
"                :finish_string
[{DOT}&&^\\"]+   :literal_text
{vertical}       |
<<EOF>>          :error unterminated_string
```
Strings (of the usual sort) are not allowed to span lines, and they MUST be closed.
In a nod to usability, unterminated strings are caught specifically with rules here,
rather than leaving the end-user with a stuck scanner.

## Patterns IN_LONG_STRING
What's special about these long-strings is that they can span lines, and also the
terminator is more than one character long. Thus, the patterns for
matching literal text and the final delimiters are a tad different:
```
"""              :finish_string
""?              |
\s+              |
[{DOT}&&^\\"]+   :literal_text
<<EOF>>          :error unterminated_string
```
Similar to the `IN_COMMENT` group, it would be possible to write even more aggressive
regular expressions, but that particular juice is not really worth the squeeze.

## Productions PROGRAM
First, a couple macros. Nothing too crazy, but it does show that you
can have one macro-call as argument to another, and THINGS SHOULD WORK.
```
optional(foo) -> :nothing | foo
one_or_more(foo) -> foo :first | one_or_more(foo) foo :append
comma_separated(foo): foo :first | .foo ',' .comma_separated(foo) :append
list_of(foo) -> optional(one_or_more(foo))
comma_list(foo) -> optional(comma_separated(foo))
```
Now comes the bulk of the grammar. Note that precedence declarations
come later on. It's not a perfect 1::1 match to the reference grammar,
but it's clear to see the correspondence.
```
PROGRAM -> one_or_more(Declaration)
Declaration ->  VariableDecl | FunctionDecl | ClassDecl | InterfaceDecl

VariableDecl -> .Variable ';'
Variable -> Type ident
Type -> int | double | bool | string
	| .Type '[' ']' :array_type

FunctionDecl -> .Type .ident '(' .Formals ')' .StmtBlock
FunctionDecl -> .void .ident '(' .Formals ')' .StmtBlock
```
There's a reason for the above near-duplication in `FunctionDecl`: If you write instead
`-> .[Type void] .ident...`, then the grammar is no longer LR(1): The
parser can't know if it's parsing a `Variable` or a `FunctionDecl`,
so it doesn't know whether to reduce the `Type` as a `[Type|void]` or
shift a following `ident`. Ideally that should not be a problem because of
unit-rule optimization (a.k.a. renaming-elimination). Tracking this
down is going to result in a much nicer tool...
```
Formals -> comma_list(Variable)

ClassDecl -> class .ident .optional(Parent) .optional(Impls) '{' .list_of(Field) '}' :class
Parent -> extends .ident
Impls -> implements .comma_separated(ident)
Field -> VariableDecl | FunctionDecl

InterfaceDecl -> interface .ident '{' .list_of(Prototype) '}' :interface
Prototype -> .[Type void] .ident '(' .Formals ')' ';'

StmtBlock -> '{' .list_of(Stmt) '}'

Stmt -> StmtBlock
	| .Expr ';'    :evaluate_for_side_effects
	| if '(' .Expr ')' .Stmt             :if_statement
	| if '(' .Expr ')' .Stmt else .Stmt  :if_else_statement
	| while '(' .Expr ')' .Stmt          :while_statement
	| for '(' .optional(Expr) ';' .Expr ';' .optional(Expr) ')' .Stmt   :for_statement
	| return .optional(Expr) ';'   :return_statement
	| break .optional(ident) ';'   :break_statement
	| Print '(' .comma_separated(Expr) ')' ';'  :print_statement
```
There's a minor annoyance with the `:if_statement` and `:if_else_statement` actions:
it would be convenient to supply an `optional(ElseClause)`, but it seems to confuse
the table generator into seeing a conflict that operator-precedence declarations are
not sufficient to resolve. I think I understand why, but gee whiz if some parse table
visualization kung-fu wouldn't be awesome. Come to think of it, I've got a little
project I'm working on...
```
Expr -> .LValue '=' .Expr   :assign
	| Constant | LValue | this | Call | '(' .Expr ')'
	| .Expr '+'  .Expr :add
	| .Expr '-'  .Expr :subtract
	| .Expr '*'  .Expr :multiply
	| .Expr '/'  .Expr :divide
	| .Expr '%'  .Expr :modulo
	|       '-'  .Expr :negate    %prec UMINUS
	| .Expr '<'  .Expr :lt
	| .Expr '<=' .Expr :le
	| .Expr '==' .Expr :eq
	| .Expr '!=' .Expr :ne
	| .Expr '>=' .Expr :ge
	| .Expr '>'  .Expr :gt
	| .Expr '&&' .Expr :and
	| .Expr '||' .Expr :or
	|       '!'  .Expr :not
	| .ReadInteger '(' ')' :read
	| .ReadLine '(' ')'    :read
	| New '(' .ident ')'   :new
	| NewArray '(' .Expr ',' .Type ')'  :new_array
	
LValue -> ident
	| .Expr '.' .ident      :field
	| .Expr '[' .Expr ']'   :element

Call -> .ident '(' .Actuals ')'         :function_call
	| .Expr '.' .ident '(' .Actuals ')' :method_call

Actuals -> optional(comma_separated(Expr))

Constant -> intConstant | doubleConstant | boolConstant | stringConstant | null

```

## Precedence
The usual rules apply, remembering that highest-precedence comes first in MacroParse.
Decaf doesn't have bitwise operators, so there's little opportunity for confusion.
I'm going to assume chained-comparison operators are not allowed, and that `&&`
binds more tightly than `||`.
```
%left '[' '(' '.'
%bogus UMINUS
%left '*' '/' '%'
%left '+' '-'
%nonassoc '<' '<=' '==' '!=' '>=' '>'
%nonassoc '!'
%left '&&'
%left '||'
%right '='
```
Mathematically, Decaf does not need a special high-precedence rule for unary
negation: it has neither operator overloading nor exponentiation notation.
But it's still widely accepted that unary negation should happen before any
other math, so I've thrown it in.

The following declaration solves the "dangling-else" shift/reduce conflict:
```
%right if else
```
A rule-precedence declaration on the `:if_statement` rule should eliminate the need to include
the `if` token in this precedence declaration, but at the moment I don't recall if there's
metagrammar for that yet. Also, this works too.
