# 顺义正式服商品字段映射

## 核心业务映射

- `goods_name` -> `products.name`
- `cate_name` -> `categories(level=1).name`
- `scate_name` -> `categories(level=2, parent=level1).name`
- `unit` -> `products.unit`
- `sale_price`(优先) / `quotation_price` -> `products.reference_price`
- `spec` -> `products.spec`
- `place` -> `products.origin`
- `status=1` -> `products.status=active`，其他 -> `disabled`

## 扩展字段映射（新增结构化列）

- `goods_sn` -> `products.goods_sn`
- `brand` -> `products.brand`
- `expire_date` -> `products.expire_date`
- `manufacturer` -> `products.manufacturer`
- `model` -> `products.model`
- `source` -> `products.source`
- `attr` -> `products.attr`
- `level` -> `products.level`
- `limit_price` -> `products.limit_price`
- `discount_rate` -> `products.discount_rate`
- `float_rate_max` -> `products.float_rate_max`
- `float_rate_min` -> `products.float_rate_min`
- `supp_id` -> `products.supplier_id`
- `supp_name` -> `products.supplier_name`
- `goods_channel` -> `products.goods_channel`
- `finance_code` -> `products.finance_code`
- `finance_rate` -> `products.finance_rate`
- `number` -> `products.number`
- `weight` -> `products.weight`
- `remark` -> `products.remark`
- `logo` -> `products.logo`
- `slogo` -> `products.slogo`
- `url` -> `products.external_url`

## 默认与兜底规则

- `reference_price`：`sale_price` 为有效数值时优先，否则使用 `quotation_price`，再否则为 `0`
- `unit`：为空时默认 `件`
- `spec/origin`：为空时写空字符串
- 分类缺失时自动创建（先一级再二级）
- 幂等键优先 `goods_sn`，缺失时回退 `name + spec + unit + supplier_id`
