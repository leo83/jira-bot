-- Active: 1758816025903@@clickhouse.aeroclub.int@8123@robotisation
-- Dictionary table for Jira issue statuses

DROP TABLE IF EXISTS jira_statuses;

CREATE TABLE jira_statuses (
    status_id UInt8 NOT NULL,
    status_name String NOT NULL,
    status_category String NOT NULL,  -- 'To Do', 'In Progress', 'Done'
    created_at DateTime NOT NULL DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (status_id);

-- Insert common Jira statuses
INSERT INTO jira_statuses (status_id, status_name, status_category) VALUES
    (1, 'Open', 'To Do'),
    (2, 'To Do', 'To Do'),
    (3, 'In Progress', 'In Progress'),
    (4, 'In Review', 'In Progress'),
    (5, 'Testing', 'In Progress'),
    (6, 'Done', 'Done'),
    (7, 'Closed', 'Done'),
    (8, 'Resolved', 'Done'),
    (9, 'Reopened', 'To Do'),
    (10, 'Backlog', 'To Do'),
    (11, 'Selected for Development', 'To Do'),
    (12, 'Blocked', 'In Progress'),
    (13, 'On Hold', 'In Progress'),
    (14, 'Cancelled', 'Done'),
    (15, 'Won''t Do', 'Done');


