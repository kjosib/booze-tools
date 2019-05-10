# Pascal
Pascal is a once-wildly-popular programming language invented by Nicklaus Wirth.

It is compact, block-structured, lexically scoped, with nested functions,
functions as parameters (but not return values) and strong static manifest types,
allowing for variant records, but lacking generics and variable-sized arrays.

It got picked up in educational curricula and then extended in various directions
and had the sharp corners filed off by various commercial implementations. It also
stimulated development of the UCSD P-System, which was a write-once run-anywhere
stack-oriented byte-coded virtual-machine and operating system from the 1980s with
implementations on the Apple ][ family and presumably other bigger machines.

As originally designed, Pascal contains a few features we would today consider
archaic. In particular, statements can have numeric labels (which must be
pre-declared) and thus be the target of `goto` commands. By contrast, there is
no equivalent of `break` or `continue` as you may know them from the C family.

There are various places in the official grammar that call for things like
`procedure identifier` or `type identifier`. Such restrictions require semantic
analysis. Accordingly, they're left out of the context-free grammar.

As it happens, Pascal is designed for a single-pass recursive-descent compiler,
so in principle you could write semantic actions that update a symbol table and
even emit object code as you go along, but why blend concerns?

As it also happens, if you ***do not*** blend these concerns, then it's easy to
wind up with a grammar which is LR(1) but not LALR(1). Such is true of *this*
grammar definition. In particular: if the parser is ready to accept a `command`,
and then gets an `identifier`, then the lookahead following that state gets
so-called "mysterious reduce-reduce conflicts". There's no *real* conflict:
it's a naked procedure call if the end-of-statement follows; a `variable`
otherwise. There's no *real* mystery either: consider the command `a := b`.
By the state where LR(0) notices a `variable` produces `identifier`, it has
combined both sides of the assignment operator, and so LALR(1) gets confused.

The rest of this document is essentially a re-casting of
[this Pascal grammar reference](https://www.cs.utexas.edu/users/novak/grammar.html)
into the form MacroParse can use.

# Patterns
Comments are surrounded by curly braces. I'm not bothering with defining them to nest.
Space is not significant except where it's necessary to avoid confusion. There is some
confusion over whether spaces are allowed mid-number; I'm assuming not. Also, I'm going
to define the literal constant production rules in a slightly more sensible manner,
so that the letter `E` does not come out looking like a reserved word.
```
\{[^}]*\}              :ignore comment
\s+                    :ignore whitespace
\d+                    :integer
\d+\.\d+               :decimal
\d+\.\d+[eE][-+]?\d+   :scientific_notation
'([^']|'')*'           :string_constant
<|<=|=|<>|>=|>         :relop
{alpha}+               :word
{alpha}{alnum}+        :identifier
:=                     |
\.\.                   |
{punct}                :token
```
Note that in Pascal string constants, you escape `'` as `''`, whereas `"` needs no escaping.
That bit needs to be taken care of in the driver.

Pascal has a lot of keywords, and it's a case-insensitive language. For this example,
I'll assume that keyword recognition is done in the scanner-driver, for action `word`.
I'll spell keywords in ALL CAPS in the grammar rules, so there's a simple test.
Note also that Pascal does not seem to permit the underscore character in identifiers.
I wonder if that's an oversight corrected in a later version of the standard?

I've chosen to group relative operators in the lexer here: these *could* be thrown in with
all other generic tokens, but I expect there's a benefit to recognizing them specially.

# Productions module
A couple macro definitions help considerably: comma-separated list, semicolon-separated list,
and most kinds of such declarations as begin with a keyword.
```
csl(item) -> item       :first
| .csl(item) ',' .item  :append

ssl(item) -> item       :first
| .ssl(item) ';' .item  :append

decls(keyword,item) -> :empty | keyword .ssl(item) ';'
names -> csl(identifier)

```
Here is what might be called the backbone structure of a Pasacal program:
```
module -> PROGRAM identifier '(' names ')' ';' block '.'
block -> .labels .const_defs .type_defs .var_defs .subroutines BEGIN .ssl(stmt) END

labels -> :empty | LABEL .csl(integer) ';'
const_defs -> decls(CONST, c_decl)
type_defs -> decls(TYPE, t_decl)
var_defs -> decls(VAR, v_decl)

c_decl -> .identifier '=' .constant
t_decl -> .identifier '=' .type
v_decl -> .names ':' .type

subroutines -> :empty | .subroutines .signature ';' .block ';'  :append

signature -> PROCEDURE identifier formal_parameters
signature -> FUNCTION identifier formal_parameters ':' identifier

formal_parameters -> :empty | '(' .ssl(formal_group) ')'
formal_group -> .names ':' .identifier    :normal_args
	| FUNCTION .names ':' .identifier :func_args
	| PROCEDURE .names                :proc_args
```
Pascal is imperative. These are its statements and control structures:
```
stmt -> command :plain_stmt | .integer ':' .command :labeled_stmt
command -> :empty
	| .variable ':=' .expr           :assignment
	| .identifier                    :naked_procedure_call
	| .identifier '(' .csl(expr) ')' :parametric_procedure_call
	| BEGIN .ssl(stmt) END           :sequence
	| IF .expr THEN .stmt            :if_then
	| IF .expr THEN .stmt ELSE .stmt :if_then_else
	| CASE .expr OF .branches END    :case_selection
	| WHILE .expr DO .stmt           :while_loop
	| REPEAT .ssl(stmt) UNTIL .expr  :repeat_loop
	| FOR .identifier ':=' .expr .direction .expr DO .stmt   :for_loop
	| WITH .csl(variable) DO .stmt   :with_scope
	| GOTO .integer                  :goto_label

direction -> TO | DOWNTO

branches -> :empty | ssl(one_case)
one_case -> .csl(constant) ':' .stmt

```
Pascal supports a reasonable set of arithmetic and functional expressions.
The official standard resolves matters of precedence by defining non-terminals
for each layer, rather than relying on operator precedence specification.
```
expr -> simple
	| simple relop simple :relational_test
	| simple IN simple    :set_membership

simple -> signed_term | simple add_op term :sum
signed_term -> term | '+' .term | '-' .term :negate
term -> factor | term mul_op factor :product
add_op -> '+' | '-' | OR
mul_op -> '*' | '/' | DIV | MOD | AND
```
Here's a caveat: a function call without parameters looks just like a variable name.
The symbol table must resolve the question during semantic analysis.
```
factor -> string_contant
	| numeric
	| NIL
	| variable
	| .identifier '(' .csl(expr) ')' :parametric_function_call
	| '(' .expr ')'
	| NOT .factor                    :logical_inverse
	| '[' ']'                        :emmpty_set
	| '[' .csl(set_member) ']'       :full_set

set_member -> expr
	| .expr '..' .expr :range

variable -> identifier
	| .variable '[' .csl(expr) ']'  :array_element
	| .variable '.' .identifier     :field
	| .variable '^'                 :dereference

numeric -> integer | real
```
The type algebra has a few holes, but for it's day, it was decent, all things considered.
One thing that's a bit odd is that the size of an array is part of its type (at least
according to the official standard) so that means you have all these numbers working their
way through the type system, and *that* means access to named-constants in the process is
quite nice. Unfortunately, compile-time evaluation is limited to negation.  
```
constant -> string_constant
	| identifier        :named_constant
	| '+' .identifier   :named_constant
	| '-' .identifier   :negate_named_constant
	| numeric
	| '+' .numeric
	| '-' .numeric      :negate_numeric

type -> simple_type
	| '^' .identifier       :reference_type
	| collection
	| PACKED .collection    :packed

collection -> RECORD .field_list END
	| ARRAY '[' .csl(simple_type) ']' OF .type   :array_type
	| FILE OF .type          :file_type
	| SET OF .simple_type    :set_type

field_list -> struct           :simple_record
	| .struct CASE .identifier ':' .identifier OF .tags   :tagged_union
	| .struct CASE .identifier OF .tags                   :untagged_union

struct -> :emtpy | ssl(v_decl)
tags -> :empty | ssl(tag_group)
tag_group -> .csl(constant) ':' '(' .field_list ')'

``` 
# Precedence
This part is here mainly to resolve LR(1) conflicts in the grammar.
```
%right IF ELSE
```
