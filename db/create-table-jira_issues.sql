drop table if exists jira_issues;
CREATE TABLE jira_issues(  
    message_ref uuid NOT NULL  ,
    jira_key VARCHAR(255) not null,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE jira_issues IS 'Table for storing Jira issues linked to messages';
COMMENT ON COLUMN jira_issues.message_ref IS 'Message reference';
COMMENT ON COLUMN jira_issues.jira_key IS 'Jira key';
COMMENT ON COLUMN jira_issues.created_at IS 'Created at';
