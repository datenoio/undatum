## ADDED Requirements

### Requirement: Safe Rule Expression Evaluation
Cross-field rule conditions SHALL be evaluated by a restricted expression evaluator that supports
only comparisons, boolean and arithmetic operators, literals, field references and a documented
function set, and MUST NOT execute arbitrary Python.

#### Scenario: Supported condition
- **WHEN** a rule has `condition: "start_date <= end_date and amount > 0"`
- **THEN** the condition is evaluated for each record

#### Scenario: Code execution attempt rejected
- **WHEN** a rule has `condition: "().__class__.__bases__[0].__subclasses__()"`
- **THEN** validation stops with a rule syntax error naming the unsupported construct

#### Scenario: Field named like a keyword
- **WHEN** a dataset has a field named `or` and a rule references it
- **THEN** the field value is used and the expression is not corrupted
