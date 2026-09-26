import AppKit
import Foundation
import UserNotifications
#if canImport(WPSBackupCore)
import WPSBackupCore
#endif

@MainActor
final class AppModel: ObservableObject {
    @Published var settings: AppSettings
    @Published var status: EngineStatus?
    @Published var statusError: String?
    @Published var progress: RunProgress?
    @Published var agent: AgentState = .unknown
    @Published var health = Health(level: .warn, reasons: ["正在读取状态…"])
    @Published var busyMessage: String?
    @Published var loginOutput: String = ""
    @Published var loginRunning = false

    private var fastTimer: Timer?
    private var slowTimer: Timer?
    private var refreshing = false
    private var loginProcess: Process?

    nonisolated static let defaultEngineRoot =
        Bundle.main.object(forInfoDictionaryKey: "WPSEngineRoot") as? String ?? ""

    var env: EngineEnvironment { EngineEnvironment(settings: settings) }

    init() {
        settings = AppSettings.load(defaultEngineRoot: Self.defaultEngineRoot)
        if !FileManager.default.fileExists(atPath: AppConstants.settingsURL.path) {
            try? settings.save()   // runner 读取同一份设置
        }
        Notifier.requestAuthorization()
        // 首次启动：登录时自动打开菜单栏图标（异常通知由 GUI 发出）；之后尊重用户在设置中的选择
        // （v2：登录项改为经典 LaunchAgent，旧的 SMAppService 登录项在清理时已移除，需重新配置一次）
        if !UserDefaults.standard.bool(forKey: "didConfigureLoginItemV2") {
            AgentManager.launchAtLogin = true
            UserDefaults.standard.set(true, forKey: "didConfigureLoginItemV2")
        }
        // 每次启动幂等安装/修复定时任务（内容未变且已加载时不做任何事）；
        // 用户在“登录项”中关闭的，不强行打开，只在菜单中提示
        AgentManager.installScheduler(stateDir: env.stateDir)
        AgentManager.refreshLoginItemPath()
        agent = AgentManager.state
        refreshStatus()
        fastTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.pollProgress() }
        }
        slowTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshStatus() }
        }
    }

    // MARK: - 状态

    func refreshStatus() {
        guard !refreshing else { return }
        refreshing = true
        agent = AgentManager.state
        let env = self.env
        Task.detached {
            let (decoded, message) = AppModel.fetchStatus(env)
            await MainActor.run {
                self.refreshing = false
                self.status = decoded ?? self.status
                self.statusError = message
                self.recomputeHealth(engineAvailable: decoded != nil)
            }
        }
    }

    /// 调用引擎 `status --json`（GUI 与 --diagnose 共用）
    nonisolated static func fetchStatus(_ env: EngineEnvironment) -> (EngineStatus?, String?) {
        let r = Shell.run(env.settings.pythonPath, Array(env.arguments(["status", "--json"]).dropFirst()),
                          env: env.variables, cwd: env.settings.engineRoot, timeout: 60)
        guard r.status == 0, let data = r.stdout.data(using: .utf8) else {
            return (nil, r.stderr.split(separator: "\n").last.map(String.init) ?? "退出码 \(r.status)")
        }
        do { return (try EngineStatus.decode(data), nil) } catch { return (nil, "状态解析失败：\(error)") }
    }

    private func recomputeHealth(engineAvailable: Bool) {
        let new = mergeHealth(engine: engineAvailable ? status : nil, agent: agent,
                              engineError: statusError)

        health = new
        Notifier.notifyIfChanged(health: new, lastRun: status?.lastRun)
    }

    func pollProgress() {
        let url = URL(fileURLWithPath: env.stateDir).appendingPathComponent("progress.json")
        var p: RunProgress?
        if let data = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder().decode(RunProgress.self, from: data),
           let pid = decoded.pid, kill(pid_t(pid), 0) == 0 {
            p = decoded
        }
        let wasRunning = progress != nil
        progress = p
        if wasRunning && p == nil {
            busyMessage = nil
            refreshStatus()      // 运行结束，立即刷新结果
        }
    }

    // MARK: - 操作

    func backupNow() {
        let marker = URL(fileURLWithPath: env.stateDir).appendingPathComponent("force_run")
        try? Data().write(to: marker)
        busyMessage = "正在启动备份…"
        if agent == .enabled, AgentManager.kickstart() {
            return
        }
        // agent 不可用时直接运行 runner 等价命令（同样经过运行锁与运行记录）
        let env = self.env
        Task.detached {
            _ = Shell.run(env.settings.pythonPath, Array(env.arguments(["scheduled"]).dropFirst()),
                          env: env.variables, cwd: env.settings.engineRoot, timeout: 24 * 3600)
        }
    }

    func cancelRun() {
        guard let pid = progress?.pid else { return }
        kill(pid_t(pid), SIGTERM)
        busyMessage = "正在取消…"
    }

    func enableAgent(force: Bool = true) {
        let stateDir = env.stateDir
        Task.detached {
            AgentManager.installScheduler(stateDir: stateDir, force: force)
            await MainActor.run {
                self.agent = AgentManager.state
                self.refreshStatus()
            }
        }
    }

    func saveSettings(_ s: AppSettings) {
        settings = s
        try? s.save()
        refreshStatus()
    }

    func openBackupFolder() {
        NSWorkspace.shared.open(URL(fileURLWithPath: status?.backupDir ?? env.backupDir))
    }

    func openLog() {
        NSWorkspace.shared.open(URL(fileURLWithPath: status?.logFile ?? env.stateDir + "/backup.log"))
    }

    // MARK: - 重新登录（唯一需要人工的步骤）

    func relogin() {
        guard !loginRunning else { return }
        let cli = status?.cli?.path ?? NSHomeDirectory() + "/.local/bin/wps365-cli"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: cli)
        p.arguments = ["auth", "login", "--device"]
        p.environment = env.variables
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        loginOutput = ""
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let s = String(decoding: h.availableData, as: UTF8.self)
            guard !s.isEmpty else { return }
            Task { @MainActor in self?.loginOutput += s }
        }
        p.terminationHandler = { [weak self] proc in
            pipe.fileHandleForReading.readabilityHandler = nil
            Task { @MainActor in
                guard let self else { return }
                self.loginRunning = false
                self.loginOutput += "\n登录进程结束（退出码 \(proc.terminationStatus)）"
                self.refreshStatus()
                if proc.terminationStatus == 0 { self.backupNow() }
            }
        }
        do {
            try p.run()
            loginRunning = true
            loginProcess = p
        } catch {
            loginOutput = "无法启动 wps365-cli：\(error)"
        }
    }

    func cancelLogin() {
        loginProcess?.terminate()
    }
}

// MARK: - 通知（仅异常，不通知成功）

enum Notifier {
    private static let key = "lastNotifiedSignature"

    static func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    static func notifyIfChanged(health: Health, lastRun: LastRun?) {
        guard health.level != .ok else {
            UserDefaults.standard.removeObject(forKey: key)
            return
        }
        let sig = health.reasons.joined(separator: "|") + "#" + (lastRun?.finishedAt ?? "")
        guard UserDefaults.standard.string(forKey: key) != sig else { return }
        UserDefaults.standard.set(sig, forKey: key)
        post(title: health.level == .error ? "WPS 备份需要处理" : "WPS 备份提醒",
             body: health.reasons.first ?? "")
    }

    /// `WPSBackup --test-notify`：验证通知链路（授权状态 + 实际发送）
    static func selfTest() -> Never {
        let sem = DispatchSemaphore(value: 0)
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, error in
            print("authorization granted=\(granted) error=\(String(describing: error))")
            sem.signal()
        }
        _ = sem.wait(timeout: .now() + 30)
        UNUserNotificationCenter.current().getNotificationSettings { s in
            print("authorizationStatus=\(s.authorizationStatus.rawValue) (2=authorized) alertSetting=\(s.alertSetting.rawValue)")
            sem.signal()
        }
        _ = sem.wait(timeout: .now() + 10)
        post(title: "WPS 备份通知测试", body: "如果你看到这条通知，异常提醒可以正常送达。")
        Thread.sleep(forTimeInterval: 3)
        exit(0)
    }

    /// 已授权 → 系统通知；未授权/被拒（ad-hoc 签名 App 常见，且 add() 不报错会静默丢弃）→ AppleScript 通知
    static func post(title: String, body: String) {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
                postViaAppleScript(title: title, body: body)
                return
            }
            let c = UNMutableNotificationContent()
            c.title = title
            c.body = body
            let req = UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil)
            UNUserNotificationCenter.current().add(req) { error in
                if error != nil { postViaAppleScript(title: title, body: body) }
            }
        }
    }

    static func postViaAppleScript(title: String, body: String) {
        let script = "display notification \(quote(body)) with title \(quote(title))"
        let r = Shell.run("/usr/bin/osascript", ["-e", script])
        print("osascript notification exit=\(r.status) \(r.stderr)")
    }

    private static func quote(_ s: String) -> String {
        "\"" + s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") + "\""
    }
}
