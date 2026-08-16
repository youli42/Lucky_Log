// 模块元数据唯一来源（后端 app/config.py ALL_MODULES 为镜像清单）。
// 新增采集模块时：后端 SINGLE_SOURCES + ALL_MODULES 各加一行，这里补一行标签即可。

export const MODULE_LABELS = {
  system: 'System',
  webservice: 'Web (WebService)',
  docker: 'Docker',
  cron: 'Cron',
  ddns: 'DDNS',
  ssl: 'SSL',
  webterminal: 'WebTerminal',
  rclone: 'Rclone',
  filebrowser: 'FileBrowser',
  wol: 'WOL',
  ftpserver: 'FTP',
  webdav: 'WebDAV',
  dlnaservice: 'DLNA',
  frp: 'FRP',
  cloudflared: 'Cloudflared',
  ipdb: 'IPDB',
  storagemanagement: '存储管理',
  thirdPartyAuthManager: '三方认证',
  smb: 'SMB',
  coraza: 'Coraza',
  portforward: '端口转发',
  iconlib: '图标库',
  stun: 'STUN',
}

/** 有独立专用面板的模块（顶部固定区入口），不出现在通用模块列表。 */
export const DEDICATED_PANEL_MODULES = new Set(['webservice', 'docker', 'smb'])
