-- 少收草稿字段 + 收货后生成的退货单（已有库手工执行一次）

ALTER TABLE order_receiving_lines
  ADD COLUMN shortage_reason_code VARCHAR(16) NULL COMMENT 'lack|quality|other',
  ADD COLUMN shortage_reason_detail VARCHAR(512) NULL,
  ADD COLUMN shortage_ordered_kg DECIMAL(14,4) NULL,
  ADD COLUMN shortage_delta_kg DECIMAL(14,4) NULL;

CREATE TABLE IF NOT EXISTS order_returns (
    id INT NOT NULL AUTO_INCREMENT,
    order_id INT NOT NULL,
    return_no VARCHAR(64) NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'receive_shortage',
    client_id INT NOT NULL,
    receive_idempotency_key VARCHAR(128) NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'confirmed',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_returns_return_no (return_no),
    UNIQUE KEY uq_order_returns_order_source (order_id, source),
    CONSTRAINT fk_order_returns_order FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
    CONSTRAINT fk_order_returns_client FOREIGN KEY (client_id) REFERENCES users (id),
    KEY ix_order_returns_order_id (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_return_lines (
    id INT NOT NULL AUTO_INCREMENT,
    order_return_id INT NOT NULL,
    line_index INT NOT NULL,
    product_id INT NULL,
    product_name VARCHAR(255) NOT NULL DEFAULT '',
    ordered_kg DECIMAL(14,4) NOT NULL,
    received_kg DECIMAL(14,4) NOT NULL,
    delta_kg DECIMAL(14,4) NOT NULL,
    reason_code VARCHAR(16) NOT NULL,
    reason_detail VARCHAR(2000) NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_order_return_lines_ret FOREIGN KEY (order_return_id) REFERENCES order_returns (id) ON DELETE CASCADE,
    KEY ix_order_return_lines_ret (order_return_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
