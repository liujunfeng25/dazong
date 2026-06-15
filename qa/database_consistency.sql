-- Dazong QA-only consistency audit. Run against the isolated dazong_qa database.

SELECT 'orders_empty_items' AS check_name, COUNT(*) AS issue_count
FROM orders
WHERE JSON_LENGTH(items_json) = 0;

SELECT 'orders_non_positive_amount' AS check_name, COUNT(*) AS issue_count
FROM orders
WHERE total_amount <= 0;

SELECT 'orders_non_positive_item_quantity' AS check_name, COUNT(*) AS issue_count
FROM orders AS o
JOIN JSON_TABLE(
    o.items_json,
    '$[*]' COLUMNS (
        product_id INT PATH '$.product_id',
        quantity DECIMAL(18,3) PATH '$.quantity'
    )
) AS item
WHERE item.quantity <= 0;

SELECT 'orders_amount_mismatch' AS check_name, COUNT(*) AS issue_count
FROM (
    SELECT
        o.id,
        o.total_amount,
        ROUND(COALESCE(SUM(item.quantity * item.unit_price), 0), 2) AS computed_amount
    FROM orders AS o
    LEFT JOIN JSON_TABLE(
        o.items_json,
        '$[*]' COLUMNS (
            quantity DECIMAL(18,3) PATH '$.quantity',
            unit_price DECIMAL(18,4) PATH '$.unit_price'
        )
    ) AS item ON TRUE
    GROUP BY o.id, o.total_amount
) AS amount_check
WHERE ABS(total_amount - computed_amount) > 0.01;

SELECT 'products_blank_name' AS check_name, COUNT(*) AS issue_count
FROM products
WHERE is_deleted = 0 AND TRIM(name) = '';

SELECT 'products_non_positive_price' AS check_name, COUNT(*) AS issue_count
FROM products
WHERE is_deleted = 0 AND reference_price <= 0;

SELECT 'products_non_positive_dimensions' AS check_name, COUNT(*) AS issue_count
FROM products
WHERE is_deleted = 0
  AND (
      length_cm <= 0
      OR width_cm <= 0
      OR height_cm <= 0
      OR unit_weight_kg <= 0
      OR volume_adjust_factor <= 0
  );

SELECT 'products_standard_unit_mismatch' AS check_name, COUNT(*) AS issue_count
FROM products
WHERE is_deleted = 0
  AND (
      (standard_type = 'standard' AND unit IN ('kg', '斤'))
      OR
      (standard_type = 'non_standard' AND unit NOT IN ('kg', '斤'))
  );

SELECT 'allocations_non_positive_quantity' AS check_name, COUNT(*) AS issue_count
FROM order_item_allocations
WHERE quantity <= 0;

SELECT 'allocations_non_positive_price' AS check_name, COUNT(*) AS issue_count
FROM order_item_allocations
WHERE unit_price <= 0;

SELECT 'allocation_quantity_exceeds_order' AS check_name, COUNT(*) AS issue_count
FROM (
    SELECT
        allocation.order_id,
        allocation.product_id,
        SUM(allocation.quantity) AS allocated_quantity,
        MAX(order_item.order_quantity) AS order_quantity
    FROM order_item_allocations AS allocation
    JOIN orders AS o ON o.id = allocation.order_id
    JOIN JSON_TABLE(
        o.items_json,
        '$[*]' COLUMNS (
            product_id INT PATH '$.product_id',
            order_quantity DECIMAL(18,3) PATH '$.quantity'
        )
    ) AS order_item ON order_item.product_id = allocation.product_id
    GROUP BY allocation.order_id, allocation.product_id
) AS allocation_check
WHERE allocated_quantity > order_quantity + 0.001;

SELECT 'reviews_rating_out_of_range' AS check_name, COUNT(*) AS issue_count
FROM order_reviews
WHERE rating < 1 OR rating > 5;

SELECT 'reviews_before_receipt_confirmation' AS check_name, COUNT(*) AS issue_count
FROM order_reviews AS review
JOIN orders AS o ON o.id = review.order_id
WHERE o.status NOT IN ('收货确认', '已结算');

SELECT 'bills_non_positive_amount' AS check_name, COUNT(*) AS issue_count
FROM bills
WHERE amount <= 0;

SELECT 'statements_negative_amounts' AS check_name, COUNT(*) AS issue_count
FROM billing_statements
WHERE amount < 0 OR confirmed_amount < 0 OR settled_amount < 0;

SELECT 'statements_over_settled' AS check_name, COUNT(*) AS issue_count
FROM billing_statements
WHERE confirmed_amount > amount OR settled_amount > amount;

SELECT 'orphan_order_client' AS check_name, COUNT(*) AS issue_count
FROM orders AS o
LEFT JOIN users AS u ON u.id = o.client_id
WHERE u.id IS NULL OR u.role <> 'client';

SELECT 'orphan_order_delivery' AS check_name, COUNT(*) AS issue_count
FROM orders AS o
LEFT JOIN users AS u ON u.id = o.delivery_id
WHERE u.id IS NULL OR u.role <> 'delivery';

SELECT 'order_canteen_owner_mismatch' AS check_name, COUNT(*) AS issue_count
FROM orders AS o
JOIN client_canteens AS c ON c.id = o.canteen_id
WHERE c.school_client_id <> o.client_id;

SELECT 'allocation_supplier_owner_mismatch' AS check_name, COUNT(*) AS issue_count
FROM order_item_allocations AS allocation
JOIN users AS supplier ON supplier.id = allocation.supplier_id
WHERE supplier.role NOT IN ('supplier', 'factory')
   OR (
       supplier.role = 'supplier'
       AND supplier.supplier_delivery_id <> allocation.delivery_id
   );

SELECT 'dispatch_trip_count_mismatch' AS check_name, COUNT(*) AS issue_count
FROM delivery_dispatch_trips AS trip
LEFT JOIN (
    SELECT
        trip_id,
        COUNT(*) AS item_count,
        COUNT(DISTINCT order_id) AS order_count,
        SUM(status = '已装车') AS loaded_count
    FROM delivery_dispatch_items
    GROUP BY trip_id
) AS item_counts ON item_counts.trip_id = trip.id
WHERE trip.total_allocations <> COALESCE(item_counts.item_count, 0)
   OR trip.total_orders <> COALESCE(item_counts.order_count, 0)
   OR trip.ready_count + trip.blocked_count + trip.not_loaded_count <> trip.total_allocations;

SELECT 'status_log_missing_for_versioned_order' AS check_name, COUNT(*) AS issue_count
FROM orders AS o
LEFT JOIN (
    SELECT order_id, COUNT(*) AS log_count
    FROM order_status_logs
    GROUP BY order_id
) AS logs ON logs.order_id = o.id
WHERE o.version > 1 AND COALESCE(logs.log_count, 0) = 0;

SELECT 'active_account_missing_required_location' AS check_name, COUNT(*) AS issue_count
FROM users
WHERE status = 'active'
  AND role IN ('client', 'delivery', 'factory')
  AND (TRIM(address) = '' OR lng IS NULL OR lat IS NULL);

SELECT 'active_canteen_missing_location' AS check_name, COUNT(*) AS issue_count
FROM client_canteens
WHERE status = 'active'
  AND (TRIM(address) = '' OR lng IS NULL OR lat IS NULL);

SELECT 'duplicate_active_category_name' AS check_name, COUNT(*) AS issue_count
FROM (
    SELECT level, COALESCE(parent_id, 0) AS parent_key, LOWER(TRIM(name)) AS normalized_name
    FROM categories
    WHERE is_deleted = 0
    GROUP BY level, COALESCE(parent_id, 0), LOWER(TRIM(name))
    HAVING COUNT(*) > 1
) AS duplicate_categories;

-- Evidence rows for the most severe consistency failures.
SELECT
    o.id,
    o.order_no,
    o.status,
    o.total_amount,
    o.total_weight_kg,
    o.items_json
FROM orders AS o
WHERE JSON_LENGTH(o.items_json) = 0
   OR o.total_amount < 0
   OR EXISTS (
       SELECT 1
       FROM JSON_TABLE(
           o.items_json,
           '$[*]' COLUMNS (quantity DECIMAL(18,3) PATH '$.quantity')
       ) AS item
       WHERE item.quantity <= 0
   )
ORDER BY o.id DESC
LIMIT 100;
