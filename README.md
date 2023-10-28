# NCVR Identification Query Tool

This repository contains a script which can run identification queries against the North Carolina Voter Registration database.
The database is a public source of personally identifiable information and commonly used in record linkage research as a test dataset.
This tool enables you to run queries to find out how many people are uniquely identifiable by any combination of attributes.

## Setup

You will need to install [Python](https://www.python.org/downloads/), [Poetry](https://python-poetry.org/docs/), [Docker](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install/).
Clone this repository.
Open a terminal and change into the root directory of this repository.
Run `poetry install`.
This will install the script and all of its dependencies.
Check if it worked by running `poetry run ncvr --help`.

```
$ poetry run ncvr --help
Usage: ncvr [OPTIONS] COMMAND [ARGS]...

Options:
  -c, --connection-uri TEXT  Database connection string  [default: postgresql:
                             //ncvr:ncvr@localhost:5432/ncvr?sslmode=disable]
  --help                     Show this message and exit.

Commands:
  count  Count rows in table.
  list   List all available column names.
  query  Run an identification query.
```

Change into the [Docker directory](./docker) and run `docker compose up -d`.
This will start a Postgres instance on your machine.
If you're starting it for the first time, the latest NCVR records will be pulled and inserted into the database.
Depending on your machine's performance and network connection, this might take a while.
The database is ready when `docker compose logs` shows the following line.

```
$ docker compose logs
...
2023-10-10 18:39:52.763 UTC [1] LOG:  database system is ready to accept connections
```

## Usage

### Count the amount of valid records

You can get the total amount of records that abide by the following rules by running `poetry run ncvr count`.
These are the records that will be used for identification queries.

- record is not marked as confidential
- record is marked as active
- person was eligible to vote at their date of registration
- person is no older than 120 years by the end of the year
- residential and mail zip code does not consist of all zeros
- phone number does not consist of all zeros
- zip code consist of either five or nine digits

```
$ poetry run ncvr count
+---------+
|   Count |
+---------+
| 6152174 |
+---------+
```

### Get the list of attributes

To get a list of all attributes that you can use to run identification queries, use `poetry run ncvr list`.

```
$ poetry run ncvr list
+-------------------+-------------------+-------------+
| Name              | Type              | Max. length |
+-------------------+-------------------+-------------+
| age_at_year_end   | integer           |        None |
| birth_state_cd    | character varying |           2 |
| birth_year        | integer           |        None |
...
| res_state_cd      | character varying |           2 |
| res_street        | character varying |          65 |
| res_zip           | character         |           9 |
+-------------------+-------------------+-------------+
```

### Run an identification query

Use `poetry run ncvr query` to run an identification query against the NCVR database.
You may select any combination of attributes. 
You can prepend an exclamation mark `!` to an attribute to ensure that all records have this attribute set, meaning that it's not empty.
You can also use a simplified version of Python's slice notation to use substrings from attributes in your query.

For example:

- `poetry run query first_name` queries people that are uniquely identifiable by their first name
- `poetry run query first_name last_name` queries people that are uniquely identifiable by their first and last name
- `poetry run query first_name "last_name[0]"` queries people that are uniquely identifiable by their first name and the first character of their last name
- `poetry run query "first_name[0:2]" "last_name[1:3]"` queries people that are uniquely identifiable by the first two characters of their first name and the two characters after the first character of their last name

```
$ poetry run ncvr query first_name "last_name[0]"
+------+--------+--------+--------+----------+
| Size |  Count |  Total | One of |    Ratio |
+------+--------+--------+--------+----------+
|    1 | 411079 | 411079 |     20 | 0.066818 |
|    2 |  63796 | 127592 |     50 | 0.020739 |
|    3 |  26547 |  79641 |     80 | 0.012945 |
|    4 |  15161 |  60644 |    200 | 0.009857 |
|    5 |   9873 |  49365 |    200 | 0.008024 |
+------+--------+--------+--------+----------+
```

Looking at the third row of the table, the result reads as follows: "There are 26,547 people, or roughly one in 80 people, who share the first name and the first character of their last name with two other people. These people make up 1.29% of the total population."

The amount of attributes that you put into your query affects the runtime of the query.
Go wild and try some complex attribute combinations, but be aware that the resulting queries might end up taking quite a bit more time.

## License

MIT.

[The NCVR data is publicly provided by the North Carolina State Board of Elections.](https://www.ncsbe.gov/results-data/voter-registration-data)