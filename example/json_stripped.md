This excerpt removes all the tutorial fluff from the JSON syntax definition in
the [first tutorial](json.md) and fits in 35 lines, not counting this sentence.
## Definitions
```
wholeNumber     [1-9]\d*
signedInteger   -?(0|{wholeNumber})
fractionalPart  \.\d+
exponent        [Ee][-+]?\d+
```
## Patterns
```
{signedInteger}                               :integer
{signedInteger}{fractionalPart}?{exponent}?   :float
\s+                                           :ignore_whitespace
[][{}:,]                                      :punctuation
true|false|null                               :reserved_word
"                                             :enter_string
```
## Patterns in_string
```
"               :leave_string
[^\\"]+         :stringy_bit
\\["/\\]        :escaped_literal
\\[bfnrt]       :shorthand_escape
\\u{xdigit}{4}  :unicode_escape
```
## Productions: value
```
list_of(item) -> :empty | one_or_more(item)
one_or_more(item) -> item :first | .one_or_more(item) `, .item :append

value => string | number | object | array | true | false | null
object ::= '{ .list_of(key_value_pair) '} :object
array = '[ .list_of(value) ']
key_value_pair -> .string `: .value
string : `" .text `" :string
text ==> :empty | text character :append
```