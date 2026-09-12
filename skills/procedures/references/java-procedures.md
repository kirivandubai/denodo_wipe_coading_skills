# Java stored procedures

A compiled class, packaged in a JAR, imported into the server and then registered with
`CREATE PROCEDURE`. The oldest of the three kinds and the only one that can do things VQL
cannot — call an external library, open a socket, run arbitrary Java.

**Before reaching for this, check whether a VQL procedure does the job**
(`vql-procedures.md`). The documentation's own list of reasons is: no Java to write, no
recompile-package-import cycle to repeat on every change, and a definition other people can
read without downloading a JAR.

## The statements

```sql
-- unverified: только по документации 9.5
CREATE [OR REPLACE] PROCEDURE <name>
    CLASSNAME '<fully qualified class>'
    [ CLASSPATH '<path to jars>' ]
    [ JARS '<jar name>' [, '<jar name>']* ]
    [ FOLDER = '<path>' ]
    [ DESCRIPTION = '<text>' ]
    [ CHECK_INDIRECT_ACCESS { ON | OFF } ];

ALTER PROCEDURE <name>
    [ CLASSNAME '<class>' ]
    [ CLASSPATH = '<path>' ]
    [ JARS '<jar name>' [, '<jar name>']* ]
    [ CHECK_INDIRECT_ACCESS { ON | OFF } ];
```

Note the shape differences from `CREATE VQL PROCEDURE`: no parameter list (the Java class
declares its own schema), no body, and `FOLDER =` among the ordinary clauses rather than
before a parameter list.

## What has to exist first

The JAR is imported into the server as an extension (Administration Guide, *Importing
Extensions*) and then named in `JARS`. Until the class is inside an imported JAR, the
statement fails on creation:

```
error storing procedure: Unable to find class 'com.acme.denodo.OrderEnrichment'
```

*verified: 9.5.1 (стенд, 2026-09-12) — the failure, not the success: importing a JAR is
outside what this repository can do on the stand, so the working form stays unverified.*

`CLASSPATH` points at JAR files on the machine instead, and the documentation recommends
against it: the procedure then depends on a path existing on that particular server.

`CHECK_INDIRECT_ACCESS ON` makes the server check the `INDIRECT_ACCESS` privilege on the
views the procedure reads, when that privilege is enabled server-wide.

## Everything else is the same

Calling, reading the signature, using it inside a view, dropping it — a Java procedure is
invoked and inspected exactly like a VQL one:
`SELECT … FROM <name>() WHERE <input> = …`, `DESC PROCEDURE <name>`,
`DROP PROCEDURE [IF EXISTS] <name> [CASCADE]`. In `GET_ELEMENTS()` it shows up as
`type = 'storedProcedure'` with a `subtype` other than `user defined - vql`.

Writing the Java class itself — the interfaces to implement, the libraries to compile
against — is in the Developer Guide,
`vdp/developer/developing_extensions/developing_stored_procedures/`.

## Documentation

`vdp/vql/stored_procedures/importing_a_stored_procedure/importing_a_stored_procedure` under
`https://community.denodo.com/docs/html/accessible/9.5/`.
