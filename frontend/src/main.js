import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import './style.css'
import './charts'
import App from './App.vue'
import Overview from './views/Overview.vue'
import Access from './views/Access.vue'
import ModuleLogs from './views/ModuleLogs.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', component: Overview },
    { path: '/access', component: Access },
    { path: '/module/:module', component: ModuleLogs },
  ],
})

createApp(App).use(router).mount('#app')
