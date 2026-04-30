import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from neo4j import AsyncGraphDatabase, AsyncDriver
from mcp.server.fastmcp import Context, FastMCP
from dotenv import load_dotenv
load_dotenv()

# 1. Define a context class to hold your resources
@dataclass
class AppContext:
    """Application context with shared resources."""
    driver: AsyncDriver
    database: str


# 2. Create the lifespan context manager
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle."""

    # Startup: Read credentials from environment variables
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE")

    # Initialize the Neo4j driver
    driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    try:
        # Yield the context with initialized resources
        yield AppContext(driver=driver, database=database)
    finally:
        # Shutdown: Clean up resources
        await driver.close()


# 3. Pass lifespan to the server
mcp = FastMCP("Movies GraphRAG Server", lifespan=app_lifespan)


@mcp.tool()
async def list_movies_by_genre(genre: str, ctx: Context, cursor: str ="0", total_page: int =20) -> dict:
    """
    Get paginated movies list by genre.

    Args:
        genre: The genre of the Movie.
    
    Returns:
        A dictionary that contains list of movies with details, current_page that already fetched movies, next_cursor is specify next limit when user request more movie.
    """
    driver = ctx.request_context.lifespan_context.driver
    database = ctx.request_context.lifespan_context.database
    skip = int(cursor)
    
    result, _, _ = await driver.execute_query(
        """MATCH (m:Movie)-[:IN_GENRE]-(g:Genre) WHERE g.name = $genre ORDER BY m.title RETURN m.title AS title, m.released AS released_at, m.imdbRating AS rating SKIP $skip LIMIT $limit """
    ,
    skip=skip,
    genre=genre,
    limit=total_page,
    database_ = database
    )
    
    movies = [dict(record) for record in result]
    
    return {
        "movies": movies,
        "current_page": skip + total_page,
        "next_cursor": (skip + total_page * 2)
    }




@mcp.resource("movie://{tmdb_id}")
async def get_movie(tmdb_id: str, ctx: Context) -> str:
    """
    Get detailed information about a specific movie by TMDB ID.

    Args:
        tmdb_id: The TMDB ID of the movie (e.g., "603" for The Matrix)

    Returns:
        Formatted string with movie details including title, plot, cast, and genres
    """
    await ctx.info(f"Fetching movie details for TMDB ID: {tmdb_id}")

    context = ctx.request_context.lifespan_context

    try:
        records, _, _ = await context.driver.execute_query(
            """
            MATCH (m:Movie {tmdbId: $tmdb_id})
            RETURN m.title AS title,
               m.released AS released,
               m.tagline AS tagline,
               m.runtime AS runtime,
               m.plot AS plot,
               [ (m)-[:IN_GENRE]->(g:Genre) | g.name ] AS genres,
               [ (p)-[r:ACTED_IN]->(m) | {name: p.name, role: r.role} ] AS actors,
               [ (d)-[:DIRECTED]->(m) | d.name ] AS directors
            """,
            tmdb_id=tmdb_id,
            database_=context.database
        )

        if not records:
            await ctx.warning(f"Movie with TMDB ID {tmdb_id} not found")
            return f"Movie with TMDB ID {tmdb_id} not found in database"

        movie = records[0].data()

        # Format the output
        output = []
        output.append(f"# {movie['title']} ({movie['released']})")
        output.append("")

        if movie['tagline']:
            output.append(f"_{movie['tagline']}_")
            output.append("")

        output.append(f"**Runtime:** {movie['runtime']} minutes")
        output.append(f"**Genres:** {', '.join(movie['genres'])}")

        if movie['directors']:
            output.append(f"**Director(s):** {', '.join(movie['directors'])}")

        output.append("")
        output.append("## Plot")
        output.append(movie['plot'])

        if movie['actors']:
            output.append("")
            output.append("## Cast")
            for actor in movie['actors']:
                if actor['role']:
                    output.append(f"- {actor['name']} as {actor['role']}")
                else:
                    output.append(f"- {actor['name']}")

        result = "\n".join(output)

        await ctx.info(f"Successfully fetched details for '{movie['title']}'")

        return result

    except Exception as e:
        await ctx.error(f"Failed to fetch movie: {str(e)}")
        raise

# 4. Access the driver in your tools
@mcp.tool()
async def graph_statistics(ctx: Context) -> dict[str, int]:
    """Count the number of nodes and relationships in the graph."""

    # Access the driver from lifespan context
    driver: AsyncDriver = ctx.request_context.lifespan_context.driver
    database = ctx.request_context.lifespan_context.database

    # Use the driver to query Neo4j
    records, summary, keys = await driver.execute_query(
        "RETURN COUNT {()} AS nodes, COUNT {()-[]-()} AS relationships"
        ,database_=database
    )

    # Process the results
    if records:
        return dict(records[0])
    return {"nodes": 0, "relationships": 0}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")