---
title: Prevent SQL Injection with Parameterized Queries
impact: CRITICAL
impactDescription: Eliminates the #1 database attack vector; prevents data breach, data loss, or full database compromise
tags: security, sql-injection, parameterized-queries, orm
---

## Prevent SQL Injection with Parameterized Queries

String-concatenated or interpolated SQL lets an attacker inject arbitrary SQL through user input. Always bind user input as query parameters — never build SQL text by concatenating or interpolating values.

**Incorrect (string concatenation — injectable):**

```sql
-- C# / .NET
var sql = "SELECT * FROM users WHERE email = '" + email + "'";
var cmd = new SqlCommand(sql, connection);

-- Python
cur.execute("SELECT * FROM users WHERE email = '" + email + "'")
cur.execute(f"SELECT * FROM users WHERE email = '{email}'")
```

**Correct (parameterized query):**

```sql
-- C# / .NET
var sql = "SELECT * FROM users WHERE email = @email";
var cmd = new SqlCommand(sql, connection);
cmd.Parameters.AddWithValue("@email", email);

-- Python (psycopg2)
cur.execute("SELECT * FROM users WHERE email = %s", (email,))

-- Python (psycopg2, named params)
cur.execute("SELECT * FROM users WHERE email = %(email)s", {"email": email})
```

ORM query builders (Entity Framework, Dapper with parameters, SQLAlchemy, Django ORM) parameterize automatically — the risk is specifically raw/dynamic SQL built with string concatenation or f-strings/string interpolation.

Reference: [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
