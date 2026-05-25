# WPS CalDAV 同步故障根因分析 & 解决方案

## 一、根因分析

### 为什么 WPS CalDAV 只能同步一次？

根据我们的协议测试，WPS CalDAV 存在三个客户端兼容性"毒丸"：

```
1. Digest Auth (MD5, qop=auth)
   → 需要维护 nonce、nc 计数器
   → 客户端第二次同步时 nonce 可能过期或 nc 不同步
   → 认证失败 → 客户端放弃同步

2. 307 重定向 (/r/9/ → /r/9)
   → REPORT 请求被 307 重定向
   → 很多日历客户端对 CalDAV 重定向处理有 bug
   → 请求失败 → 客户端放弃

3. ctag 不稳定 (2秒内变化，事件数不变)
   → 客户端检测到 ctag 变化 = 认为日历有更新
   → 发起全量同步 → 遇到上述认证/重定向问题
   → 失败 → 标记账号为"不健康" → 停止同步
```

**为什么飞书可以？**

| 特性 | 飞书 | WPS | 客户端兼容性 |
|------|------|-----|-------------|
| 认证 | Basic | Digest | Basic 无状态，100%兼容 |
| 重定向 | 无 | 307 尾斜杠 | 无重定向 = 无故障点 |
| 路径格式 | `/u_xxx/UUID/` | `/r/9/UUID` | 飞书更标准 |
| ctag | 时间戳数字 | URL 格式 | 飞书格式更标准 |

**结论：不是 WPS 服务器有问题，是 WPS 的实现与主流日历客户端的兼容性差。**

---

## 二、方案分析

### 方案 A：WPS CLI → 飞书日历桥接（推荐，最简单）

```
┌──────────┐    WPS CLI    ┌──────────┐   CalDAV    ┌────────────────────┐
│  WPS 日历 │ ←──────────→ │  桥接脚本  │ ←─────────→ │ 飞书日历            │
└──────────┘  (定时拉取)   └──────────┘  (写入事件)  │ → Mac/iPad/Android  │
                                           Basic Auth └────────────────────┘
```

**实现：**
1. Python/Go 脚本通过 WPS CLI 或直接 HTTP 拉取日历事件
2. 与本地 SQLite 缓存对比，检测增删改
3. 通过飞书 Calendar API 写入飞书日历
4. 所有设备通过飞书 CalDAV 同步（已验证可用！）

**优点：**
- 实施最简单（~200行 Python）
- 不需要服务器，Mac 上 cron 运行即可
- 飞书 CalDAV 已在所有设备验证可用
- 维护成本极低

**缺点：**
- WPS → 飞书单向同步
- Mac 需要保持开机（或部署到云服务器）
- 依赖飞书日历 API 限额

**实施周期：** 1-2 天

---

### 方案 B：WPS CalDAV 代理服务（推荐，长期最优）

```
┌──────────┐   CalDAV (代理)   ┌──────────────────┐   CalDAV   ┌──────────────┐
│  WPS 日历 │ ←───────────────→ │ WPS CalDAV Proxy  │ ←────────→ │ iOS/Android/ │
└──────────┘  (Digest Auth)     │ :8843             │ Basic Auth │ Mac 日历 App │
                                │ · 稳定 ctag        │            └──────────────┘
                                │ · 支持 sync-token  │
                                │ · Basic Auth       │
                                │ · SQLite 缓存      │
                                └──────────────────┘
```

**实现：**
一个轻量级 Go/Python CalDAV 服务：
1. 后端：通过 WPS CalDAV 拉取事件，SQLite 本地缓存
2. 前端：标准 CalDAV 端点，Basic Auth，稳定 ctag (etags 的 hash)
3. 智能 poll：每 N 分钟拉取 WPS，仅 etag 变化时更新缓存
4. 可部署在任何 Linux 服务器 (x86/ARM/树莓派)

**优点：**
- 完整 CalDAV 协议支持，标准兼容性最佳
- 可支持稳定的 ctag 和 sync-token
- 不依赖飞书，完全独立
- 一次部署，所有设备通用

**缺点：**
- 需要一台长期运行的服务器（VPS/家庭服务器/树莓派）
- 实施成本较高（~500行 Go + 测试）
- 需要维护服务

**实施周期：** 3-5 天

---

### 方案 C：利用现有 WPS CLI + cron 直接同步到本地 iCalendar

```
WPS CLI → 拉取事件 → 生成本地 .ics 文件 → macOS 日历订阅 .ics URL
```

**优点：** 最简单
**缺点：** 只支持 macOS（订阅日历），不支持 Android/iOS；且订阅日历是只读的

---

## 三、我的推荐：方案 A + B 组合

```
短期（本周）：方案 A — WPS → 飞书桥接
              └─ 立即解决所有设备同步问题

长期（2周内）：方案 B — WPS CalDAV Proxy
              └─ 摆脱飞书依赖，自己掌控
```

### 详细实施计划

#### Step 1：WPS CLI 事件拉取（已验证可工作）

```python
# 已实现的基础能力
- Digest Auth 认证 ✅
- 日历发现 ✅  
- 事件获取 (REPORT) ✅
- ctag 检测 ✅
- etag 变更检测 ✅
```

#### Step 2：飞书日历写入桥接（方案A核心）

```python
# 伪代码
class WPS2FeishuSync:
    def run(self):
        # 1. 从 WPS 拉取所有事件 (etag + calendar-data)
        wps_events = self.fetch_wps_events()
        
        # 2. 与本地缓存比较
        cache = self.load_cache()  # {uid: {etag, ...}}
        created, updated, deleted = self.diff(wps_events, cache)
        
        # 3. 通过飞书 API 同步到飞书日历
        for event in created:
            self.feishu_create_event(event)
        for event in updated:  
            self.feishu_update_event(event)
        for uid in deleted:
            self.feishu_delete_event(uid)
        
        # 4. 更新缓存
        self.save_cache(wps_events)
```

#### Step 3：CalDAV Proxy（方案B核心）

```go
// 核心组件
type WPSProxy struct {
    backend    *WPSClient      // WPS CalDAV 客户端
    cache      *sqlite.DB      // 事件缓存
    caldavSrv  *caldav.Server  // 前端 CalDAV 服务
}

// 关键：稳定的 ctag = SHA256(所有 etags 排序后拼接)
func (p *WPSProxy) stableCtag() string {
    etags := p.cache.GetAllETags()
    sort.Strings(etags)
    return sha256(join(etags))
}
```

---

## 四、还需要确认的信息

1. **你的 Mac 是长期开机的吗？** → 影响方案A的 cron 执行
2. **有没有可用的 Linux 服务器（VPS/树莓派/家庭NAS）？** → 影响方案B的部署
3. **飞书日历 API 是否可用？** — 你有飞书开发者权限吗？
4. **WPS CLI 能做什么？** — 是否有批量导出/导入日历的能力？

**如果以上条件都不满足**，还有一个折中方案：在你的 Mac 上用 Python 起一个小型 CalDAV 代理（localhost），然后通过 Zerotier/Tailscale 让其他设备访问。

---

## 下一步行动建议

1. **先确认**：WPS CLI 能力、飞书 API 权限、是否有可用服务器
2. **快速验证**：用方案A的 WPS→飞书桥接脚本，手动运行一次验证可行性
3. **正式部署**：cron 定时运行，所有设备连飞书 CalDAV
4. **长期规划**：评估是否需要独立 CalDAV Proxy

需要我开始编写方案A的桥接脚本吗？