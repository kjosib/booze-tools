# Calculator Example
This is an example scanner/grammar for a simple desktop calculator with variable
assignment and recollection. It mainly exists to exercise and demonstrate the
precedence-parsing facility of `MacroParse`, but also shows one way a `MacroParse`
definition can be integrated into a real application.

A driver and functional application are at [calculator.py](calculator.py).
Testcases are [here](../tests/test_examples.py)

For a rather more verbose tutorial introduction to most of `MacroParse`, please
see [json.md](json.md) in this folder.

# Precedence
Unlike Bison or Yacc, highest-precedence comes first. After all, that's the way
you learned it in grade school!
```
%bogus UMINUS
%right '^'
%left '*' '/'
%left '+' '-'
```
The declaration `%bogus` introduces a name for a precedence level that can only be
used as a rule's `%prec` symbol, which you can see illustrated below for unary negation.
In case you're wondering, it's how we make `-1 ^ 2` = `1`.

You can also use `%nonassoc` in the usual way, but this example does not require that.
The larger [Decaf Example](decaf.md) uses it to prevent things like `a > b < c`, which
admittedly *can* be made sense of, but they aren't part of the Decaf language specification.

And finally, this grammar is LALR and does not need the full LR-1 treatment,
so we can do this:

```
%method LALR
```

# Productions START
The productions for this are pretty normal. Unlike the JSON example,
it doesn't bother with `%void` symbol declarations and just uses the `.` to
express which places in the right-hand-side are significant to the
parse-action functions.
```
START -> .E                :evaluate
      | .variable '=' .E   :assign
      | '?'                :help

E -> '(' .E ')'
  | .E '+' .E   :add
  | .E '-' .E   :subtract
  | .E '*' .E   :multiply
  | .E '/' .E   :divide
  | .E '^' .E   :power
  | '-' .E      :negate  %prec UMINUS
  | variable    :lookup
  | number
```
But lo, the users will make mistakes. Some error productions are a fabulous help.
```
START -> $error$      :complete_garbage
E -> '(' .$error$ ')' :broken_parenthetical
```

## Definitions
In contrast to the JSON example, this scanner does not attempt to recognize negative numbers.
This allows expressions like `3-1i` (without whitespace) to function properly.
```
mantissa        (0|[1-9]\d*)(\.\d+)?
exponent        [Ee][-+]?\d+
real            {mantissa}{exponent}? 
```
## Patterns
Nothing fancy here, but the observant will note that complex numbers are supported.
```
{real}             :real
{real}[iI]         :imaginary
{alpha}{word}*     :variable
\s+                :ignore_whitespace
{punct}            :punctuation
```
