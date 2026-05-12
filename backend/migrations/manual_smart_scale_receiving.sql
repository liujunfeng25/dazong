-- 已有库需手工执行一次（create_all 不会 ALTER 旧表加列）
-- MySQL 8+

CREATE TABLE IF NOT EXISTS order_receiving_lines (
    id INT NOT NULL AUTO_INCREMENT,
    order_id INT NOT NULL,
    line_index INT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    draft_kg DECIMAL(14, 4) NULL,
    confirmed_kg DECIMAL(14, 4) NULL,
    confirmed_at DATETIME NULL,
    confirmed_by_user_id INT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_order_receiving_lines_order FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
    CONSTRAINT fk_order_receiving_lines_user FOREIGN KEY (confirmed_by_user_id) REFERENCES users (id),
    CONSTRAINT uq_order_receiving_line_order_line UNIQUE (order_id, line_index),
    KEY ix_order_receiving_lines_order_id (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 若列已存在会报错，可忽略或先检查 information_schema
ALTER TABLE orders ADD COLUMN receive_signatures_json JSON NULL COMMENT '智能秤双签';
