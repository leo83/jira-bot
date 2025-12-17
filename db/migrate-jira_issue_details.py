#!/usr/bin/env python3
"""
Migration script to populate jira_issue_details table with existing Jira issues.

This script:
1. Reads all unique jira_key values from jira_issues table
2. Fetches current status, summary, and task type from Jira API for each issue
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
    - JIRA_USERNAME: Jira username
    - JIRA_API_TOKEN: Jira API token
"""

import os
import sys
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


def main():
    print("=" * 60)
    print("Jira Issue Details Migration Script")
    print("=" * 60)

    # Validate configuration
    if not all([JIRA_URL, JIRA_API_TOKEN]):
        print("ERROR: Missing Jira configuration. Please set environment variables:")
        print("  - JIRA_URL")
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

    print("\nProcessing issues...")
    for i, jira_key in enumerate(jira_keys, 1):
        try:
            print(f"[{i}/{len(jira_keys)}] Processing {jira_key}...", end=" ")

            # Fetch issue from Jira
            issue = jira.issue(jira_key)
            status_name = str(issue.fields.status)
            summary = str(issue.fields.summary)
            task_type = str(issue.fields.issuetype)

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
                    INSERT INTO jira_issue_details (jira_key, summary, created_at, updated_at, status_name, task_type)
                    VALUES (%(key)s, %(summary)s, %(created_at)s, now(), %(status_name)s, %(task_type)s)
                    """,
                    {
                        "key": jira_key,
                        "summary": summary,
                        "created_at": original_created_at,
                        "status_name": status_name,
                        "task_type": task_type,
                    },
                )
                print(f"Updated (status: {status_name}, type: {task_type})")
            else:
                # Insert new record
                ch_client.execute(
                    """
                    INSERT INTO jira_issue_details (jira_key, summary, created_at, updated_at, status_name, task_type)
                    VALUES (%(key)s, %(summary)s, now(), now(), %(status_name)s, %(task_type)s)
                    """,
                    {
                        "key": jira_key,
                        "summary": summary,
                        "status_name": status_name,
                        "task_type": task_type,
                    },
                )
                print(f"Inserted (status: {status_name}, type: {task_type})")

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

    # Optimize table
    print("\nOptimizing jira_issue_details table...")
    ch_client.execute("OPTIMIZE TABLE jira_issue_details FINAL")
    print("Done!")


if __name__ == "__main__":
    main()
