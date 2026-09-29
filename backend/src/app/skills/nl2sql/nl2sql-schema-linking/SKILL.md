---
name: nl2sql-schema-linking
description: "TRIGGER when: the NL2SQL pipeline needs to identify relevant database tables, columns, primary keys, foreign keys, and join relationships for a natural language question; user wants schema context extraction for a query; user asks which tables/columns are needed for a given question. This skill is Step 1 in the SQL-of-Thought pipeline and should be used BEFORE subproblem decomposition and query planning. SKIP when: user provides a complete schema context already; user asks SQL questions without needing schema discovery."
---

# NL2SQL Schema Linking Agent

## Overview

The Schema Linking Agent is the **first step** in the SQL-of-Thought pipeline. It parses the natural language question in conjunction with the database schema to identify the relevant tables, columns, primary keys, foreign keys, and join relationships needed to answer the query.

This step constrains SQL generation to schema-relevant entities, reducing hallucinations and ensuring structural correctness in downstream stages.

## Role in Pipeline

```
Input:  Natural language question (Q) + Database identifier (db_id)
Output: Cropped schema (S) — relevant tables, columns, PKs, FKs, join relationships
Next:   → nl2sql-subproblem (Step 2)
```

## Process

### Step 1: Retrieve Schema Knowledge via FalkorDB Graph Retrieval

Use the graph retrieval tools to discover relevant schema information:

1. **`find_relevant_schema_tool`** — Retrieve the cropped schema for the question
   ```
   find_relevant_schema_tool({ user_query: "Which tables contain customer order information and their payment status?",
                               graph_id: "<FalkorDB Graph ID from the connection context>" })
   ```
   Internally it (a) has an LLM rewrite the question into table-purpose and column-content
   descriptions, (b) vector-searches the `Table` and `Column` embeddings in FalkorDB, then
   (c) graph-traverses foreign-key neighbourhoods and table-to-table shortest paths to add
   JOIN bridge tables. It returns `tables` plus a prompt-ready `schema_text`.

2. **`get_graph_list_tool`** — List available schema graphs
   ```
   get_graph_list_tool({})
   ```
   Always pass the connection's `graph_id` explicitly. With several graphs present an empty id
   may resolve to a memory graph and retrieval will fail.

3. **If no schema graph exists yet** — ask the user to connect the database first (`/database`
   API: DDL upload or live connection). Never generate SQL from a vague schema description.

### Step 2: Schema Linking Reasoning (Chain-of-Thought)

Perform structured reasoning to link the question to schema entities:

```
Given question: "Find the average salary of employees in departments with more than 10 people"

Schema Linking Reasoning:
1. The question mentions "employees" → likely maps to `employees` table
2. "salary" → likely maps to `salary` column in `employees` table
3. "departments" → likely maps to `departments` table
4. "more than 10 people" → implies counting employees per department → needs `dept_id` column
5. Join relationship: `employees.dept_id` → `departments.dept_id` (foreign key)

Cropped Schema Output:
- Tables: employees, departments
- Columns: employees.salary, employees.dept_id, departments.dept_name, departments.dept_id
- Primary Keys: departments.dept_id
- Foreign Keys: employees.dept_id → departments.dept_id
- Join: employees JOIN departments ON employees.dept_id = departments.dept_id
```

### Step 3: Format Output

The cropped schema output must include:
- **Table names** — Only tables relevant to the question
- **Column names** — Only columns needed (not all columns in the table)
- **Primary keys** — For relevant tables
- **Foreign keys** — For join relationships
- **Join paths** — How relevant tables connect

## Best Practices

- **Be conservative**: Include only directly relevant tables/columns. Extra entities distract downstream agents.
- **Trace join paths**: If the question involves multiple tables, explicitly identify the join path through foreign keys.
- **Handle ambiguity**: When a term could map to multiple columns (e.g., "name" → first_name vs last_name), list both as candidates and note the ambiguity.
- **Note retrieval provenance**: Distinguish entities that came from vector hits vs. those added by FK/shortest-path expansion, so downstream agents know what was structurally implied rather than directly asked for.

## Common Pitfalls

| Pitfall | Correction |
|---------|-----------|
| Missing a required table for JOIN | `find_relevant_schema_tool` already expands via FK chains and table-to-table shortest paths — if a bridge table is still absent, query the join path explicitly |
| Including all columns instead of relevant ones | Only include columns explicitly mentioned or structurally required |
| Ignoring composite foreign keys | Composite FKs arrive as several `keyType=FK` columns in `schema_text`; check the whole column list, not just the first match |
| Mapping NL terms to wrong columns | Consult the semantic model section (business names / synonyms / enum descriptions) injected into the system prompt |

## Output Template

```json
{
  "tables": ["table1", "table2"],
  "columns": {
    "table1": ["col_a", "col_b", "col_id"],
    "table2": ["col_c", "col_d", "table1_id"]
  },
  "primary_keys": {
    "table1": "col_id",
    "table2": "col_d"
  },
  "foreign_keys": {
    "table2.table1_id": "table1.col_id"
  },
  "join_paths": [
    "table2 JOIN table1 ON table2.table1_id = table1.col_id"
  ],
  "reasoning": "Step-by-step schema linking logic..."
}
```