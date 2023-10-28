from typing import NamedTuple, Never

import click
import psycopg
from click import Context
from prettytable import PrettyTable
from psycopg import Connection


class PgColumnDef(NamedTuple):
    name: str
    type: str
    max_len: int | None


class QueryColumnSpec(NamedTuple):
    name: str
    range: tuple[int, int] | None
    not_null: bool


def _echo_and_exit(message: str, code: int = 1) -> Never:
    click.secho(message, fg="red", err=True)
    exit(code)


def _connect_pg(connection_uri: str):
    return psycopg.Connection.connect(connection_uri)


def _parse_query_column(column_query: str):
    def _int(val):
        try:
            return int(val)
        except ValueError:
            raise ValueError("range start/end must be a valid integer")

    not_null = False

    if column_query[0] == "!":
        column_query = column_query[1:]
        not_null = True

    range_start_idx = column_query.find("[")

    # no range specified, return as is
    if range_start_idx == -1:
        return QueryColumnSpec(column_query, None, not_null)

    col_name = column_query[:range_start_idx]
    # assume that the last character is a closing square bracket
    col_range_spec = column_query[range_start_idx + 1:-1]
    col_range_parts = col_range_spec.split(":")

    match len(col_range_parts):
        case 1:
            x = _int(col_range_parts[0])
            return QueryColumnSpec(col_name, (x, x + 1,), not_null)
        case 2:
            x = _int(col_range_parts[0])
            y = _int(col_range_parts[1])

            if y <= x:
                raise ValueError("end of range must be after start of range")

            if x < 0:
                raise ValueError("start of range must not be lower than zero")

            return QueryColumnSpec(col_name, (x, y,), not_null)
        case _:
            raise ValueError("range specification must contain at most one colon ':' character")


def _query_columns(conn: Connection):
    cur = conn.execute("""
        SELECT attname, format_type(atttypid, atttypmod)
        FROM pg_catalog.pg_attribute
        WHERE attrelid = 'ncvr_plausible'::regclass
        AND attnum > 0
        """)

    def _parse_column(row):
        col_name = row[0]
        col_type = row[1]
        col_max_len = None

        max_len_idx = col_type.find("(")

        # check if there's a length in the data type
        if max_len_idx != -1:
            col_max_len = int(col_type[max_len_idx+1:-1])
            col_type = col_type[:max_len_idx]

        return PgColumnDef(col_name, col_type, col_max_len)

    return [_parse_column(row) for row in cur]


def _count_rows(conn: Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM ncvr_plausible")
    row = cur.fetchone()

    return row[0]


@click.group()
@click.option(
    "-c", "--connection-uri",
    default="postgresql://ncvr:ncvr@localhost:5432/ncvr?sslmode=disable",
    help="Database connection string",
    show_default=True
)
@click.pass_context
def cli(ctx: Context, connection_uri: str):
    ctx.ensure_object(dict)
    ctx.obj["CONNECTION_URI"] = connection_uri


@cli.command("query")
@click.argument("query", nargs=-1)
@click.option("-l", "--limit", default=5, help="Group size limit")
@click.pass_context
def run_query(
        ctx: Context,
        query: tuple[str],
        limit: int
):
    """Run an identification query."""
    if len(query) == 0:
        _echo_and_exit("Query needs to contain at least one column")

    query_spec: list[QueryColumnSpec] = []

    for q in query:
        try:
            query_spec.append(_parse_query_column(q))
        except ValueError as e:
            _echo_and_exit(f"Failed to parse query: {e}")

    with _connect_pg(ctx.obj["CONNECTION_URI"]) as conn:
        pg_cols = _query_columns(conn)
        pg_col_dict: dict[str, PgColumnDef] = {col.name: col for col in pg_cols}
        pg_query_parts: list[str] = []
        pg_not_null_column_names: list[str] = []

        # validate user query
        for query_col in query_spec:
            if query_col.name not in pg_col_dict:
                _echo_and_exit(f"Unknown column: {query_col.name}")

            query_col_def = pg_col_dict[query_col.name]

            # add the column to the WHERE clause if it's explicitly supposed to be not null.
            # this only works on char types since year of birth, age at year-end and registration date are always set.
            # so in a sense, the not-null option has no effect on anything but char cols.
            if query_col.not_null and "character" in query_col_def.type:
                pg_not_null_column_names.append(query_col.name)

            # if the user specified a range, check if the column supports it
            if query_col.range is not None:
                if query_col_def.max_len is None:
                    _echo_and_exit(f"Column does not support character ranges: {query_col.name}")

                if query_col.range[1] > query_col_def.max_len:
                    _echo_and_exit(f"End index out of bounds: {query_col.name} has a maximum length of "
                                   f"{query_col_def.max_len} but the end index is {query_col.range[1]}")

                # strings are 1-indexed in pg
                pg_substr_start = query_col.range[0] + 1
                pg_substr_len = query_col.range[1] - query_col.range[0]

                pg_query_parts.append(f"SUBSTRING({query_col.name} FROM {pg_substr_start} FOR {pg_substr_len})")
            else:
                pg_query_parts.append(query_col.name)

        pg_query_select = " || '#' || ".join(pg_query_parts)
        record_count = _count_rows(conn)

        inner_query = "SELECT COUNT(*) AS grp_sz FROM ncvr_plausible"

        if len(pg_not_null_column_names) != 0:
            # first append the " <> ''" bit to every column
            where_not_null_cols = [f"{not_null_col} <> ''" for not_null_col in pg_not_null_column_names]
            # then join them with 'AND' into the statement
            inner_query += f" WHERE {' AND '.join(where_not_null_cols)}"

        inner_query += f" GROUP BY {pg_query_select}"

        cur = conn.execute(f"""
            SELECT grp_sz, COUNT(*) AS grp_cnt FROM ({inner_query}) tab_grp
            WHERE grp_sz <= %(max_group_size)s::integer
            GROUP BY grp_sz
            ORDER BY grp_sz ASC
            """, {"max_group_size": limit})

        def _construct_table_row(row):
            nonlocal record_count
            group_size = row[0]
            group_count = row[1]
            group_total = group_size * group_count
            group_ratio = group_total / record_count

            order, magnitude = 1, 1

            while (1 / (magnitude * order)) > group_ratio:
                magnitude += 1
                magnitude %= 10

                if magnitude == 0:
                    magnitude += 1
                    order *= 10

            group_one_of = order * magnitude

            return group_size, group_count, group_total, group_one_of, round(group_ratio, 6)

        tab = PrettyTable()
        tab.field_names = ["Size", "Count", "Total", "One of", "Ratio"]
        tab.add_rows(_construct_table_row(row) for row in cur)
        tab.align = "r"

        click.echo(tab)


@cli.command("count")
@click.pass_context
def count_rows(ctx: Context):
    """Count rows in table."""
    with _connect_pg(ctx.obj["CONNECTION_URI"]) as conn:
        count = _count_rows(conn)

        tab = PrettyTable()
        tab.field_names = ["Count"]
        tab.add_row((count,))
        tab.align = "r"

        click.echo(tab)


@cli.command("list")
@click.pass_context
def list_columns(ctx: Context):
    """List all available column names."""
    with _connect_pg(ctx.obj["CONNECTION_URI"]) as conn:
        pg_cols = _query_columns(conn)

        tab = PrettyTable()
        tab.field_names = ["Name", "Type", "Max. length"]
        tab.add_rows(pg_cols)
        tab.align = "l"
        tab.align["Max. length"] = "r"

        click.echo(tab.get_string(sortby="Name"))


if __name__ == "__main__":
    cli()
