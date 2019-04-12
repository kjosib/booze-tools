# Example `Decaf` MacroParse Specification

The [Decaf Language](https://parasol.tamu.edu/courses/decaf/students/)
is designed for teaching a course on compilers, so it's perfect as a full-throttle example
exercise for MacroParse. Also, Decaf resembles Java, but with less caffeine.

A little poking around suggests that the definition of Decaf depends strongly on which
institution you attend. I glanced at a couple versions and I like the one linked above.
It's a bit more feature-complete than some of the other alternatives. Also, it's hosted
at Texas A&M University, and as a proud Tea-Sip I have to pick on TAMU.

## Conditions

I plan to implement the pre-processor by integration into the main scanner definition.
This will provide an example of both start-condition nesting and the use of
a separate scanner instance to re-process tokens. However, the pre-processor is
not a project for today. It will have to wait.

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
An identifier is a sequence of letters, digits, and underscores, starting with a letter. Decaf is case-sensitive,
e.g., if is a keyword, but IF is an identifier; binky and Binky are two distinct identifiers. Identifiers can
be at most 31 characters long. A good solution is to recognize all such sequences and
deal with overlong words in the driver, but MacroParse makes it convenient to build the constraint
directly into the scanner (at the cost of a larger table).
```
{alpha}{word}{0,30}   :ident
```

Boolean constants are also reserved. They would overlap with the definition of identifiers
(given above) but the rule priority level `:1` is higher than the default (zero) so these rules win.
```
true|false       :boolean_constant :1
```
Integer constants may be either decimal or hexadecimal using the C-style convention.
Floating point constants require a decimal point, but not necessarily a fractional part.
Strings are not allowed to span lines, and they MUST be closed. In a nod to usability,
unterminated strings are caught specifically with an extra rule here. It demonstrates
how you can add a parameter (any sequence of letters and the underscore) to an action.
```
\d+                       :decimal_integer
0[xX]{xdigit}+            :hex_integer
\d+\.\d*([eE][-+]?\d+)?   :double_constant
"[{DOT}&&^"]*"            :string_constant
"                         :error unterminated_string
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
.?/$$     :error unterminated_comment
```
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

Expr -> .LValue '=' .Expr   :assign
    | Constant | LValue | this | Call | '(' .Expr ')'
    | .Expr '+'  .Expr :add
    | .Expr '-'  .Expr :subtract
    | .Expr '*'  .Expr :multiply
    | .Expr '/'  .Expr :divide
    | .Expr '%'  .Expr :modulo
    |       '-'  .Expr :negate
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
    
    
    

```

## Precedence
The usual rules apply, remembering that highest-precedence comes first in MacroParse.
Decaf doesn't have bitwise operators, so there's little opportunity for confusion.
I'm going to assume chained-comparison operators are not allowed, and that `&&`
binds more tightly than `||`.
```
%left '*' '/' '%'
%left '+' '-'
%nonassoc '<' '<=' '==' '!=' '>=' '>'
%left '!'
%left '&&'
%left '||'
%right '='
```
The following declaration solves the "dangling-else" shift/reduce conflict:
```
%right if else
```
A rule-precedence declaration on the `:if_statement` rule should eliminate the need to include
the `if` token in this precedence declaration, but at the moment I don't recall if there's
metagrammar for that yet. Also, this works too.
