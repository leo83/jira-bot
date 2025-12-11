#!/usr/bin/env python3
"""
Migration script to populate jira_issue_details table with existing Jira issues.

This script:
1. Reads all unique jira_key values from jira_issues table
2. Fetches current status and summary from Jira API for each issue
3. Inserts the data into jira_issue_details table

Usage:
    python migrate-jira_issue_details.py

Environment variables required:
    - CH_HOST: ClickHouse host
    - CH_PORT: ClickHouse port (default: 9000)
    - CH_DATABASE: ClickHouse database
    - CH_USER: ClickHouse username
    - CH_PASSWORD: ClickHouse password
    - JIRA_URL: Jira server URL
    - JIRA_USER: Jira username
    - JIRA_API_TOKEN: Jira API token
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Get the project root directory (parent of db/)
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Add parent directory to path to import app modules
sys.path.insert(0, str(PROJECT_ROOT))

from clickhouse_driver import Client
from dotenv import load_dotenv
from jira import JIRA

# Load .env from project root
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)
print(f"Loading .env from: {env_path}")

# ClickHouse configuration
CH_HOST = os.getenv("CH_HOST", "localhost")
CH_PORT = int(os.getenv("CH_PORT", "9000"))
CH_DATABASE = os.getenv("CH_DATABASE", "default")
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "")

# Jira configuration
JIRA_URL = os.getenv("JIRA_URL")
JIRA_USER = os.getenv("JIRA_USER") or os.getenv("JIRA_USERNAME")  # Support both names
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")


# Status mapping - maps Jira status names to status_id
STATUS_MAP = {
    "Open": 1,
    "To Do": 2,
    "In Progress": 3,
    "In Review": 4,
    "Testing": 5,
    "Done": 6,
    "Closed": 7,
    "Resolved": 8,
    "Reopened": 9,
    "Backlog": 10,
    "Selected for Development": 11,
    "Blocked": 12,
    "On Hold": 13,
    "Cancelled": 14,
    "Won't Do": 15,
}


def get_status_id(status_name: str, ch_client: Client) -> int:
    """
    Get status_id for a given status name.
    If status doesn't exist, insert it and return new id.
    """
    if status_name in STATUS_MAP:
        return STATUS_MAP[status_name]

    # Check if status exists in database
    result = ch_client.execute(
        "SELECT status_id FROM jira_statuses WHERE status_name = %(name)s",
        {"name": status_name},
    )

    if result:
        STATUS_MAP[status_name] = result[0][0]
        return result[0][0]

    # Insert new status
    max_id_result = ch_client.execute("SELECT max(status_id) FROM jira_statuses")
    new_id = (max_id_result[0][0] or 0) + 1

    # Determine category based on common patterns
    status_lower = status_name.lower()
    if any(
        x in status_lower for x in ["done", "closed", "resolved", "complete", "cancel"]
    ):
        category = "Done"
    elif any(
        x in status_lower for x in ["progress", "review", "test", "block", "hold"]
    ):
        category = "In Progress"
    else:
        category = "To Do"

    ch_client.execute(
        """
        INSERT INTO jira_statuses (status_id, status_name, status_category)
        VALUES (%(id)s, %(name)s, %(category)s)
        """,
        {"id": new_id, "name": status_name, "category": category},
    )

    STATUS_MAP[status_name] = new_id
    print(f"  Added new status: {status_name} (id={new_id}, category={category})")
    return new_id


def main():
    print("=" * 60)
    print("Jira Issue Details Migration Script")
    print("=" * 60)

    # Validate configuration
    if not all([JIRA_URL, JIRA_USER, JIRA_API_TOKEN]):
        print("ERROR: Missing Jira configuration. Please set environment variables:")
        print("  - JIRA_URL")
        print("  - JIRA_USER")
        print("  - JIRA_API_TOKEN")
        sys.exit(1)

    print(f"\nClickHouse: {CH_HOST}:{CH_PORT}/{CH_DATABASE}")
    print(f"Jira URL: {JIRA_URL}")

    # Connect to ClickHouse
    print("\nConnecting to ClickHouse...")
    ch_client = Client(
        host=CH_HOST,
        port=CH_PORT,
        database=CH_DATABASE,
        user=CH_USER,
        password=CH_PASSWORD,
    )

    # Connect to Jira using Bearer token authentication
    print("Connecting to Jira...")
    jira = JIRA(server=JIRA_URL, token_auth=JIRA_API_TOKEN)

    # Get unique jira_keys from jira_issues
    print("\nFetching unique jira_keys from jira_issues...")
    result = ch_client.execute("SELECT DISTINCT jira_key FROM jira_issues")
    jira_keys = [row[0] for row in result]
    print(f"Found {len(jira_keys)} unique Jira issues")

    if not jira_keys:
        print("No issues to migrate. Exiting.")
        return

    # Process each issue
    success_count = 0
    error_count = 0
    skipped_count = 0

    print("\nProcessing issues...")
    for i, jira_key in enumerate(jira_keys, 1):
        try:
            print(f"[{i}/{len(jira_keys)}] Processing {jira_key}...", end=" ")

            # Fetch issue from Jira
            issue = jira.issue(jira_key)
            status_name = str(issue.fields.status)
            summary = str(issue.fields.summary)

            # Get status_id
            status_id = get_status_id(status_name, ch_client)

            # Check if already exists to get original created_at
            existing = ch_client.execute(
                "SELECT created_at FROM jira_issue_details FINAL WHERE jira_key = %(key)s",
                {"key": jira_key},
            )

            if existing:
                # Update existing record - preserve original created_at
                original_created_at = existing[0][0]
                ch_client.execute(
                    """
                    INSERT INTO jira_issue_details (jira_key, status_id, summary, created_at, updated_at)
                    VALUES (%(key)s, %(status)s, %(summary)s, %(created_at)s, now())
                    """,
                    {
                        "key": jira_key,
                        "status": status_id,
                        "summary": summary,
                        "created_at": original_created_at,
                    },
                )
                print(f"Updated (status: {status_name})")
            else:
                # Insert new record
                ch_client.execute(
                    """
                    INSERT INTO jira_issue_details (jira_key, status_id, summary, created_at, updated_at)
                    VALUES (%(key)s, %(status)s, %(summary)s, now(), now())
                    """,
                    {"key": jira_key, "status": status_id, "summary": summary},
                )
                print(f"Inserted (status: {status_name})")

            success_count += 1

        except Exception as e:
            error_count += 1
            print(f"ERROR: {e}")

    # Print summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Total issues processed: {len(jira_keys)}")
    print(f"Successful: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Skipped: {skipped_count}")

    # Optimize table
    print("\nOptimizing jira_issue_details table...")
    ch_client.execute("OPTIMIZE TABLE jira_issue_details FINAL")
    print("Done!")


if __name__ == "__main__":
    main()
