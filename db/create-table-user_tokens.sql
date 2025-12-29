-- Active: 1758816025903@@clickhouse.aeroclub.int@8123@robotisation
-- Table for storing encrypted Jira tokens for Telegram users

DROP TABLE IF EXISTS user_tokens;

CREATE TABLE user_tokens (
    telegram_id Int64 NOT NULL,
    jira_token_encrypted String NOT NULL,
    telegram_username Nullable(String),
    created_at DateTime NOT NULL DEFAULT now(),
    updated_at DateTime NOT NULL DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (telegram_id);

-- Note: ReplacingMergeTree ensures only the latest token per telegram_id is kept
-- based on the updated_at column. This allows users to update their tokens.
-- jira_token_encrypted contains Fernet-encrypted token data.




