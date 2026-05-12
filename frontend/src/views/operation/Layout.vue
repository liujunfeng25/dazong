<script setup>
import PortalLayout from '../../components/PortalLayout.vue'

const menu = [
  { label: '运营看板', path: '/operation/dashboard' },
  { label: '分类管理', path: '/operation/categories' },
  { label: '商品管理', path: '/operation/products' },
  { label: '合约查看', path: '/operation/contracts' },
  { label: '账号管理', path: '/operation/accounts' },
  { label: '客户食堂', path: '/operation/client-canteens' },
  { label: '订单监控', path: '/operation/orders' },
  { label: '账期配置', path: '/operation/billing-cycles' },
  { label: '工单处理', path: '/operation/tickets' },
  { label: '消息中心', path: '/operation/notifications' },
]
</script>

<template>
  <PortalLayout
    title="大宗物资供应链管理系统"
    role-label="运营端"
    color="#312E81"
    :menu="menu"
  />
</template>
