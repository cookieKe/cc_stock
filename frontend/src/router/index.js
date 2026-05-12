import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
  { path: '/stock/:code', name: 'StockDetail', component: () => import('../views/StockDetail.vue') },
  { path: '/scanner', name: 'Scanner', component: () => import('../views/Scanner.vue') },
  { path: '/watchlist', name: 'Watchlist', component: () => import('../views/Watchlist.vue') },
  { path: '/strategies', name: 'Strategies', component: () => import('../views/Strategies.vue') },
  { path: '/data', name: 'DataSummary', component: () => import('../views/DataSummary.vue') },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
