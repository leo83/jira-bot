-- Table for storing Jira issue details

DROP TABLE IF EXISTS jira_issue_details;

CREATE TABLE jira_issue_details (
    jira_key String NOT NULL,
    summary String NOT NULL,
    created_at DateTime NOT NULL DEFAULT now(),
    updated_at DateTime NOT NULL DEFAULT now(),
    status_name String NOT NULL,
    task_type String NOT NULL
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (jira_key);


