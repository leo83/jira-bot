-- Active: 1758816025903@@clickhouse.aeroclub.int@8123@robotisation
drop table if exists jira_issues;
CREATE TABLE jira_issues(  
    message_ref UUID NOT NULL  ,
    jira_key VARCHAR(255) NOT NULL ,
    created_at TIMESTAMP NOT NULL DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (message_ref)
;

OPTIMIZE TABLE jira_issues FINAL DEDUPLICATE BY message_ref, jira_key;
