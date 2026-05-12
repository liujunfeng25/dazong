<script setup>
import { onBeforeUnmount, watch } from 'vue'
import { useNotificationStore } from './stores/notifications'
import { useUserStore } from './stores/user'

const userStore = useUserStore()
const notificationStore = useNotificationStore()

watch(
  () => userStore.token,
  (token) => {
    if (token) notificationStore.connect()
    else notificationStore.disconnect()
  },
  { immediate: true },
)

onBeforeUnmount(() => notificationStore.disconnect())
</script>

<template>
  <router-view />
</template>
