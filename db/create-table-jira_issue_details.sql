-- Active: 1758816025903@@clickhouse.aeroclub.int@8123@robotisation
-- Table for storing Jira issue details

DROP TABLE IF EXISTS jira_issue_details;

CREATE TABLE jira_issue_details (
    jira_key String NOT NULL,
    status_id UInt8 NOT NULL,  -- References jira_statuses(status_id)
    summary String NOT NULL,
    created_at DateTime NOT NULL DEFAULT now(),
    updated_at DateTime NOT NULL DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (jira_key);

-- Note: ClickHouse doesn't support foreign keys, but status_id references jira_statuses(status_id)
-- The ReplacingMergeTree engine ensures that only the latest row per jira_key is kept
-- based on the updated_at column, which is useful for tracking status changes.


