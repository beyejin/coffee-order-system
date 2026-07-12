CREATE TABLE orders
(
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT   NOT NULL,
    menu_id    BIGINT   NOT NULL,
    price      BIGINT   NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES user (id),
    CONSTRAINT fk_orders_menu FOREIGN KEY (menu_id) REFERENCES menu (id)
);
