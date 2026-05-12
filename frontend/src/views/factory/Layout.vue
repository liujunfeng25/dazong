<script setup>
import PortalLayout from '../../components/PortalLayout.vue'

const menu = [
  { label: '我的订单', path: '/factory/orders' },
  { label: '对配送商应收', path: '/factory/bills' },
  { label: '报告列表', path: '/factory/reports' },
  { label: '上传报告', path: '/factory/reports/upload' },
  { label: '消息中心', path: '/factory/notifications' },
]
</script>

<template>
  <PortalLayout
    title="大宗物资供应链管理系统"
    role-label="厂家端"
    color="#14532D"
    :menu="menu"
  />
</template>
