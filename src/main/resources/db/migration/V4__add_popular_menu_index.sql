CREATE INDEX idx_orders_created_at_menu_id
    ON orders (created_at, menu_id);
