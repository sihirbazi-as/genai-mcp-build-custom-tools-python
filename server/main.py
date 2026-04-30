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

if __name__ == "__main__":
    mcp.run(transport="sse")