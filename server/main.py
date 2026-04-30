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

@mcp.tool()
async def query_specific_genre(genre: str, limit: int = 10, ctx: Context = None) -> dict[str, list]:
    """Query movies by a specific genre.
    
    Args:
        genre: The genre name to filter by (e.g., "Action", "Comedy")
    
    Returns:
        A dictionary containing the list of movies in that genre.
    """
    driver: AsyncDriver = ctx.request_context.lifespan_context.driver
    database = ctx.request_context.lifespan_context.database
    
    await ctx.info(message=f"Querying movies for genre: {genre}")
    records, summary, keys = await driver.execute_query(
       """
MATCH (m:Movie)-[:IN_GENRE]-(g:Genre) WHERE g.name = $genre RETURN m.title AS title, m.year AS year, m.imdbRating AS rating LIMIT $limit""",
        limit=limit,
        genre=genre,
        database_=database
    )

    movies = [dict(record) for record in records]
    return {"movies": movies}



if __name__ == "__main__":
    mcp.run(transport="streamable-http")