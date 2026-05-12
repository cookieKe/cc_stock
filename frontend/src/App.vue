<template>
  <div class="app">
    <nav class="sidebar">
      <h2 class="logo">📈 A股推荐</h2>
      <router-link to="/">📊 仪表盘</router-link>
      <router-link to="/scanner">🔍 市场扫描</router-link>
      <router-link to="/watchlist">⭐ 自选追踪</router-link>
      <router-link to="/strategies">⚙️ 策略管理</router-link>
      <router-link to="/data">📋 数据汇总</router-link>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; color: #333; }
.app { display: flex; min-height: 100vh; }
.sidebar {
  width: 200px; background: #001529; color: #fff; padding: 20px 0;
  display: flex; flex-direction: column; gap: 4px;
}
.sidebar .logo { font-size: 18px; padding: 0 20px; margin-bottom: 16px; color: #1890ff; }
.sidebar a {
  color: #ffffffaa; text-decoration: none; padding: 10px 20px;
  font-size: 14px; transition: all 0.2s;
}
.sidebar a:hover, .sidebar a.router-link-active { color: #fff; background: #1890ff; }
.content { flex: 1; padding: 24px; overflow-y: auto; }
.card { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.card h3 { margin-bottom: 12px; font-size: 16px; color: #1a1a1a; }
.btn {
  display: inline-block; padding: 8px 16px; border: none; border-radius: 4px;
  cursor: pointer; font-size: 14px; transition: opacity 0.2s;
}
.btn:hover { opacity: 0.85; }
.btn-primary { background: #1890ff; color: #fff; }
.btn-danger { background: #ff4d4f; color: #fff; }
.btn-default { background: #f5f5f5; color: #333; border: 1px solid #d9d9d9; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; font-size: 14px; }
th { background: #fafafa; font-weight: 600; color: #555; }
tr:hover { background: #fafafa; }
.positive { color: #cf1322; }
.negative { color: #3f8600; }
.flex-row { display: flex; gap: 16px; align-items: center; }
.flex-between { display: flex; justify-content: space-between; align-items: center; }
input, select { padding: 6px 10px; border: 1px solid #d9d9d9; border-radius: 4px; font-size: 14px; }
.chart-box { width: 100%; height: 400px; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.metric-card { background: #fafafa; border-radius: 6px; padding: 14px; text-align: center; }
.metric-card .value { font-size: 22px; font-weight: bold; margin-top: 4px; }
.metric-card .label { font-size: 12px; color: #888; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: #fff; border-radius: 8px; padding: 24px; min-width: 380px; max-width: 500px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); }
.modal-box h3 { margin-bottom: 16px; }
.param-row { display: flex; align-items: center; gap: 12px; padding: 6px 0; }
.param-row label { width: 140px; font-size: 13px; color: #555; text-align: right; }
.param-row input { flex: 1; padding: 5px 8px; border: 1px solid #d9d9d9; border-radius: 4px; font-size: 13px; }
.table-scroll { max-height: 520px; overflow-y: auto; }
.table-scroll thead { position: sticky; top: 0; z-index: 1; }
</style>
