# SQL Error Taxonomy (Reference for Correction Agent)

> This is the canonical reference copy for the nl2sql-correction skill (the SQL-of-Thought orchestrator skill has been retired; the system prompt inlines the orchestration logic).

## Quick Diagnosis Checklist

When diagnosing a failed SQL query, scan each category in order and check all sub-categories:

### 1. Syntax (`syntax`)
- `syntax.sql_syntax_error` — General syntax violations (malformed queries, missing keywords)
- `syntax.invalid_alias` — Incorrect or conflicting table/column alias

### 2. Schema Link (`schema_link`)
- `schema_link.table_missing` — Required table not in the query
- `schema_link.col_missing` — Required column not referenced
- `schema_link.ambiguous_col` — Column name exists in multiple tables without qualification
- `schema_link.incorrect_foreign_key` — Wrong FK column in join condition

### 3. Join (`join`)
- `join.join_missing` — Required JOIN clause omitted
- `join.join_wrong_type` — Wrong join type (INNER vs LEFT/RIGHT). Use when rows that should have been **kept despite having no match** were dropped. If the returned rows are the **opposite set** (question asks for rows WITHOUT X, query returns rows WITH X), that is `set_ops.except_missing`.
- `join.extra_table` — Unnecessary table included
- `join.incorrect_col` — Wrong column in JOIN ON condition

### 4. Filter (`filter`)
- `filter.where_missing` — The query has **no row-level filtering at all** while the question clearly requires it. Do NOT use this to describe a missing exclusion / set-difference — that is `set_ops.except_missing`.
- `filter.condition_wrong_col` — Filter on wrong column
- `filter.condition_type_mismatch` — Type mismatch in comparison

### 5. Aggregation (`aggregation`)
- `aggregation.agg_no_groupby` — Aggregate function without GROUP BY
- `aggregation.groupby_missing_col` — GROUP BY missing a required column
- `aggregation.having_without_groupby` — HAVING without GROUP BY
- `aggregation.having_incorrect` — HAVING condition logically wrong
- `aggregation.having_vs_where` — Post-aggregation filter in WHERE instead of HAVING

### 6. Value (`value`)
- `value.hardcoded_value` — Literal value where column reference should be
- `value.value_format_wrong` — Date/string/numeric value in wrong format

### 7. Subquery (`subquery`)
- `subquery.unused_subquery` — Subquery result not referenced in outer query
- `subquery.subquery_missing` — Required nested query not implemented. Use this only when the missing subquery supplies a **value or comparison basis** (e.g. "above the department average", "higher than the overall max"). If the missing logic is "exclude / does not exist", use `set_ops.except_missing` instead.
- `subquery.subquery_correlation_error` — Correlated subquery references wrong outer column

### 8. Set Operations (`set_ops`)
- `set_ops.union_missing` — Required UNION not included
- `set_ops.intersect_missing` — Required INTERSECT not included
- `set_ops.except_missing` — Required set difference not implemented: the question asks for rows that do **NOT** match / do **NOT** exist. **Any of these forms counts** — `EXCEPT`, `NOT IN (subquery)`, `NOT EXISTS (subquery)`, `LEFT JOIN ... WHERE right.key IS NULL`. A "list X that have no Y" question belongs here, not in `filter` / `subquery` / `join`.

### 9. Other Issues (`other`)
- `other.order_by_missing` — Required sorting not applied
- `other.limit_missing` — Required row count restriction omitted
- `other.duplicate_select` — Same column selected multiple times
- `other.unsupported_function` — Function not available in SQLite
- `other.extra_values_selected` — More columns in SELECT than needed

## Diagnostic Priority Order

Scan categories in this priority order:
1. **Syntax** first (blocking errors — query cannot even parse)
2. **Schema Link** (structural correctness)
3. **Join** (multi-table correctness)
4. **Aggregation** (most common logical errors)
5. **Filter** (condition correctness)
6. **Subquery** (nested logic correctness)
7. **Set Operations** (UNION/INTERSECT/EXCEPT correctness)
8. **Value** (literal/format correctness)
9. **Other** (sorting, limits, redundancy)

> This order governs **detection** — what to look at first — not the final label. When two
> categories both look plausible, the label is decided by the decision rules below.

## Overlapping Codes: Decision Rules

Several codes describe neighbouring phenomena and are commonly mislabelled. Apply the
**first matching row** below, regardless of the scan order above:

| Failure shape | Final label | Do NOT use |
|---|---|---|
| The question asks for rows that do **not** match / do **not** exist ("without X", "never ordered", anti-join) | `set_ops.except_missing` | `subquery.subquery_missing`, `filter.where_missing`, `join.join_wrong_type` |
| The missing logic supplies a **value or comparison basis** ("above the group average", "higher than the overall max") | `subquery.subquery_missing` | `filter.where_missing` |
| The query has **no row-level filter at all**, and there is no exclusion or comparison semantics | `filter.where_missing` | — |
| Rows that should have been **kept despite having no match** were dropped (INNER where LEFT was needed) | `join.join_wrong_type` | `set_ops.except_missing` |
| A non-aggregated column is in SELECT but **missing from GROUP BY** (silently returns arbitrary values) | `aggregation.groupby_missing_col` | `other.extra_values_selected` — use that one only when the column *is* correctly grouped/aggregated but the question simply did not ask for it |

When a pair contains a **causal** defect and a **cosmetic** one, the causal one is always the
primary label: a wrong result beats a redundant column every time.

Deciding question for the hardest pair: *"does the answer require knowing what is
**absent**?"* If yes → `set_ops`; if it requires knowing a **magnitude to compare against**
→ `subquery`.

## Root Cause Identification

For each diagnosis:
1. **Primary root cause** — The single most impactful error category
2. **Secondary errors** — Additional issues that compound the root cause
3. **Repair strategy** — Concrete fix aligned with the identified taxonomy codes

> **List only what the failure evidence proves.** Every additional code sends the repair plan
> to change something that is not actually broken. If a code cannot be justified directly from
> the question, the SQL and the execution feedback, leave it out. When two codes describe the
> same defect, report the more specific one.

> Remember: Use concise error codes (e.g., `aggregation.agg_no_groupby`) not verbose descriptions.