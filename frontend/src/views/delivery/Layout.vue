<script setup>
import PortalLayout from '../../components/PortalLayout.vue'

const menu = [
  { label: '待投标', path: '/delivery/tenders' },
  { label: '我的合约', path: '/delivery/contracts' },
  { label: '供货商管理', path: '/delivery/suppliers' },
  { label: '配送订单', path: '/delivery/orders' },
  { label: '售后工单', path: '/delivery/complaints' },
  { label: '车辆管理', path: '/delivery/vehicles' },
  { label: '设备管理', path: '/delivery/devices' },
  { label: '智能分单', path: '/delivery/smart-split' },
  { label: '智能排线', path: '/delivery/smart-routing' },
  { label: '应收账单', path: '/delivery/bills' },
  { label: '消息中心', path: '/delivery/notifications' },
]
</script>

<template>
  <PortalLayout
    title="大宗物资供应链管理系统"
    role-label="配送商端"
    color="#1E3A8A"
    :menu="menu"
  />
</template>
