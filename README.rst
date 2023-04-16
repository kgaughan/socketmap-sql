=============
socketmap-sql
=============

A socketmap_ script for interfacing with an SQL database.

.. _socketmap: http://www.postfix.org/socketmap_table.5.html

Why?
====

I have a number of FreeBSD_ servers, with one intended to act as my primary
mailserver (the current one and remaining one becoming secondary mailservers).
The problem is that I'm using Postfix_, and trying very hard to stick to
precompiled packages rather than using ports, and Postfix on FreeBSD lacks
bindings to databases. In my case, I wanted to be able to use an SQL database.

.. _FreeBSD: https://www.freebsd.org/
.. _Postfix: http://www.postfix.org/

Configuration format
====================

Configuration files are INI files containing two types of section.

First is the ``[database]`` section, which gives database connection details.
The *driver* field specifies the driver to use; if omitted, its value defaults
to *sqlite3*. The remaining fields are passed to the driver's ``connect()``
function.

::

    [database]
    driver = sqlite3
    database = /path/to/sqlite.db

Other sections start with ``table:``, and denote virtual tables to be queried.
There are two fields: *transform* (optional) and *query* (required).

The *transform* field gives the name of a transformation to apply to the query
parameter before its use in the query the query. The default is to accept the
parameter as-is (*all*). Other values can be a reference to a Python function
in the form 'module:function', *local* for just the local part, *domain* for
the domain part of the address, and *split* breaks an email address in two.
It must return a list or tuple giving the postitional arguments to use in the
query.

The *query* field give an SQL query to be used to generate the synthetic table.
Use placeholders as specified by the database driver's documentation.

Usage
=====

Run with::

    socketmap-sql --config /path/to/config.ini

If you don't provide the *--config* flag, it defaults to
``/etc/socketmap-sql.ini``.

Postfix
=======

This script is intended to be executed by Postfix's spawn_ mechanism, meaning
it reads its input and writes its output to stdin and stdout respectively.

.. _spawn: http://www.postfix.org/spawn.8.html

Assuming you've installed the script in ``/usr/local/libexec``, add the
following to ``master.cf``::

    sockmapd  unix  -      -       n       -       1       spawn
      user=nobody argv=/usr/local/libexec/socketmap-sql

Compatibility
=============

The script only works on Python 3.8+.

.. vim:set ft=rst:
