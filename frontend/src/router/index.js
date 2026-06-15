import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

import Login from '../views/Login.vue'
import ClientLayout from '../views/client/Layout.vue'
import SupplierLayout from '../views/supplier/Layout.vue'
import DeliveryLayout from '../views/delivery/Layout.vue'
import FactoryLayout from '../views/factory/Layout.vue'
import OperationLayout from '../views/operation/Layout.vue'
import MonitorLayout from '../views/monitor/Layout.vue'

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: Login, meta: { public: true } },
  { path: '/docs', component: () => import('../views/ApiDocs.vue'), meta: { public: true } },
  {
    path: '/operation',
    component: OperationLayout,
    meta: { role: 'operation' },
    children: [
      { path: '', redirect: '/operation/dashboard' },
      { path: 'dashboard', component: () => import('../views/operation/Dashboard.vue') },
      { path: 'categories', component: () => import('../views/operation/Categories.vue') },
      { path: 'products', component: () => import('../views/operation/Products.vue') },
      { path: 'smart-scale-recognition', component: () => import('../views/operation/SmartScaleRecognition.vue') },
      { path: 'periodic-reports', component: () => import('../views/operation/PeriodicReports.vue') },
      { path: 'accounts', component: () => import('../views/operation/Accounts.vue') },
      { path: 'client-canteens', component: () => import('../views/operation/ClientCanteens.vue') },
      { path: 'contracts', component: () => import('../views/operation/Contracts.vue') },
      { path: 'orders', component: () => import('../views/operation/Orders.vue') },
      { path: 'orders/:id', component: () => import('../views/operation/OrderDetail.vue') },
      { path: 'receiving-differences', component: () => import('../views/common/ReceivingDifferences.vue'), props: { role: 'operation' } },
      { path: 'billing-overview', component: () => import('../views/operation/BillingOverview.vue') },
      { path: 'billing-cycles', component: () => import('../views/operation/BillingCycles.vue') },
      { path: 'tickets', component: () => import('../views/operation/Tickets.vue') },
      { path: 'notifications', component: () => import('../views/common/Notifications.vue') },
    ],
  },
  {
    path: '/client/select-canteen',
    component: () => import('../views/client/ClientCanteenGate.vue'),
    meta: { role: 'client' },
    children: [
      {
        path: '',
        component: () => import('../views/client/SelectCanteen.vue'),
        meta: { role: 'client' },
      },
    ],
  },
  {
    path: '/client',
    component: ClientLayout,
    meta: { role: 'client' },
    children: [
      { path: '', redirect: '/client/dashboard' },
      {
        path: 'dashboard',
        component: () => import('../views/client/Dashboard.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'contracts',
        component: () => import('../views/client/Contracts.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'contracts/new',
        component: () => import('../views/client/ContractNew.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'contracts/:id/bids',
        component: () => import('../views/client/ContractBids.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'tenders',
        component: () => import('../views/client/Tenders.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'orders/new',
        component: () => import('../views/client/OrderNew.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'orders',
        component: () => import('../views/client/Orders.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'orders/:id',
        component: () => import('../views/client/OrderDetail.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'receive/:id',
        component: () => import('../views/client/Receive.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'bills',
        component: () => import('../views/client/Bills.vue'),
        meta: { requiresClientCanteen: true },
      },
      {
        path: 'notifications',
        component: () => import('../views/common/Notifications.vue'),
        meta: { requiresClientCanteen: true },
      },
    ],
  },
  {
    path: '/delivery',
    component: DeliveryLayout,
    meta: { role: 'delivery' },
    children: [
      { path: '', redirect: '/delivery/workbench' },
      { path: 'workbench', component: () => import('../views/delivery/Workbench.vue') },
      { path: 'tenders', component: () => import('../views/delivery/Tenders.vue') },
      { path: 'tenders/:id', component: () => import('../views/delivery/TenderDetail.vue') },
      { path: 'contracts', component: () => import('../views/delivery/Contracts.vue') },
      { path: 'suppliers', component: () => import('../views/delivery/Suppliers.vue') },
      { path: 'orders', component: () => import('../views/delivery/Orders.vue') },
      { path: 'orders/:id', component: () => import('../views/delivery/OrderDetail.vue') },
      { path: 'receiving-differences', component: () => import('../views/common/ReceivingDifferences.vue'), props: { role: 'delivery' } },
      { path: 'complaints', component: () => import('../views/delivery/Complaints.vue') },
      { path: 'vehicles', component: () => import('../views/delivery/Vehicles.vue') },
      { path: 'devices', component: () => import('../views/delivery/Devices.vue') },
      { path: 'warehouses', component: () => import('../views/delivery/Warehouses.vue') },
      { path: 'smart-split', component: () => import('../views/delivery/SmartSplit.vue') },
      { path: 'smart-routing', component: () => import('../views/delivery/SmartRouting.vue') },
      { path: 'dispatch-trips', component: () => import('../views/delivery/DispatchTrips.vue') },
      { path: 'route-plan', redirect: '/delivery/smart-routing' },
      { path: 'bills', component: () => import('../views/delivery/Bills.vue') },
      { path: 'notifications', component: () => import('../views/common/Notifications.vue') },
    ],
  },
  {
    path: '/supplier',
    component: SupplierLayout,
    meta: { role: 'supplier' },
    children: [
      { path: '', redirect: '/supplier/orders' },
      { path: 'orders', component: () => import('../views/supplier/Orders.vue') },
      { path: 'orders/:id', component: () => import('../views/supplier/OrderDetail.vue') },
      { path: 'quotes', component: () => import('../views/supplier/ProductQuotes.vue') },
      { path: 'periodic-reports', component: () => import('../views/common/PeriodicReportsProvider.vue') },
      { path: 'bills', component: () => import('../views/supplier/Bills.vue') },
      { path: 'notifications', component: () => import('../views/common/Notifications.vue') },
    ],
  },
  {
    path: '/factory',
    component: FactoryLayout,
    meta: { role: 'factory' },
    children: [
      { path: '', redirect: '/factory/orders' },
      { path: 'orders', component: () => import('../views/factory/Orders.vue') },
      { path: 'orders/:id', component: () => import('../views/factory/OrderDetail.vue') },
      { path: 'bills', component: () => import('../views/factory/Bills.vue') },
      { path: 'reports', component: () => import('../views/factory/Reports.vue') },
      { path: 'reports/upload', component: () => import('../views/factory/ReportUpload.vue') },
      { path: 'periodic-reports', component: () => import('../views/common/PeriodicReportsProvider.vue') },
      { path: 'notifications', component: () => import('../views/common/Notifications.vue') },
    ],
  },
  {
    path: '/monitor',
    component: MonitorLayout,
    meta: { role: 'monitor' },
    children: [
      { path: '', redirect: '/monitor/dashboard' },
      { path: 'dashboard', component: () => import('../views/monitor/Dashboard.vue') },
      { path: 'tianshu', component: () => import('../views/monitor/TianshuBigScreen.vue') },
      { path: 'price-cockpit', component: () => import('../views/monitor/PriceCockpit.vue') },
      { path: 'route-planning', component: () => import('../views/monitor/RoutePlanningShowcase.vue') },
      { path: 'orders', component: () => import('../views/monitor/Orders.vue') },
      { path: 'logistics', component: () => import('../views/monitor/Logistics.vue') },
      { path: 'alerts', component: () => import('../views/monitor/Alerts.vue') },
      { path: 'reports', component: () => import('../views/monitor/Reports.vue') },
      { path: 'home', component: () => import('../views/monitor/Home.vue') },
      { path: 'notifications', component: () => import('../views/common/Notifications.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const userStore = useUserStore()
  if (to.meta.public) {
    if (to.path === '/login' && userStore.token && userStore.role) {
      if (userStore.role === 'client') {
        try {
          await userStore.fetchMe()
        } catch {
          userStore.logout()
          return '/login'
        }
        if (userStore.userInfo?.canteen_id == null || userStore.userInfo?.canteen_id === undefined) {
          return { path: '/client/select-canteen', query: { redirect: '/client/dashboard' } }
        }
      }
      return `/${userStore.role}`
    }
    return true
  }
  if (!userStore.token) return '/login'

  if (!userStore.userInfo) {
    try {
      await userStore.fetchMe()
    } catch {
      userStore.logout()
      return '/login'
    }
  }
  if (to.meta.role && to.meta.role !== userStore.role) {
    return `/${userStore.role}`
  }
  if (userStore.role === 'client' && to.path === '/client/select-canteen') {
    const cid = userStore.userInfo?.canteen_id
    const allowRepick = to.query.repick === '1' || to.query.repick === 'true'
    if (cid != null && cid !== undefined && !allowRepick) {
      const r = typeof to.query.redirect === 'string' && to.query.redirect.startsWith('/client') ? to.query.redirect : '/client/dashboard'
      return r
    }
  }
  if (
    userStore.role === 'client' &&
    to.meta.requiresClientCanteen &&
    (userStore.userInfo?.canteen_id == null || userStore.userInfo?.canteen_id === undefined)
  ) {
    return { path: '/client/select-canteen', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
