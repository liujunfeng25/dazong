<script setup>
import PortalLayout from '../../components/PortalLayout.vue'
const menu = [
  { label: '监管驾驶舱', path: '/monitor/dashboard' },
  { label: '天枢大屏', path: '/monitor/tianshu' },
  { label: '路线规划汇报', path: '/monitor/route-planning' },
  { label: '订单溯源', path: '/monitor/orders' },
  { label: '物流监控', path: '/monitor/logistics' },
  { label: '预警中心', path: '/monitor/alerts' },
  { label: '统计报表', path: '/monitor/reports' },
  { label: '消息中心', path: '/monitor/notifications' },
]
</script>

<template>
  <PortalLayout
    title="大宗物资供应链管理系统"
    role-label="监管端"
    color="#111827"
    :menu="menu"
  />
</template>
