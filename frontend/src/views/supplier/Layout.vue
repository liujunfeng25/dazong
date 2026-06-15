<script setup>
import PortalLayout from '../../components/PortalLayout.vue'

const menu = [
  { label: '配送分包订单', path: '/supplier/orders' },
  { label: '商品报价', path: '/supplier/quotes' },
  { label: '周期报告', path: '/supplier/periodic-reports' },
  { label: '对配送商应收', path: '/supplier/bills' },
  { label: '消息中心', path: '/supplier/notifications' },
]
</script>

<template>
  <PortalLayout
    title="大宗物资供应链管理系统"
    role-label="供货商端"
    color="#9A3412"
    :menu="menu"
  />
</template>
