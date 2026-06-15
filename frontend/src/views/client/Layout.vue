<script setup>
import { useIsMobile } from '../../composables/useIsMobile'
import PortalLayout from '../../components/PortalLayout.vue'
import MobileClientLayout from './MobileClientLayout.vue'

const { isMobile } = useIsMobile()

const menu = [
  { label: '采购看板', path: '/client/dashboard' },
  { label: '我的合约', path: '/client/contracts' },
  { label: '发起招标', path: '/client/contracts/new' },
  { label: '招标进度', path: '/client/tenders' },
  { label: '新建订单', path: '/client/orders/new' },
  { label: '我的订单', path: '/client/orders' },
  { label: '我的账单', path: '/client/bills' },
  { label: '消息中心', path: '/client/notifications' },
]
</script>

<template>
  <MobileClientLayout v-if="isMobile" />
  <PortalLayout
    v-else
    title="大宗物资供应链管理系统"
    role-label="客户端"
    color="#264A9E"
    :menu="menu"
  />
</template>
