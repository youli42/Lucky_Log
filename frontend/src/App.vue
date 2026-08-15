<script setup>
import TopBar from './components/TopBar.vue'
import Sidebar from './components/Sidebar.vue'
</script>

<template>
  <div class="layout">
    <TopBar />
    <div class="body">
      <Sidebar />
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout { display: flex; flex-direction: column; height: 100vh; }
.body { flex: 1; display: flex; min-height: 0; }
.content { flex: 1; min-width: 0; overflow: auto; padding: 14px; }
</style>
