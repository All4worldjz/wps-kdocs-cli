import AppKit
import SwiftUI
#if canImport(WPSBackupCore)
import WPSBackupCore
#endif

@main
enum Entry {
    static func main() {
        if CommandLine.arguments.contains("--test-notify") {
            Notifier.selfTest()
        }
        if CommandLine.arguments.contains("--diagnose") {
            Diagnose.run()
        } else {
            WPSBackupApp.main()
        }
    }
}

/// `WPS Backup.app/Contents/MacOS/WPSBackup --diagnose`：打印 GUI 所见的状态（排障/验收用）
enum Diagnose {
    static func run() -> Never {
        let settings = AppSettings.load(defaultEngineRoot: AppModel.defaultEngineRoot)
        let env = EngineEnvironment(settings: settings)
        let agent = AgentManager.state
        let (status, err) = AppModel.fetchStatus(env)
        let health = mergeHealth(engine: status, agent: agent, engineError: err)
        print("engineRoot:   \(settings.engineRoot)")
        print("python:       \(settings.pythonPath)")
        print("scheduler:    \(agent) [\(AgentManager.lastExit)] plist=\(AgentManager.plistURL(AppConstants.schedulerLabel).path)")
        print("loginItem:    \(AgentManager.launchAtLogin)")
        print("cli:          \(status?.cli?.path ?? "-") \(status?.cli?.version ?? "")")
        print("auth:         \(status?.auth?.status ?? "-") refreshable=\(status?.auth?.refreshable ?? false) until \(status?.auth?.refreshTokenExpiresAt ?? "-")")
        print("lastRun:      exit=\(status?.lastRun?.exitCode.description ?? "-") at \(status?.lastRun?.finishedAt ?? "-")")
        print("lastSuccess:  \(status?.lastSuccessAt ?? "-")")
        print("heartbeat:    \(status?.heartbeat?.at ?? "-")")
        print("nextRun:      \(status?.nextRunAt ?? "-")")
        print("health:       \(health.level.rawValue) \(health.reasons)")
        if let err { print("engineError:  \(err)") }
        exit(health.level == .error ? 1 : 0)
    }
}

struct WPSBackupApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        MenuBarExtra {
            MenuContent().environmentObject(model)
        } label: {
            Image(systemName: model.menuIcon)
        }
        .menuBarExtraStyle(.window)

        Window("WPS Backup 设置", id: "settings") {
            SettingsView().environmentObject(model)
        }
        .windowResizability(.contentSize)
    }
}

extension AppModel {
    var menuIcon: String {
        if progress != nil { return "arrow.triangle.2.circlepath.icloud" }
        switch health.level {
        case .ok: return "checkmark.icloud"
        case .warn: return "exclamationmark.icloud"
        case .error: return "xmark.icloud"
        }
    }
}

private func fmt(_ iso: String?) -> String {
    guard let d = ISO8601Local.parse(iso) else { return "—" }
    let f = DateFormatter()
    f.dateFormat = Calendar.current.isDateInToday(d) ? "今天 HH:mm" : "MM-dd HH:mm"
    return f.string(from: d)
}

private func bytes(_ n: Int64?) -> String {
    guard let n else { return "—" }
    return ByteCountFormatter.string(fromByteCount: n, countStyle: .file)
}

struct MenuContent: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            if !model.health.reasons.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(model.health.reasons, id: \.self) { r in
                        Label(r, systemImage: model.health.level == .error ? "xmark.octagon.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(model.health.level == .error ? .red : .orange)
                            .font(.callout)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    actionsForProblems
                }
            }
            if let p = model.progress { progressView(p) }
            Divider()
            summary
            if let errs = model.status?.lastRun?.errors, !errs.isEmpty {
                DisclosureGroup("上次错误（\(model.status?.lastRun?.errorCount ?? errs.count)）") {
                    ScrollView {
                        VStack(alignment: .leading) {
                            ForEach(errs, id: \.self) { Text($0).font(.caption).textSelection(.enabled) }
                        }
                    }.frame(maxHeight: 120)
                }
            }
            Divider()
            buttons
        }
        .padding(14)
        .frame(width: 340)
        .onAppear { model.refreshStatus() }
    }

    private var header: some View {
        HStack {
            Image(systemName: model.menuIcon)
                .foregroundStyle(model.health.level == .ok ? .green : (model.health.level == .warn ? .orange : .red))
                .font(.title2)
            VStack(alignment: .leading) {
                Text("WPS 云盘备份").font(.headline)
                Text(model.progress != nil ? "备份进行中" :
                        (model.health.level == .ok ? "一切正常" : (model.health.level == .warn ? "需要留意" : "需要处理")))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    @ViewBuilder private var actionsForProblems: some View {
        HStack {
            if model.agent == .requiresApproval {
                Button("打开登录项设置") { AgentManager.openLoginItemsSettings() }
            }
            if model.agent == .notRegistered || model.agent == .notFound || model.agent == .spawnFailed {
                Button("启用定时备份") { model.enableAgent() }
            }
            if model.status?.auth?.status != "valid" && model.status?.auth?.refreshable != true && model.status != nil {
                Button("重新登录 WPS") { model.relogin(); openWindow(id: "settings") }
            }
        }.controlSize(.small)
    }

    private func progressView(_ p: RunProgress) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            let phase = ["scan": "扫描云盘", "download": "下载文件", "otl": "备份智能文档", "starting": "准备中"][p.phase ?? ""] ?? (p.phase ?? "")
            Text("\(phase) \(p.total ?? 0 > 0 ? "\(p.done ?? 0)/\(p.total ?? 0)" : "")").font(.callout)
            if (p.total ?? 0) > 0 { ProgressView(value: p.fraction) } else { ProgressView().progressViewStyle(.linear) }
            if let c = p.current, !c.isEmpty { Text(c).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
        }
    }

    private var summary: some View {
        let st = model.status
        let counts = st?.lastRun?.counts ?? [:]
        return Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
            GridRow { Text("上次成功").foregroundStyle(.secondary); Text(fmt(st?.lastSuccessAt)) }
            GridRow { Text("上次运行").foregroundStyle(.secondary)
                Text("\(fmt(st?.lastRun?.finishedAt))  \(exitText(st?.lastRun?.exitCode))") }
            GridRow { Text("本次变化").foregroundStyle(.secondary)
                Text("新增 \(counts["new"] ?? 0) · 更新 \(counts["updated"] ?? 0) · 失败 \(counts["failed"] ?? 0)") }
            GridRow { Text("下次计划").foregroundStyle(.secondary); Text(fmt(st?.nextRunAt)) }
            GridRow { Text("已备份").foregroundStyle(.secondary)
                Text("\(st?.snapshot?.snapshotCount ?? 0) 个文件 · \(bytes(st?.snapshot?.totalSize))") }
        }.font(.callout)
    }

    private func exitText(_ c: Int?) -> String {
        switch c {
        case 0: return "✅"
        case 1: return "❌ 有失败"
        case 75: return "⏭ 已在运行"
        case 124: return "⏱ 超时"
        case 130: return "⏹ 已取消"
        case nil: return ""
        default: return "退出码 \(c!)"
        }
    }

    private var buttons: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if model.progress != nil {
                    Button("取消备份") { model.cancelRun() }
                } else {
                    Button("立即备份") { model.backupNow() }.keyboardShortcut("b")
                        .disabled(model.busyMessage != nil)
                }
                if let m = model.busyMessage { Text(m).font(.caption).foregroundStyle(.secondary) }
            }
            HStack {
                Button("打开备份目录") { model.openBackupFolder() }
                Button("查看日志") { model.openLog() }
            }
            HStack {
                Button("设置…") { openWindow(id: "settings"); NSApp.activate(ignoringOtherApps: true) }
                Spacer()
                Button("退出") { NSApp.terminate(nil) }
            }
        }.controlSize(.regular)
    }
}

struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    @State private var draft = AppSettings.defaults(engineRoot: "")
    @State private var launchAtLogin = AgentManager.launchAtLogin

    var body: some View {
        Form {
            Section("计划") {
                Stepper("每日备份时间：\(draft.scheduleHour):00", value: $draft.scheduleHour, in: 0...23)
                Text("到点后若当天尚未成功，每小时自动重试（每天最多 3 次）；Mac 睡眠错过时唤醒后补跑。")
                    .font(.caption).foregroundStyle(.secondary)
                Stepper("并发下载线程：\(draft.workers)", value: $draft.workers, in: 1...8)
                Stepper("单次运行上限：\(draft.runTimeoutHours) 小时", value: $draft.runTimeoutHours, in: 1...48)
            }
            Section("内容") {
                Toggle("智能文档同时导出 docx", isOn: $draft.exportDocx)
                Toggle("扫描 WPS Office 本地缓存（需要“完全磁盘访问权限”）", isOn: $draft.cacheScan)
            }
            Section("运行环境") {
                LabeledContent("引擎目录") { Text(draft.engineRoot).textSelection(.enabled).font(.caption) }
                TextField("Python", text: $draft.pythonPath)
                LabeledContent("wps365-cli") {
                    Text("\(model.status?.cli?.path ?? "—")  \(model.status?.cli?.version ?? "")").font(.caption)
                }
                LabeledContent("登录状态") {
                    Text(authText).font(.caption)
                }
            }
            Section("系统") {
                LabeledContent("定时任务") { Text(agentText) }
                HStack {
                    Button(model.agent == .enabled ? "重新安装定时任务" : "启用定时备份") { model.enableAgent() }
                    Button("登录项设置") { AgentManager.openLoginItemsSettings() }
                }
                Toggle("登录时打开菜单栏图标", isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { AgentManager.launchAtLogin = $0 }
            }
            Section("WPS 账号") {
                HStack {
                    Button(model.loginRunning ? "等待浏览器授权…" : "重新登录 WPS") { model.relogin() }
                        .disabled(model.loginRunning)
                    if model.loginRunning { Button("取消") { model.cancelLogin() } }
                }
                if !model.loginOutput.isEmpty {
                    ScrollView {
                        Text(model.loginOutput).font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    }.frame(height: 90)
                }
            }
            HStack {
                Spacer()
                Button("保存") { model.saveSettings(draft) }.keyboardShortcut(.defaultAction)
                    .disabled(draft == model.settings)
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
        .onAppear { draft = model.settings; launchAtLogin = AgentManager.launchAtLogin }
    }

    private var agentText: String {
        switch model.agent {
        case .enabled: return "✅ 已启用（每小时检查，到点运行）"
        case .requiresApproval: return "⚠️ 已在“登录项”中关闭"
        case .spawnFailed: return "❌ 无法启动"
        case .notRegistered, .notFound: return "❌ 未注册"
        case .unknown: return "未知"
        }
    }

    private var authText: String {
        guard let a = model.status?.auth else { return "—" }
        let ok = a.status == "valid" || a.refreshable == true
        return (ok ? "✅ 有效" : "❌ 已失效") + (a.refreshTokenExpiresAt.map { "，至 \(fmt($0))" } ?? "")
            + (a.airpageScope == false ? "（缺 airpage 权限）" : "")
    }
}
