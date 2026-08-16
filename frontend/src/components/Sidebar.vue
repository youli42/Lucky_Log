<script setup>
import { computed } from 'vue'
import { store } from '../store'

const MODULES = [
  { name: 'system', label: 'System' },
  { name: 'cron', label: 'Cron' },
  { name: 'ddns', label: 'DDNS' },
  { name: 'ssl', label: 'SSL' },
  { name: 'webterminal', label: 'WebTerminal' },
  { name: 'rclone', label: 'Rclone' },
  { name: 'filebrowser', label: 'FileBrowser' },
  { name: 'wol', label: 'WOL' },
  { name: 'ftpserver', label: 'FTP' },
  { name: 'webdav', label: 'WebDAV' },
  { name: 'dlnaservice', label: 'DLNA' },
  { name: 'frp', label: 'FRP' },
  { name: 'cloudflared', label: 'Cloudflared' },
  { name: 'ipdb', label: 'IPDB' },
  { name: 'storagemanagement', label: '存储管理' },
  { name: 'thirdPartyAuthManager', label: '三方认证' },
  { name: 'coraza', label: 'Coraza' },
  { name: 'portforward', label: '端口转发' },
  { name: 'iconlib', label: '图标库' },
  { name: 'stun', label: 'STUN' },
]
// 注：docker / smb / webservice 有专用面板（Docker、SMB、Web 访问分析），在顶部固定区，
//     故不出现在本通用模块列表（避免重复）。
const cfg = computed(() => {
  const inst = store.instances.find((i) => i.name === store.instance)
  const enabled = new Set(inst && inst.modules ? inst.modules : [])
  return MODULES.filter((m) => enabled.has(m.name))
})
</script>

<template>
  <nav class="sidebar">
    <router-link to="/overview" class="item" active-class="active">总览大屏</router-link>
    <router-link to="/access" class="item" active-class="active">Web 访问分析</router-link>
    <router-link to="/docker" class="item" active-class="active">Docker</router-link>
    <router-link to="/smb" class="item" active-class="active">SMB</router-link>
    <div class="divider"></div>
    <router-link
      v-for="m in cfg" :key="m.name"
      :to="m.to || `/module/${m.name}`" class="item" active-class="active"
    >{{ m.label }}</router-link>
    <div class="divider"></div>
    <router-link to="/settings" class="item" active-class="active">设置</router-link>
  </nav>
</template>

<style scoped>
.sidebar {
  width: 170px; min-width: 170px; background: var(--panel); border-right: 1px solid var(--border);
  padding: 10px 8px; overflow-y: auto;
}
.item {
  display: block; padding: 8px 10px; margin: 2px 0; border-radius: 6px; color: var(--text); font-size: 13px;
}
.item:hover { background: var(--panel2); }
.item.active { background: var(--accent); color: #fff; }
.divider { height: 1px; background: var(--border); margin: 8px 4px; }
</style>
