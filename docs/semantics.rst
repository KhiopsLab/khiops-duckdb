Export format
=============

File
----

* Tab-separated text with a header line: Khiops' default format.
* Line breaks inside values become spaces, so one record is one line.
* Missing values are empty quoted fields (``""``).
* An existing file is replaced. Its folder must exist.
* Without a dictionary, every column is written, unsorted.

Types
-----

.. list-table::
   :header-rows: 1
   :widths: 34 38 28

   * - DuckDB type
     - Exported text
     - Khiops type
   * - Integers, ``DECIMAL``
     - As DuckDB prints them
     - ``Numerical``
   * - ``FLOAT``, ``DOUBLE``
     - The same; NaN and infinity are missing
     - ``Numerical``
   * - ``VARCHAR``, ``ENUM``, ``UUID``, ``BOOLEAN``
     - Text
     - ``Categorical``
   * - ``DATE``
     - ``2026-01-02``
     - ``Date``
   * - ``TIME``
     - ``12:34:56.123``
     - ``Time``
   * - ``TIMESTAMP``
     - ``2026-01-02 12:34:56.123``
     - ``Timestamp``
   * - ``TIMESTAMPTZ``
     - The same, in UTC
     - ``Timestamp``
   * - Lists, structs, ``BLOB``, intervals
     - DuckDB's text form
     - None: cast in SQL, or declare ``Text``

* Key columns are ``Categorical``.
* A text column can be declared any type; its content must match.
* Any other column can only be declared ``Categorical``, ``Text`` or its type
  above. To change the values, cast in SQL.

Dates and times
---------------

A format declared in the dictionary is the format written:

.. code-block:: text

   Date       since   ; <DateFormat="DD/MM/YYYY">             04/03/2026
   Time       opened  ; <TimeFormat="(H)H:(M)M">              5:6
   Timestamp  seen    ; <TimestampFormat="YYYYMMDDHHMMSS.">   20260304050607.089

* Every date, time and timestamp format Khiops documents is supported. An
  unknown format is rejected.
* Without a declared format, Khiops' native formats are used.
* Fractions of a second are truncated to milliseconds, Khiops' precision.
* ``TIMESTAMPTZ`` is converted to UTC. Declared ``TimestampTZ``, it is written
  with its ``+00:00`` zone.
* A text column is never reformatted.

Cloud storage
-------------

``output_data_table_path`` can be a cloud URI your DuckDB connection can write.
On ``s3://`` and ``gs://``, a ``*`` in the file name writes several files and
returns the pattern, which Khiops' cloud drivers read as one table:

.. code-block:: python

   data_table_path = export_data_table(
       customers, "gs://bucket/customers/part-*.tsv",
       dictionary_domain, "Customer",
   )

* DuckDB splits the data, one file per writer thread.
* The target folder must be empty.
* Not available for a table sorted by a key: a sorted table is one file.
* Not covered by this project's automated tests.

Not checked
-----------

The export does not validate the data. Duplicate or missing keys and
unparsable values are reported by Khiops, for example by ``kh.check_database``.
