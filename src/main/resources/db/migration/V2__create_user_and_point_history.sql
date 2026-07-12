CREATE TABLE user
(
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    balance    BIGINT   NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE point_history
(
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT      NOT NULL,
    amount     BIGINT      NOT NULL,
    type       VARCHAR(10) NOT NULL,
    created_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_point_history_user FOREIGN KEY (user_id) REFERENCES user (id),
    CONSTRAINT chk_point_history_type CHECK (type IN ('CHARGE', 'USE'))
);

INSERT INTO user (balance)
VALUES (0);
